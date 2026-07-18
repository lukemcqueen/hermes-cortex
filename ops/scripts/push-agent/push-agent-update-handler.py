#!/usr/bin/env python3
"""
push-agent-update-handler.py — Update handler for push-only agents (e.g. Titus).

Polls the agent inbox for UPDATE_REQUEST messages, processes them,
and sends UPDATE_RESULT back to the orchestrator.

Designed to run as a launchd plist (macOS) or systemd timer (Linux).
Silent when no work to do — watchdog pattern.

Usage:
    python3 push-agent-update-handler.py                  # single poll (cron/launchd)
    python3 push-agent-update-handler.py --once           # same
    python3 push-agent-update-handler.py --watch          # continuous poll every 5m

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


def send_bus_result(queue: str, correlation_id: str, result_body: dict) -> bool:
    """Send UPDATE_RESULT or FIX_RESULT back to orchestrator."""
    full_body = {
        "from": AGENT_NAME,
        "to": "moses",
        "topic": "fleet-update",
        "subject": "UPDATE_RESULT",
        "correlation_id": correlation_id,
        "body": result_body,
    }
    body_json = json.dumps(full_body).replace("'", "''")
    try:
        r = subprocess.run(
            ["docker", "exec", "gbrain-postgres", "psql", "-U", "gbrain", "-d", "gbrain",
             "-t", "-A", "-c",
             f"SELECT bus.send('{queue}', '{body_json}'::jsonb, 0)"],
            capture_output=True, text=True, timeout=15
        )
        ok = r.returncode == 0 and r.stdout.strip() and "ERROR" not in r.stdout
        if ok:
            log(f"Sent UPDATE_RESULT (corr={correlation_id[:8]}…)")
        else:
            log(f"Failed to send result: {r.stderr[:200]}")
        return ok
    except Exception as e:
        log(f"Error sending result: {e}")
        return False


def read_inbox(queue: str, vt: int = 30) -> dict | None:
    """Read one message from inbox."""
    try:
        r = subprocess.run(
            ["docker", "exec", "gbrain-postgres", "psql", "-U", "gbrain", "-d", "gbrain",
             "-t", "-A", "-c",
             f"SELECT bus.read('{queue}', {vt})"],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0 and r.stdout.strip():
            return json.loads(r.stdout.strip())
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

            # Archive the message
            try:
                subprocess.run(
                    ["docker", "exec", "gbrain-postgres", "psql", "-U", "gbrain",
                     "-d", "gbrain", "-t", "-A", "-c",
                     f"SELECT bus.archive('{inbox_queue}', '{msg.get('msg_id', '')}')"],
                    capture_output=True, text=True, timeout=15
                )
            except Exception:
                pass

            # Send result back
            send_bus_result("inbox_moses", correlation_id, result_body)

            # Track processed ID
            processed.add(correlation_id)
            state.setdefault("processed_ids", [])
            state["processed_ids"].append(correlation_id)
            state["processed_ids"] = state["processed_ids"][-50:]  # keep last 50
            state["last_result"] = result_body
            save_state(state)

            if result_body["success"]:
                log(f"✅ Update successful: {result_body['git_sha_before']} → {result_body['git_sha_after']}")
            else:
                log(f"❌ Update had issues: {len(result_body['errors'])} error(s)")
            return True

        elif subject == "FIX_REQUEST":
            # FIX_REQUEST handling can go here in future iterations
            log(f"Received FIX_REQUEST (corr={correlation_id[:8]}…) — not yet implemented")
            return False

        return False

    if args.watch:
        log(f"Starting watch mode (interval={args.interval}s)")
        while True:
            try:
                poll_once()
            except Exception as e:
                log(f"Error in poll cycle: {e}")
            time.sleep(args.interval)
    else:
        try:
            poll_once()
        except Exception as e:
            log(f"Error: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
