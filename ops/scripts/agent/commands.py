#!/usr/bin/env python3
"""
commands.py — Command registry for agent-message-handler.py.

Extensible decorator-based pattern. Add a new command:

    @command("MY_RESULT", "Does X and returns Y")
    def handle_my(msg_body: dict, msg_raw: dict) -> dict:
        ...
        return {"success": True, ...}

The registry auto-derives the subject as MY_REQUEST from the function name.
Use @register_custom for non-standard subject names.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# ── Paths ──
HOME = Path.home()
CORTEX_REPO = HOME / "hermes-cortex"
CORTEX_UPDATE = CORTEX_REPO / "ops" / "scripts" / "cortex-update.sh"
DOCTOR_PATH = CORTEX_REPO / "ops" / "scripts" / "manage" / "cortex-doctor.py"
SCRIPTS_DIR = HOME / ".hermes-cortex" / "scripts"
COLLECTOR_SCRIPT = SCRIPTS_DIR / "agent-learning-collector.py"
STATE_DIR = HOME / ".hermes-cortex" / "state"
def _agent_name() -> str:
    """Resolve agent identity from env → .env (cortex-bus.conf is a symlink
    to the consolidated .env; agent.env is the per-host identity file).
    Never falls back to whoami/hostname (Luke directive 2026-08-10): a
    missing identity is a hard error, not a guess."""
    for path in (
        HOME / ".hermes-cortex" / "agent.env",
        HOME / "hermes-cortex" / ".env",
        HOME / ".hermes-cortex" / "cortex-bus.conf",
    ):
        try:
            if path.is_file():
                for line in path.read_text().splitlines():
                    if line.startswith("AGENT_NAME="):
                        val = line.split("=", 1)[1].strip().strip("\"'")
                        if val:
                            return val
        except OSError:
            continue
    raise RuntimeError(
        "AGENT_NAME not configured — set AGENT_NAME= in "
        "~/.hermes-cortex/agent.env / cortex-bus.conf or export AGENT_NAME")


AGENT_NAME = os.environ.get("AGENT_NAME", "") or _agent_name()

# ── Registry ──
COMMANDS: dict[str, dict] = {}
"""{subject: {"result": str, "handler": callable, "description": str}}"""


def command(result_subject: str, description: str = "") -> Callable:
    """Decorator: register function as XXX_REQUEST → result_subject handler."""
    def decorator(fn: Callable) -> Callable:
        name = fn.__name__
        if name.startswith("handle_"):
            subject = name[len("handle_"):].upper() + "_REQUEST"
        else:
            subject = name.upper()
        COMMANDS[subject] = {"result": result_subject, "handler": fn, "description": description or subject}
        return fn
    return decorator


def register_custom(subject: str, result_subject: str, handler: Callable, description: str = "") -> None:
    """Register a command with an explicit subject (for non-standard names)."""
    COMMANDS[subject] = {"result": result_subject, "handler": handler, "description": description or subject}


def dispatch(subject: str, msg_body: dict, msg_raw: dict) -> dict | None:
    """Dispatch to handler. Returns result dict or None if unknown."""
    cmd = COMMANDS.get(subject)
    if cmd:
        try:
            return cmd["handler"](msg_body, msg_raw)
        except Exception as e:
            return {
                "success": False,
                "command": subject,
                "error": f"Handler crashed: {type(e).__name__}: {e}",
            }
    return None


# ── Shared Utilities ──

def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{AGENT_NAME}] {msg}", flush=True)


def _parse_body(body_field: Any) -> dict:
    if isinstance(body_field, str):
        try:
            return json.loads(body_field)
        except (json.JSONDecodeError, TypeError):
            return {}
    return body_field if isinstance(body_field, dict) else {}


def send_bus_result(queue: str, correlation_id: str, result_body: dict, subject: str) -> bool:
    """Send result back to orchestrator via bus."""
    full = {
        "from": AGENT_NAME, "to": "moses", "topic": "fleet-update",
        "subject": subject, "correlation_id": correlation_id, "body": result_body,
    }
    try:
        from lib.cortex_bus import bus_send
        result = bus_send(queue, full)
        ok = result is not None
        if ok:
            mid = (result.get("msg_id", "?") or "?")[:8] if isinstance(result, dict) else "?"
            log(f"Sent {subject} (mid={mid}… corr={str(correlation_id)[:8]}…)")
        else:
            log(f"Failed to send {subject}")
        return ok
    except Exception as e:
        log(f"Error sending {subject}: {e}")
        return False


def _run(cmd: list[str], timeout: int = 60) -> dict:
    """Run subprocess, return standardized result."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {
            "success": r.returncode == 0,
            "stdout": (r.stdout or ""),
            "stderr": (r.stderr or ""),
            "exit_code": r.returncode,
        }
    except subprocess.TimeoutExpired:
        log(f"TIMEOUT after {timeout}s: {' '.join(str(c) for c in cmd[:2])}")
        return {"success": False, "stdout": "", "stderr": f"TIMEOUT after {timeout}s", "exit_code": -1}
    except Exception as e:
        log(f"ERROR: {e}")
        return {"success": False, "stdout": "", "stderr": str(e), "exit_code": -1}


def _run_doctor() -> dict:
    result = _run([sys.executable, str(DOCTOR_PATH), "--json"], timeout=30)
    if result["stdout"].strip():
        try:
            start = result["stdout"].index("{")
            return json.loads(result["stdout"][start:])
        except (ValueError, json.JSONDecodeError):
            log("Doctor JSON output parse failed — falling through to defaults")
    return {"healthy": False, "summary": {"pass": 0, "warn": 0, "fail": 0}, "error": "no JSON"}


def _git_sha(path: Path) -> str:
    r = _run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"], timeout=5)
    return r["stdout"].strip() if r["success"] else "unknown"


def _run_cortex_update() -> dict:
    """Run git pull then cortex-update.sh, return result dict."""
    log("Pulling latest code ...")
    try:
        pull = subprocess.run(
            ["git", "-C", str(CORTEX_REPO), "pull", "origin", "main"],
            capture_output=True, text=True, timeout=60
        )
        if pull.returncode != 0:
            log(f"git pull had issues: {pull.stderr[:200]}")
        else:
            tail = (pull.stdout or "")[-200:].replace("\n", " ").strip()
            if tail:
                log(f"  {tail}")
    except subprocess.TimeoutExpired:
        log("git pull TIMEOUT after 60s")
    except Exception as e:
        log(f"git pull ERROR: {e}")

    log("Running cortex-update.sh ...")
    try:
        r = subprocess.run(
            ["bash", str(CORTEX_UPDATE)],
            # 300s — matches the UPDATE_REQUEST handler bound (agent-message-handler.py
            # run_cortex_update). 120s was too tight for a full pull+deploy+doctor on
            # slower hosts: titus fleet-update TIMED OUT after 120s (2026-08-11) with
            # the tree moved but deploy never completing. (auto-remediation fix)
            capture_output=True, text=True, timeout=300
        )
        result = {
            "success": r.returncode == 0 or (r.returncode == 1 and not r.stderr),
            "output": (r.stdout or "")[-2000:],
            "stderr": (r.stderr or "")[-500:],
            "exit_code": r.returncode,
        }
        tail = ((r.stdout or "")[-200:]).replace("\n", " ").strip()
        log(f"cortex-update done: exit={r.returncode} {'✓' if result['success'] else '✗'}")
        if tail:
            log(f"  {tail}")
        return result
    except subprocess.TimeoutExpired:
        log("cortex-update TIMEOUT after 300s")
        return {"success": False, "output": "", "stderr": "TIMEOUT after 300s", "exit_code": -1}
    except Exception as e:
        log(f"cortex-update ERROR: {e}")
        return {"success": False, "output": "", "stderr": str(e), "exit_code": -1}


# ═══════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════


# ── UPDATE_REQUEST → UPDATE_RESULT ──

@command("UPDATE_RESULT", "Run cortex-update.sh and doctor, report result")
def handle_update(msg_body: dict, msg_raw: dict) -> dict:
    request = _parse_body(msg_body.get("body", {}))
    correlation_id = (msg_raw.get("correlation_id") or "") if isinstance(msg_raw, dict) else ""
    target_sha = request.get("target_sha", "unknown")
    target_version = request.get("target_version", "")
    run_doctor_flag = request.get("run_doctor", True)

    log(f"Processing UPDATE_REQUEST: SHA={target_sha}")

    before = _git_sha(CORTEX_REPO)

    update_result = _run_cortex_update()
    if not update_result["success"]:
        log("First attempt failed, retrying once...")
        update_result = _run_cortex_update()

    after = _git_sha(CORTEX_REPO)
    doctor = _run_doctor() if run_doctor_flag else {}
    doctor_fail = doctor.get("summary", {}).get("fail", 0) if doctor else 0

    result = {
        "success": update_result["success"] and doctor_fail == 0,
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


# ── ROLLBACK_REQUEST → ROLLBACK_RESULT ──

@command("ROLLBACK_RESULT", "Git checkout to previous SHA and verify")
def handle_rollback(msg_body: dict, msg_raw: dict) -> dict:
    request = _parse_body(msg_body.get("body", {}))
    target_sha = request.get("target_sha", "HEAD~1")
    reason = request.get("reason", "No reason given")

    log(f"Processing ROLLBACK_REQUEST: → {target_sha[:12]} ({reason})")
    before = _git_sha(CORTEX_REPO)

    checkout = _run(["git", "-C", str(CORTEX_REPO), "checkout", target_sha], timeout=30)
    checkout_ok = checkout["success"]
    after = _git_sha(CORTEX_REPO)
    doctor = _run_doctor()

    return {
        "success": checkout_ok and doctor.get("healthy", False),
        "sha_before": before,
        "sha_after": after,
        "reverted": checkout_ok,
        "doctor": doctor,
        "duration_seconds": 0,
        "errors": [] if checkout_ok else ["git checkout failed"],
    }


# ── GIT_AUTH_CHECK → GIT_AUTH_RESULT ──

@command("GIT_AUTH_RESULT", "Verify git can ls-remote origin")
def handle_git_auth(msg_body: dict, msg_raw: dict) -> dict:
    request = _parse_body(msg_body.get("body", {}))
    expected_url = request.get("expected_url", "")
    checks = []

    # git installed
    r = _run(["git", "version"], timeout=5)
    checks.append({"name": "git installed", "pass": r["success"], "detail": r["stdout"].strip()})
    if not r["success"]:
        return {"authenticated": False, "remote_url": "", "error": "git not found", "checks": checks}

    # remote URL
    r = _run(["git", "-C", str(CORTEX_REPO), "remote", "get-url", "origin"], timeout=5)
    remote_url = r["stdout"].strip() if r["success"] else ""
    checks.append({"name": "remote URL", "pass": expected_url in remote_url, "detail": remote_url})

    # ls-remote
    r = _run(["git", "-C", str(CORTEX_REPO), "ls-remote", "origin", "HEAD"], timeout=15)
    auth_ok = r["success"] and r["stdout"].strip() != ""
    checks.append({"name": "ls-remote", "pass": auth_ok, "detail": r["stdout"].strip()[:40] if auth_ok else r["stderr"][:200]})

    return {
        "success": all(c["pass"] for c in checks),
        "authenticated": all(c["pass"] for c in checks),
        "remote_url": remote_url if remote_url else "unknown",
        "error": "",
        "checks": checks,
    }


# ── EXEC → EXEC_RESULT ──

@command("EXEC_RESULT", "Run a script under ~/.hermes-cortex/scripts/")
def handle_exec(msg_body: dict, msg_raw: dict) -> dict:
    request = _parse_body(msg_body.get("body", {}))
    command = (request.get("command") or "").strip()
    params = request.get("params") or []
    timeout = int(request.get("timeout", 60))

    if not command:
        return {"success": False, "stdout": "", "stderr": "No command specified", "exit_code": -1, "command": ""}

    script_path = SCRIPTS_DIR / command
    if not script_path.exists():
        abs_path = Path(command)
        if abs_path.exists() and abs_path.is_file():
            script_path = abs_path
        else:
            return {"success": False, "stdout": "", "stderr": f"Script not found: {command}",
                    "exit_code": -1, "command": command}

    log(f"Executing: {script_path} {' '.join(str(p) for p in params)}")

    cmd_parts = [sys.executable, str(script_path)] if script_path.suffix in (".py",) else \
                ["bash", str(script_path)] if script_path.suffix in (".sh", ".bash") else \
                [str(script_path)]
    cmd_parts.extend(str(p) for p in params)

    result = _run(cmd_parts, timeout=timeout)
    result["command"] = command
    return result


# ── FIX_REQUEST → FIX_RESULT ──

@command("FIX_RESULT", "Run pre-defined repair for common issues")
def handle_fix(msg_body: dict, msg_raw: dict) -> dict:
    request = _parse_body(msg_body.get("body", {}))
    fix_type = request.get("fix_type", "").strip()
    params = request.get("params", {})

    fixes = {
        "reinstall-crons": {
            "description": "Reinstall cron definitions from install-crons.sh",
            "run": lambda: _run(["bash", str(CORTEX_REPO / "ops" / "scripts" / "install-crons.sh")], timeout=30),
        },
        "reset-collector-state": {
            "description": "Delete collector state file to force fresh collection",
            "run": lambda: _reset_state_file("agent-learning-collector-state.json"),
        },
        "reset-session-mine-state": {
            "description": "Delete session-mine state to force re-bootstrap",
            "run": lambda: _reset_state_file("agent-session-mine-state.json"),
        },
        "clear-bus-state": {
            "description": "Clear agent-message-handler processed_ids",
            "run": lambda: _reset_state_file("agent-message-state.json"),
        },
        "doctor": {
            "description": "Run doctor and return structured result",
            "run": lambda: _run_doctor(),
        },
    }

    if not fix_type:
        return {
            "success": False,
            "error": "No fix_type specified",
            "available_fixes": {k: v["description"] for k, v in fixes.items()},
        }

    fix = fixes.get(fix_type)
    if not fix:
        return {
            "success": False,
            "error": f"Unknown fix_type: {fix_type}",
            "available_fixes": {k: v["description"] for k, v in fixes.items()},
        }

    log(f"Running fix: {fix_type} — {fix['description']}")
    result = fix["run"]()
    return {
        "success": result.get("success", True),
        "fix_type": fix_type,
        "description": fix["description"],
        "result": result,
    }


def _reset_state_file(name: str) -> dict:
    path = STATE_DIR / name
    if path.exists():
        try:
            path.unlink()
            log(f"Deleted {name}")
            return {"success": True, "detail": f"Deleted {name}"}
        except OSError as e:
            return {"success": False, "detail": str(e)}
    return {"success": True, "detail": f"{name} did not exist"}


# ── DIAGNOSTIC_REQUEST → DIAGNOSTIC_RESULT ──

@command("DIAGNOSTIC_RESULT", "Run agent-diagnostic.py and return results")
def handle_diagnostic(msg_body: dict, msg_raw: dict) -> dict:
    request = _parse_body(msg_body.get("body", {}))
    check = request.get("check", "")
    respond_to = request.get("respond_to_queue", "inbox_moses")

    log(f"DIAGNOSTIC_REQUEST from {msg_body.get('from', '?')}: check={check or 'all'}")

    script = CORTEX_REPO / "ops" / "scripts" / "agent" / "agent-diagnostic.py"
    cmd = [sys.executable, str(script)]
    if check:
        cmd += ["--check", check]

    result = _run(cmd, timeout=15)
    if result["success"] and result["stdout"].strip():
        try:
            parsed = json.loads(result["stdout"])
            if isinstance(parsed, dict):
                parsed.setdefault("success", True)
            return parsed
        except json.JSONDecodeError:
            log(f"Diagnostic JSON parse failed — output was not JSON")
    return {"error": result["stderr"][:200] or "No output"}


# ── LEARNINGS_REQUEST → LEARNINGS_RESULT ──

@command("LEARNINGS_RESULT", "Run learning collector and report lesson/skill count")
def handle_learnings(msg_body: dict, msg_raw: dict) -> dict:
    request = _parse_body(msg_body.get("body", {}))
    force = request.get("force", True)  # default to force
    dry_run = request.get("dry_run", False)

    if not COLLECTOR_SCRIPT.exists():
        return {"success": False, "error": f"Collector not found at {COLLECTOR_SCRIPT}", "lessons": 0, "skills": 0}

    cmd = [sys.executable, str(COLLECTOR_SCRIPT)]
    if force:
        cmd.append("--force")
    if dry_run:
        cmd.append("--dry-run")

    log(f"Running learning collector {'(force)' if force else ''}")
    result = _run(cmd, timeout=30)

    # Parse output for lesson/skill counts
    stdout = result.get("stdout", "")
    lessons = 0
    skills = 0
    for line in stdout.split("\n"):
        if "lessons" in line.lower():
            import re
            m = re.search(r"(\d+)\s+lessons?", line, re.IGNORECASE)
            if m:
                lessons = int(m.group(1))
        if "skills" in line.lower():
            import re
            m = re.search(r"(\d+)\s+skills?", line, re.IGNORECASE)
            if m:
                skills = int(m.group(1))

    return {
        "success": result["success"],
        "lessons": lessons,
        "skills": skills,
        "stdout": stdout[:500],
        "stderr": result.get("stderr", "")[:200],
        "exit_code": result["exit_code"],
    }


# ── STATUS_REQUEST → STATUS_RESULT ──

@command("STATUS_RESULT", "Return git SHA, doctor summary, disk, uptime, crons")
def handle_status(msg_body: dict, msg_raw: dict) -> dict:
    request = _parse_body(msg_body.get("body", {}))
    include_detail = request.get("detail", False)

    result = {
        "agent": AGENT_NAME,
        "hostname": os.uname().nodename,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Git status
    result["git"] = {
        "sha": _git_sha(CORTEX_REPO),
        "clean": _run(["git", "-C", str(CORTEX_REPO), "status", "--porcelain"], timeout=5)["stdout"].strip() == "",
    }

    # Doctor summary
    doctor = _run_doctor()
    result["doctor"] = {
        "healthy": doctor.get("healthy", False),
        "pass": doctor.get("summary", {}).get("pass", 0),
        "warn": doctor.get("summary", {}).get("warn", 0),
        "fail": doctor.get("summary", {}).get("fail", 0),
    }

    # Disk
    try:
        df = subprocess.run(["df", "-h", "--output=pcent,target"], capture_output=True, text=True, timeout=5)
        lines = df.stdout.strip().split("\n")[1:] if df.returncode == 0 else []
        high = [l.strip() for l in lines if any(c.isdigit() for c in l.split()[0]) and
                int(l.split()[0].replace("%", "")) > 85]
        result["disk"] = {"high_usage": high[:5] if include_detail else len(high)}
    except Exception:
        result["disk"] = {"high_usage": "unknown"}

    # Uptime
    try:
        uptime = subprocess.run(["uptime", "-p"], capture_output=True, text=True, timeout=5)
        result["uptime"] = uptime.stdout.strip() if uptime.returncode == 0 else "unknown"
    except Exception:
        result["uptime"] = "unknown"

    # Load
    try:
        load = subprocess.run(["cat", "/proc/loadavg"], capture_output=True, text=True, timeout=5)
        result["load"] = load.stdout.strip().split()[:3] if load.returncode == 0 else "unknown"
    except Exception:
        result["load"] = "unknown"

    # Memory
    try:
        mem = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
        if mem.returncode == 0:
            lines = mem.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 3:
                    result["memory"] = f"{parts[2]}M used / {parts[1]}M total"
    except Exception:
        log("free -m not available (expected on macOS)")

    # Cron health (list crons via Hermes CLI)
    try:
        cron_r = subprocess.run(["hermes", "cron", "list", "--json"],
                                 capture_output=True, text=True, timeout=10)
        if cron_r.returncode == 0 and cron_r.stdout.strip():
            try:
                crons = json.loads(cron_r.stdout)
                total = len(crons) if isinstance(crons, list) else 0
                failed = sum(1 for c in (crons if isinstance(crons, list) else [])
                             if c.get("last_status") in ("failed", "error", "timeout"))
                result["crons"] = {"total": total, "failed": failed}
            except json.JSONDecodeError:
                result["crons"] = {"total": "parse_error", "failed": 0}
    except Exception:
        result["crons"] = {"total": "unknown", "failed": 0}

    return result


# ── DOCTOR_REQUEST → DOCTOR_RESULT ──

@command("DOCTOR_RESULT", "Run cortex-doctor.py and return structured pass/warn/fail")
def handle_doctor(msg_body: dict, msg_raw: dict) -> dict:
    request = _parse_body(msg_body.get("body", {}))
    quiet = request.get("quiet", False)

    log("Running doctor...")
    doctor = _run_doctor()
    output = ""

    if not quiet:
        r = _run([sys.executable, str(DOCTOR_PATH), "--quiet"], timeout=30)
        output = r.get("stdout", "")[-2000:]

    return {
        "success": doctor.get("healthy", False),
        "healthy": doctor.get("healthy", False),
        "version": doctor.get("version", ""),
        "summary": doctor.get("summary", {"pass": 0, "warn": 0, "fail": 0}),
        "checks": doctor.get("checks", [])[:20],
        "output": output,
    }


# ── REBOOT_REQUEST → REBOOT_RESULT ──

@command("REBOOT_RESULT", "Restart agent systemd services (requires confirmation)")
def handle_reboot(msg_body: dict, msg_raw: dict) -> dict:
    request = _parse_body(msg_body.get("body", {}))
    confirm = request.get("confirm", False)
    service = request.get("service", "")  # empty = all

    if not confirm:
        return {
            "success": False,
            "error": "Confirmation required. Set confirm=true to proceed.",
            "message": f"Will restart{' ' + service if service else ' all agent services'}",
            "available_services": ["cortex-bus", "hermes-gateway"],
        }

    services = [service] if service else ["cortex-bus", "hermes-gateway"]
    results = []

    for svc in services:
        log(f"Restarting {svc}...")
        r = _run(["systemctl", "--user", "restart", svc], timeout=30)
        results.append({
            "service": svc,
            "success": r["success"],
            "detail": r["stderr"][:200] if not r["success"] else "restarted",
        })

    # Verify
    for res in results:
        if res["success"]:
            r = _run(["systemctl", "--user", "is-active", res["service"]], timeout=5)
            res["active"] = r["stdout"].strip() == "active"

    return {
        "success": all(r["success"] for r in results),
        "services": results,
        "note": "Systemd --user restart — affects only this user's services",
    }


# ── TASK_REQUEST: accept free-text task requests from other agents ──
# Subject format: "Task: <description>" or "TASK_REQUEST"
# Body format: {"body": {"task": "<description>"}} or plain text
def handle_task(msg_body: dict, msg_raw: dict) -> dict:
    request = _parse_body(msg_body.get("body", {}))
    task_desc = request.get("task", "") or request.get("body", msg_body.get("body", ""))
    if isinstance(task_desc, dict):
        task_desc = str(task_desc)
    task_desc = str(task_desc).strip()

    sender = msg_raw.get("from", "?") if isinstance(msg_raw, dict) else "?"
    log(f"📋 TASK_REQUEST from {sender}: {task_desc[:200]}")

    return {
        "success": True,
        "command": "TASK_REQUEST",
        "task": task_desc[:500],
        "sender": sender,
        "message": f"Task received from {sender}. Luke has been notified.",
        "forwarded_to": "luke",
    }


# ── Register non-standard subjects that don't follow XXX_REQUEST naming ──

register_custom("DIAGNOSTIC_REQUEST", "DIAGNOSTIC_RESULT", handle_diagnostic,
                "Run agent-diagnostic.py and return results")

# Bus message subjects that don't match the XXX_REQUEST naming convention
register_custom("EXEC", "EXEC_RESULT", handle_exec,
                "Run a script under ~/.hermes-cortex/scripts/")
register_custom("GIT_AUTH_CHECK", "GIT_AUTH_RESULT", handle_git_auth,
                "Verify git can ls-remote origin")
register_custom("TASK_REQUEST", "TASK_RESULT", handle_task,
                "Accept free-text task requests from other agents (Gisu, Joseph, etc.)")
