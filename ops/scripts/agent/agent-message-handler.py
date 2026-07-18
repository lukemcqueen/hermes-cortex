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
AGENT_NAME = os.environ.get("AGENT_NAME", HOME.name)

# State file to track processed correlation_ids for idempotency
STATE_DIR = HOME / ".hermes-cortex" / "state"
STATE_FILE = STATE_DIR / "push-agent-update-state.json"
STATE_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{AGENT_NAME}] {msg}")


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
    log("Running doctor...")
    try:
        r = subprocess.run(
            [sys.executable, str(DOCTOR_PATH), "--json"],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0 and r.stdout.strip():
            start = r.stdout.index("{")
            return json.loads(r.stdout[start:])
        return {"healthy": False, "summary": {"pass": 0, "warn": 0, "fail": 0}}
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
            log(f"Sent {subject} (corr={correlation_id[:8]}…)")
        else:
            log(f"Failed to send {subject}")
        return ok
    except Exception as e:
        log(f"Error sending {subject}: {e}")
        return False


def read_inbox(queue: str, vt: int = 30) -> dict | None:
    """Read one message from inbox."""
    try:
        from lib.cortex_bus import bus_read
        raw = bus_read(queue, vt)
        if raw and raw.get("msg_id"):
            return raw
    except Exception:
        pass
    return None


def process_update_request(msg_body: dict, correlation_id: str) -> dict:
    """Process an UPDATE_REQUEST and return UPDATE_RESULT body."""
    request = msg_body.get("body", {})
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
    request = msg_body.get("body", {})
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
    request = msg_body.get("body", {})
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


def archive_message(queue: str, msg_id: str):
    """Archive a processed message from the inbox."""
    if not msg_id:
        return
    from lib.cortex_bus import bus_archive
    bus_archive(queue, msg_id)


def report_health_change(doctor: dict, prev_doctor: dict) -> None:
    """Report health state change to Moses via bus."""
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
        result = bus_send("inbox_moses", full_body)
        if result:
            log(f"Health report sent: {level}")
    except Exception as e:
        log(f"Failed to send health report: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Push agent update handler")
    parser.add_argument("--once", action="store_true", help="Single poll (default)")
    parser.add_argument("--watch", action="store_true", help="Continuous poll every 5 minutes")
    parser.add_argument("--interval", type=int, default=300, help="Poll interval in seconds (default 300)")
    args = parser.parse_args()

    inbox_queue = f"inbox_{AGENT_NAME}"
    state = load_state()
    processed = set(state.get("processed_ids", []))

    def poll_once() -> bool:
        msg = read_inbox(inbox_queue)
        if not msg:
            return False

        body = msg.get("body", {})
        subject = body.get("subject", "")
        correlation_id = msg.get("correlation_id", "")

        # Idempotency check
        if correlation_id in processed:
            log(f"Skipping already-processed corr={correlation_id[:8]}…")
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
            else:
                log(f"❌ Update had issues: {len(result_body['errors'])} error(s)")
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

            log(f"{'✅' if result_body['authenticated'] else '❌'} Git auth: {result_body.get('remote_url', '?')}")
            return True

        elif subject == "FIX_REQUEST":
            log(f"Received FIX_REQUEST (corr={correlation_id[:8]}…) — not yet implemented")
            return False

        return False

    # Health state tracking (report on state change, not every tick)
    last_doctor = state.get("last_doctor", {})

    def poll_and_check() -> None:
        nonlocal last_doctor
        poll_once()
        # Run doctor on every tick regardless of message activity
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
