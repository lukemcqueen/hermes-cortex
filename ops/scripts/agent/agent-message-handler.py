#!/usr/bin/env python3
"""
agent-message-handler.py — Inbox message handler for fleet agents.

Polls the agent inbox for messages (UPDATE_REQUEST, ROLLBACK_REQUEST,
GIT_AUTH_CHECK) and processes them, sending results back to Moses.

Uses the Agent Bus HTTP API (lib/cortex_bus.py) — no Docker required.
Set CORTEX_BUS_URL to the orchestrator's external bus endpoint before running.

Designed to run as a systemd timer (Linux), launchd plist (macOS),
or cron on any fleet agent. Silent when no work to do — watchdog pattern.

Env vars:
    CORTEX_BUS_URL     Bus server URL (default http://127.0.0.1:8903)
                       On remote agents, set to e.g. https://your-domain:13004
    CORTEX_BUS_TOKEN   Bearer token for bus auth
    CORTEX_BUS_AUTH    Basic auth string (user:pass) as fallback
    AGENT_NAME         Agent identity (default: hostname)

Usage:
    python3 agent-message-handler.py                  # single poll (cron)
    python3 agent-message-handler.py --once           # same
    python3 agent-message-handler.py --watch          # continuous poll every 5m

Exit codes:
    0 = no work or work completed
    1 = errors encountered
"""

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
CORTEX_REPO = HOME / "hermes-cortex"
CORTEX_UPDATE = CORTEX_REPO / "ops" / "scripts" / "cortex-update.sh"
DOCTOR_PATH = CORTEX_REPO / "ops" / "scripts" / "manage" / "cortex-doctor.py"
# Derive AGENT_NAME from env (set by cron/launchd) or cortex-bus.conf (fleet setup) or hostname
AGENT_NAME = os.environ.get("AGENT_NAME", "")
if not AGENT_NAME:
    bus_conf = HOME / ".hermes-cortex" / "cortex-bus.conf"
    if bus_conf.exists():
        for line in bus_conf.read_text().splitlines():
            if line.startswith("AGENT_NAME="):
                val = line.split("=", 1)[1].strip().strip("\"'")
                AGENT_NAME = val
                break
if not AGENT_NAME:
    AGENT_NAME = socket.gethostname()
# Ensure lib.cortex_bus is importable
from hermes_paths import ensure_scripts_path
ensure_scripts_path()

# State file to track processed correlation_ids for idempotency
STATE_DIR = HOME / ".hermes-cortex" / "state"
STATE_FILE = STATE_DIR / "agent-message-state.json"
STATE_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{AGENT_NAME}] {msg}")


def notify_telegram(message: str, subject: str = ""):
    """Send a notification to Telegram via Bot API directly."""
    try:
        token_path = HOME / ".hermes" / ".env"
        token = ""
        if token_path.exists():
            for line in token_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip("'\"")
                    break
        if not token:
            log("Telegram notify: no TELEGRAM_BOT_TOKEN found")
            return
        chat_id = "1270130526"  # Luke
        text = f"{subject}\n{message}" if subject else message
        # Escape HTML special chars
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        import urllib.request, urllib.parse
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"Telegram notify failed: {e}")


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"processed_ids": [], "last_result": None}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def run_cortex_update() -> dict:
    """Run cortex-update.sh --force-all and capture output."""
    log("Running cortex-update.sh --force-all...")
    try:
        r = subprocess.run(
            ["bash", str(CORTEX_UPDATE), "--force-all"],
            capture_output=True, text=True, timeout=120
        )
        return {
            "success": r.returncode == 0,
            "output": r.stdout[-2000:] if r.stdout else "",
            "stderr": r.stderr[-500:] if r.stderr else "",
            "exit_code": r.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "stderr": "TIMEOUT after 120s", "exit_code": -1}
    except Exception as e:
        return {"success": False, "output": "", "stderr": str(e), "exit_code": -1}


def run_doctor() -> dict:
    """Run cortex-doctor.py --json and parse result."""
    try:
        r = subprocess.run(
            [sys.executable, str(DOCTOR_PATH), "--json"],
            capture_output=True, text=True, timeout=30
        )
        if r.stdout.strip():
            try:
                start = r.stdout.index("{")
                return json.loads(r.stdout[start:])
            except (ValueError, json.JSONDecodeError):
                pass
        return {"healthy": False, "summary": {"pass": 0, "warn": 0, "fail": 0}, "error": "no JSON in doctor output"}
    except Exception as e:
        return {"healthy": False, "summary": {"pass": 0, "warn": 0, "fail": 0}, "error": str(e)}


def send_bus_result(queue: str, correlation_id: str, result_body: dict, subject: str = "UPDATE_RESULT") -> bool:
    """Send a result message back to orchestrator."""
    full_body = {
        "from": AGENT_NAME,
        "to": "moses",
        "topic": "fleet-update",
        "subject": subject,
        "correlation_id": correlation_id,
        "body": result_body,
    }
    try:
        from lib.cortex_bus import bus_send
        result = bus_send(queue, full_body)
        ok = result is not None
        if ok:
            mid = result.get("msg_id", "?") if isinstance(result, dict) else "?"
            if mid is None:
                mid = "?"
            log(f"Sent {subject} to {queue} (mid={mid[:8]}… corr={correlation_id[:8] if correlation_id else '?'}…)")
        else:
            log(f"Failed to send {subject}")
        return ok
    except Exception as e:
        log(f"Error sending {subject}: {e}")
        return False


def read_inbox(queue: str) -> dict | None:
    """Read one message from queue, return parsed body or None."""
    try:
        from lib.cortex_bus import bus_read
        raw = bus_read(queue, vt=30)
        if raw and raw.get("msg_id"):
            # Normalize None fields that could cause subscript crashes downstream
            if raw.get("correlation_id") is None:
                raw["correlation_id"] = ""
            return raw
    except Exception:
        pass
    return None


def process_update_request(msg_body: dict, correlation_id: str) -> dict:
    """Process an UPDATE_REQUEST and return UPDATE_RESULT body."""
    request_raw = msg_body.get("body", {})
    # Inner body is also a JSON string — parse if needed
    if isinstance(request_raw, str):
        try:
            request = json.loads(request_raw)
        except (json.JSONDecodeError, TypeError):
            request = {}
    else:
        request = request_raw
    target_sha = request.get("target_sha", "unknown")
    target_version = request.get("target_version", "")
    run_doctor_flag = request.get("run_doctor", True)

    log(f"Processing UPDATE_REQUEST: SHA={target_sha}")

    # Get SHA before
    try:
        before = subprocess.run(
            ["git", "-C", str(CORTEX_REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        before = "unknown"

    # Run update
    update_result = run_cortex_update()
    if not update_result["success"]:
        # Try one more time
        log("First attempt failed, retrying once...")
        update_result = run_cortex_update()

    # Get SHA after
    try:
        after = subprocess.run(
            ["git", "-C", str(CORTEX_REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        after = "unknown"

    # Run doctor
    doctor = run_doctor() if run_doctor_flag else {}

    # Build result
    result = {
        "success": update_result["success"] and doctor.get("healthy", True),
        "git_sha_before": before,
        "git_sha_after": after,
        "version": doctor.get("version", ""),
        "update_output": update_result.get("output", ""),
        "doctor": doctor,
        "errors": [],
        "duration_seconds": 0,
    }
    if not update_result["success"]:
        result["errors"].append(f"cortex-update failed: {update_result.get('stderr', '')[:200]}")
    if not doctor.get("healthy", False) and run_doctor_flag:
        s = doctor.get("summary", {})
        result["errors"].append(f"Doctor: {s.get('warn', 0)} warn, {s.get('fail', 0)} fail")

    return result


def process_rollback_request(msg_body: dict) -> dict:
    """Process a ROLLBACK_REQUEST — git checkout previous SHA and verify."""
    request_raw = msg_body.get("body", {})
    if isinstance(request_raw, str):
        try:
            request = json.loads(request_raw)
        except (json.JSONDecodeError, TypeError):
            request = {}
    else:
        request = request_raw
    target_sha = request.get("target_sha", "HEAD~1")
    reason = request.get("reason", "No reason given")

    log(f"Processing ROLLBACK_REQUEST: → {target_sha[:12]} ({reason})")

    # Get SHA before
    try:
        sha_before = subprocess.run(
            ["git", "-C", str(CORTEX_REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        sha_before = "unknown"

    # Checkout target SHA
    try:
        r = subprocess.run(
            ["git", "-C", str(CORTEX_REPO), "checkout", target_sha],
            capture_output=True, text=True, timeout=30
        )
        checkout_ok = r.returncode == 0
        if not checkout_ok:
            log(f"git checkout failed: {r.stderr[:200]}")
    except subprocess.TimeoutExpired:
        return {"success": False, "sha_before": sha_before, "sha_after": "failed",
                "reverted": False, "errors": ["git checkout timed out"]}

    # Get SHA after
    try:
        sha_after = subprocess.run(
            ["git", "-C", str(CORTEX_REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        sha_after = "unknown"

    # Run doctor
    doctor = run_doctor()

    return {
        "success": checkout_ok and doctor.get("healthy", False),
        "sha_before": sha_before,
        "sha_after": sha_after,
        "reverted": checkout_ok,
        "doctor": doctor,
        "duration_seconds": 0,
        "errors": [] if checkout_ok else [f"git checkout failed"],
    }


def process_git_auth_check(msg_body: dict) -> dict:
    """Process a GIT_AUTH_CHECK — verify git can ls-remote."""
    request_raw = msg_body.get("body", {})
    if isinstance(request_raw, str):
        try:
            request = json.loads(request_raw)
        except (json.JSONDecodeError, TypeError):
            request = {}
    else:
        request = request_raw
    expected_url = request.get("expected_url", "")

    checks = []

    try:
        r = subprocess.run(["git", "version"], capture_output=True, text=True, timeout=5)
        checks.append(("git installed", r.returncode == 0, r.stdout.strip()))
    except FileNotFoundError:
        return {"authenticated": False, "remote_url": "", "error": "git not found"}

    try:
        r = subprocess.run(
            ["git", "-C", str(CORTEX_REPO), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        remote_url = r.stdout.strip()
        checks.append(("remote URL", expected_url in remote_url, remote_url))
    except Exception as e:
        return {"authenticated": False, "remote_url": "", "error": str(e)}

    try:
        r = subprocess.run(
            ["git", "-C", str(CORTEX_REPO), "ls-remote", "origin", "HEAD"],
            capture_output=True, text=True, timeout=15
        )
        auth_ok = r.returncode == 0 and r.stdout.strip() != ""
        checks.append(("ls-remote", auth_ok, r.stdout.strip()[:40] if auth_ok else r.stderr[:200]))
    except Exception as e:
        checks.append(("ls-remote", False, str(e)))

    all_ok = all(c[1] for c in checks)
    return {
        "authenticated": all_ok,
        "remote_url": remote_url if 'remote_url' in locals() else "unknown",
        "error": "",
        "checks": [{"name": c[0], "pass": c[1], "detail": c[2]} for c in checks],
    }


def process_exec_command(msg_body: dict) -> dict:
    """Process an EXEC command — run a script and return output.

    Message body format:
        command: str   — relative path under ~/.hermes-cortex/scripts/
        params: list   — optional arguments to pass
        timeout: int   — max seconds (default 60)

    Returns:
        success: bool
        stdout: str
        stderr: str
        exit_code: int
        command: str
    """
    request_raw = msg_body.get("body", {})
    if isinstance(request_raw, str):
        try:
            request = json.loads(request_raw)
        except (json.JSONDecodeError, TypeError):
            request = {}
    else:
        request = request_raw

    command = (request.get("command") or "").strip()
    params = request.get("params") or []
    timeout = int(request.get("timeout", 60))

    if not command:
        return {
            "success": False,
            "stdout": "",
            "stderr": "No command specified",
            "exit_code": -1,
            "command": "",
        }

    # Resolve script path — relative under ~/.hermes-cortex/scripts/
    scripts_dir = HOME / ".hermes-cortex" / "scripts"
    script_path = scripts_dir / command

    if not script_path.exists():
        # Try as an absolute path
        abs_path = Path(command)
        if abs_path.exists() and abs_path.is_file():
            script_path = abs_path
        else:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Script not found: {command} (looked in {scripts_dir})",
                "exit_code": -1,
                "command": command,
            }

    log(f"Executing: {script_path} {' '.join(str(p) for p in params)}")

    # Determine interpreter
    cmd_parts = []
    if script_path.suffix in (".py",):
        cmd_parts = [sys.executable, str(script_path)]
    elif script_path.suffix in (".sh", ".bash"):
        cmd_parts = ["bash", str(script_path)]
    else:
        cmd_parts = [str(script_path)]
    cmd_parts.extend(str(p) for p in params)

    try:
        r = subprocess.run(
            cmd_parts,
            capture_output=True, text=True, timeout=timeout
        )
        return {
            "success": r.returncode == 0,
            "stdout": r.stdout,
            "stderr": r.stderr,
            "exit_code": r.returncode,
            "command": command,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"TIMEOUT after {timeout}s",
            "exit_code": -1,
            "command": command,
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "command": command,
        }


def archive_message(queue: str, msg_id: str) -> bool:
    """Archive a processed message from the inbox. Returns True on success."""
    if not msg_id:
        return False
    from lib.cortex_bus import bus_archive
    result = bus_archive(queue, msg_id)
    if not result:
        log(f"⚠️ Failed to archive message {msg_id[:8]}… in {queue}")
    return result


def report_health_change(doctor: dict, prev_doctor: dict) -> None:
    """Report health state change to inbox_health_check queue."""
    healthy = doctor.get("healthy", False)
    summary = doctor.get("summary", {})
    prev_healthy = prev_doctor.get("healthy", True)
    prev_summary = prev_doctor.get("summary", {})

    if not healthy and prev_healthy:
        level = "ISSUES_DETECTED"
        log(f"⚠️  Health degraded: {summary.get('fail', 0)} fail, {summary.get('warn', 0)} warn")
    elif healthy and not prev_healthy:
        level = "HEALTHY_NOW"
        log(f"✅ Health recovered: {prev_summary.get('fail', 0)}→{summary.get('fail', 0)} fail")
    else:
        level = "PERSISTENT_ISSUES"
        log(f"⚠️  Health still failing: {summary.get('fail', 0)} fail, {summary.get('warn', 0)} warn")

    full_body = {
        "from": AGENT_NAME,
        "to": "moses",
        "topic": "health",
        "subject": f"HEALTH_{level}",
        "body": {
            "healthy": healthy,
            "summary": summary,
            "prev_summary": prev_summary if not prev_healthy else {},
        },
    }
    try:
        from lib.cortex_bus import bus_send
        result = bus_send("inbox_health_check", full_body)
        if result:
            log(f"Health report sent: {level}")
    except Exception as e:
        log(f"Failed to send health report: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Agent message handler")
    parser.add_argument("--once", action="store_true", help="Single poll (default)")
    parser.add_argument("--watch", action="store_true", help="Continuous poll every 5 minutes")
    parser.add_argument("--interval", type=int, default=300, help="Poll interval in seconds (default 300)")
    args = parser.parse_args()

    inbox_queue = f"inbox_{AGENT_NAME}"
    log(f"Starting — polling {inbox_queue}")
    state = load_state()
    processed = set(state.get("processed_ids", []))

    def poll_once() -> bool:
        msg = read_inbox(inbox_queue)
        if not msg:
            return False

        body = msg.get("body", {})
        if body is None:
            body = {}
        msg_id = msg.get("msg_id", "")
        correlation_id = msg.get("correlation_id", "")
        if correlation_id is None:
            correlation_id = ""
        # Fallback: correlation_id may be inside the body dict
        if not correlation_id and isinstance(body, dict):
            correlation_id = body.get("correlation_id", "") or ""

        # PGMQ returns body as a JSON string — parse it if needed
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except (json.JSONDecodeError, TypeError):
                # Plain-text body — try to match known keyword prefixes
                body_str = body.strip()
                known_prefixes = {
                    "UPDATE_REQUEST:": "UPDATE_REQUEST",
                    "ROLLBACK_REQUEST:": "ROLLBACK_REQUEST",
                    "GIT_AUTH_CHECK:": "GIT_AUTH_CHECK",
                    "FIX_REQUEST:": "FIX_REQUEST",
                    "DIAGNOSTIC_REQUEST:": "DIAGNOSTIC_REQUEST",
                }
                matched = None
                for prefix, subject_val in known_prefixes.items():
                    if body_str.startswith(prefix):
                        rest = body_str[len(prefix):].strip()
                        matched = {
                            "subject": subject_val,
                            "body": {"command": rest, "run_doctor": True} if subject_val == "UPDATE_REQUEST" else {"reason": rest},
                        }
                        break

                if matched:
                    body = matched
                    log(f"Parsed plain-text body as {body['subject']}: {body_str[:80]}…")
                else:
                    # Archive unparseable so it doesn't loop forever
                    log(f"Unparseable message body, archiving: {body_str[:100]}…")
                    archive_message(inbox_queue, msg_id)
                    return False

        subject = body.get("subject", "")

        # Notify pickup
        notify_telegram(
            f"📥 [{AGENT_NAME}] Received {subject} from {body.get('from', '?')}",
            f"📥 {AGENT_NAME}:{subject}",
        )

        # Idempotency check
        if correlation_id in processed:
            log(f"Skipping already-processed corr={correlation_id[:8] if correlation_id else ''}…")
            # Archive so it doesn't loop forever
            archive_message(inbox_queue, msg_id)
            return False

        if subject == "UPDATE_REQUEST":
            # Process
            start = time.time()
            result_body = process_update_request(body, correlation_id)
            result_body["duration_seconds"] = round(time.time() - start, 1)
            archive_message(inbox_queue, msg.get("msg_id", ""))
            send_bus_result("inbox_moses", correlation_id, result_body, "UPDATE_RESULT")

            processed.add(correlation_id)
            state.setdefault("processed_ids", [])
            state["processed_ids"].append(correlation_id)
            state["processed_ids"] = state["processed_ids"][-50:]
            state["last_result"] = result_body
            save_state(state)

            if result_body["success"]:
                log(f"✅ Update successful: {result_body['git_sha_before']} → {result_body['git_sha_after']}")
                notify_telegram(f"✅ [{AGENT_NAME}] Update: {result_body['git_sha_before'][:7]}→{result_body['git_sha_after'][:7]}",
                                f"✅ {AGENT_NAME}:UPDATE")
            else:
                log(f"❌ Update had issues: {len(result_body['errors'])} error(s)")
                notify_telegram(f"❌ [{AGENT_NAME}] Update failed: {result_body['errors'][0][:120] if result_body['errors'] else 'unknown'}",
                                f"❌ {AGENT_NAME}:UPDATE")
            return True

        elif subject == "ROLLBACK_REQUEST":
            start = time.time()
            result_body = process_rollback_request(body)
            result_body["duration_seconds"] = round(time.time() - start, 1)
            archive_message(inbox_queue, msg.get("msg_id", ""))
            send_bus_result("inbox_moses", correlation_id, result_body, "ROLLBACK_RESULT")

            processed.add(correlation_id)
            state.setdefault("processed_ids", [])
            state["processed_ids"].append(correlation_id)
            state["processed_ids"] = state["processed_ids"][-50:]
            save_state(state)

            log(f"{'✅' if result_body['success'] else '❌'} Rollback: {result_body.get('sha_before', '?')[:8]} → {result_body.get('sha_after', '?')[:8]}")
            notify_telegram(
                f"{'✅' if result_body['success'] else '❌'} [{AGENT_NAME}] Rollback: {result_body.get('sha_before', '?')[:7]}→{result_body.get('sha_after', '?')[:7]}",
                f"{'✅' if result_body['success'] else '❌'} {AGENT_NAME}:ROLLBACK"
            )
            return True

        elif subject == "GIT_AUTH_CHECK":
            result_body = process_git_auth_check(body)
            archive_message(inbox_queue, msg.get("msg_id", ""))
            send_bus_result("inbox_moses", correlation_id, result_body, "GIT_AUTH_RESULT")

            processed.add(correlation_id)
            state.setdefault("processed_ids", [])
            state["processed_ids"].append(correlation_id)
            state["processed_ids"] = state["processed_ids"][-50:]
            save_state(state)

            auth_ok = result_body.get('authenticated', False)
            log(f"{'✅' if auth_ok else '❌'} Git auth: {result_body.get('remote_url', '?')}")
            notify_telegram(
                f"{'✅' if auth_ok else '❌'} [{AGENT_NAME}] Git auth: {result_body.get('remote_url', '?')[:60]}",
                f"{'✅' if auth_ok else '❌'} {AGENT_NAME}:GIT_AUTH"
            )
            return True

        elif subject == "EXEC":
            start = time.time()
            result_body = process_exec_command(body)
            archive_message(inbox_queue, msg.get("msg_id", ""))
            send_bus_result("inbox_moses", correlation_id, result_body, "EXEC_RESULT")

            processed.add(correlation_id)
            state.setdefault("processed_ids", [])
            state["processed_ids"].append(correlation_id)
            state["processed_ids"] = state["processed_ids"][-50:]
            save_state(state)

            status = "✅" if result_body["success"] else "❌"
            stdout_preview = (result_body.get("stdout", "") or "")[:80].replace("\n", " ")
            log(f"{status} EXEC {result_body.get('command', '?')}: exit={result_body.get('exit_code', '?')}  {stdout_preview}")
            notify_telegram(
                f"{status} [{AGENT_NAME}] EXEC {result_body.get('command', '?')}: exit={result_body.get('exit_code', '?')} — {stdout_preview}",
                f"{status} {AGENT_NAME}:EXEC"
            )
            return True

        elif subject == "FIX_REQUEST":
            log(f"Received FIX_REQUEST (corr={correlation_id[:8]}…) — not yet implemented")
            return False

        elif subject == "DIAGNOSTIC_REQUEST":
            # Run agent diagnostics and return result via bus
            check = ""
            if isinstance(body.get("body"), dict):
                check = body["body"].get("check", "")
            respond_to = "inbox_moses"
            if isinstance(body.get("body"), dict):
                respond_to = body["body"].get("respond_to_queue", "inbox_moses")
            log(f"DIAGNOSTIC_REQUEST from {body.get('from', '?')}: check={check or 'all'}")
            archive_message(inbox_queue, msg.get("msg_id", ""))

            # Run diagnostic as subprocess
            result_body = {}
            try:
                script = Path(__file__).resolve().parent / "agent-diagnostic.py"
                cmd = [sys.executable, str(script)]
                if check:
                    cmd += ["--check", check]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                if r.returncode == 0 and r.stdout:
                    result_body = json.loads(r.stdout)
                else:
                    result_body = {"error": r.stderr[:200] or "No output"}
            except Exception as e:
                result_body = {"error": str(e)[:200]}

            log(f"Sending DIAGNOSTIC_RESULT to {respond_to} (corr={correlation_id[:8]}…)")
            send_bus_result(respond_to, correlation_id, result_body, "DIAGNOSTIC_RESULT")
            log(f"DIAGNOSTIC_RESULT sent (corr={correlation_id[:8]}…)")
            notify_telegram(
                f"📋 [{AGENT_NAME}] Diagnostic sent to {respond_to}: {result_body.get('error', 'OK')[:80]}",
                f"📋 {AGENT_NAME}:DIAGNOSTIC"
            )
            return True

        # Unknown subject — archive so it doesn't loop forever
        log(f"Unknown subject '{subject}', archiving (corr={correlation_id[:8]}…)")
        archive_message(inbox_queue, msg_id)
        notify_telegram(
            f"⚠️ [{AGENT_NAME}] Unknown subject '{subject}' from {body.get('from', '?')}, archived",
            f"⚠️ {AGENT_NAME}:UNKNOWN"
        )
        return False

    # Health state tracking (report on state change, not every tick)
    last_doctor = state.get("last_doctor", {})

    def poll_and_check() -> None:
        nonlocal last_doctor
        had_work = poll_once()
        # Only run doctor when we actually processed a message
        if not had_work:
            return
        doctor = run_doctor()
        healthy = doctor.get("healthy", False)
        prev_healthy = last_doctor.get("healthy", True)
        # Report on state change
        if healthy != prev_healthy or (not healthy and not prev_healthy):
            report_health_change(doctor, last_doctor)
            last_doctor = doctor
            state["last_doctor"] = doctor
            save_state(state)
        elif healthy:
            last_doctor = doctor  # silently update
            state["last_doctor"] = doctor
            save_state(state)

    if args.watch:
        log(f"Starting watch mode (interval={args.interval}s)")
        while True:
            try:
                poll_and_check()
            except Exception as e:
                log(f"Error in poll cycle: {e}")
            time.sleep(args.interval)
    else:
        try:
            poll_and_check()
        except Exception as e:
            log(f"Error: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
