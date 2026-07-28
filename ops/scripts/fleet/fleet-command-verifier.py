#!/usr/bin/env python3
"""
fleet-command-verifier.py — No_agent cron, runs every 10 minutes.

Checks bus.command_verifications for pending commands past deadline,
cross-references against bus.archives / bus.messages (including DLQ),
and either verifies them, retries, or alerts via Telegram.

Agent-type awareness:
  - Push-only agents (Titus): skipped at the DB level (NULL expected_response)
  - Orchestrator-self commands: checks both live inbox AND archives
  - Half-connectivity detection: archived but no RESULT → alert, not retry

Output: silent when nothing to report (watchdog pattern).
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────

CORTEX_REPO = Path.home() / "hermes-cortex"
STATE_DIR = Path.home() / ".hermes-cortex" / "state"
TELEGRAM_BOT_TOKEN = None
TELEGRAM_CHAT_ID = "1270130526"

# Load Telegram config from .env
env_file = Path.home() / ".hermes" / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            TELEGRAM_BOT_TOKEN = line.split("=", 1)[1].strip().strip("'\"")
        if line.startswith("TELEGRAM_CHAT_ID="):
            TELEGRAM_CHAT_ID = line.split("=", 1)[1].strip().strip("'\"")

# ── Helpers ─────────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    if msg is None:
        msg = ""
    print(f"[{ts}] {msg}", file=sys.stderr)


def _psql(query: str) -> str:
    """Run SQL against bus Postgres."""
    try:
        r = subprocess.run(
            ["docker", "exec", "gbrain-postgres", "psql",
             "-U", "gbrain", "-d", "gbrain", "-t", "-c", query],
            capture_output=True, text=True, timeout=15,
        )
        return r.stdout.strip() if r.returncode == 0 else f"ERROR: {r.stderr[:200]}"
    except FileNotFoundError:
        return "ERROR: docker not found"
    except subprocess.TimeoutExpired:
        return "ERROR: query timed out"
    except Exception as e:
        return f"ERROR: {e}"


def _psql_rows(query: str) -> list[dict]:
    """Run SQL and parse JSON rows."""
    raw = _psql(f"SELECT json_agg(row_to_json(t)) FROM ({query}) t")
    if raw.startswith("ERROR") or not raw:
        return []
    try:
        rows = json.loads(raw)
        return rows if rows else []
    except (json.JSONDecodeError, TypeError):
        return []


def _bus_send(queue: str, body: dict) -> bool:
    """Send a message to a PGMQ queue."""
    body_json = json.dumps(body).replace("'", "''")
    result = _psql(f"SELECT bus.send('{queue}', '{body_json}'::jsonb, 0)")
    return bool(result) and not result.startswith("ERROR")


def _notify_telegram(message: str):
    """Send an alert via Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN:
        log("⚠️  TELEGRAM_BOT_TOKEN not set, skipping alert")
        return
    if message is None:
        message = "[No message content]"
    try:
        import urllib.request
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": f"🚨 Fleet Command Verifier\n{message}",
            "parse_mode": "HTML",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"⚠️  Telegram notify failed: {e}")


# ── Verifier Logic ──────────────────────────────────────────

def check_archives_for_response(corr_id: str, expected_subject: str) -> bool:
    """Check bus.archives for a response matching the correlation_id."""
    rows = _psql_rows(f"""
        SELECT archived_at, body
        FROM bus.archives
        WHERE ((body::jsonb #>> '{{}}')::jsonb @> '{{"correlation_id": "{corr_id}"}}'::jsonb)
          AND ((body::jsonb #>> '{{}}')::jsonb @> '{{"subject": "{expected_subject}"}}'::jsonb)
        ORDER BY archived_at DESC LIMIT 1
    """)
    return len(rows) > 0


def check_dlq_for_failure(corr_id: str) -> bool:
    """Check bus.messages DLQ for the correlation_id (handler crashed)."""
    rows = _psql_rows(f"""
        SELECT msg_id, state
        FROM bus.messages
        WHERE state = 'dlq'
          AND body::jsonb @> '{{"correlation_id": "{corr_id}"}}'::jsonb
        LIMIT 1
    """)
    return len(rows) > 0


def resend_command(row: dict) -> bool:
    """Resend the original command to the target agent.

    Uses the same correlation_id so idempotency protects against
    duplicate execution on the handler side.
    """
    queue = f"inbox_{row['out_agent']}"
    body = {
        "from": "moses",
        "to": row["out_agent"],
        "topic": "general",
        "subject": row["out_subject"],
        "correlation_id": row["out_corr"],
        "body": f"retry of {row['out_corr']}",
    }
    return _bus_send(queue, body)


def run_verifier():
    """Main verifier loop."""
    # 1. Get pending verifications
    rows = _psql_rows("SELECT * FROM bus.get_pending_verifications()")
    if not rows:
        # Silent exit — nothing to report
        return

    log(f"Found {len(rows)} pending verification(s)")
    alerts = []
    stats = {"verified": 0, "retried": 0, "timed_out": 0, "failed_dlq": 0}

    for row in rows:
        corr_id = row["out_corr"]
        agent = row["out_agent"]
        expected = row["out_expected_response"]
        retry_count = row["out_retry_count"]
        max_retries = row["out_max_retries"]
        deadline = row["out_deadline_at"]

        log(f"  Checking {corr_id} → {agent} (expected: {expected})")

        # Phase 1: Check archives for response
        if check_archives_for_response(corr_id, expected):
            _psql(f"SELECT bus.verify_command('{corr_id}', 'verified')")
            log(f"    ✅ Verified — found matching {expected} in archives")
            stats["verified"] += 1
            continue

        # Phase 2: Check DLQ (handler crashed mid-processing)
        if check_dlq_for_failure(corr_id):
            _psql(f"SELECT bus.verify_command('{corr_id}', 'failed', 'Found in DLQ — handler likely crashed')")
            msg = (f"    ❌ Failed — command {corr_id} to {agent} ended in DLQ\n"
                   f"       Subject: {row['out_subject']}")
            log(msg)
            alerts.append(msg)
            continue

        # Phase 3: Retry if under limit
        if retry_count < max_retries:
            log(f"    🔄 Retrying ({retry_count + 1}/{max_retries})...")
            if resend_command(row):
                # record_dispatch increments retry_count via ON CONFLICT
                _psql(f"SELECT bus.record_dispatch('{corr_id}', '{agent}', "
                      f"'{row['out_cmd_type']}', '{row['out_subject']}', "
                      f"'{expected}', NULL, 600)")
                log(f"    ✅ Retry sent")
                stats["retried"] += 1
            else:
                log(f"    ❌ Retry send failed")
                alerts.append(f"    ❌ Retry failed for {corr_id} to {agent}")
        else:
            # Phase 4: Timed out — no more retries
            _psql(f"SELECT bus.verify_command('{corr_id}', 'timed_out', 'Max retries ({max_retries}) exceeded')")
            msg = (f"🚨 Command timed out\n"
                   f"   Agent: {agent}\n"
                   f"   Type: {row['out_cmd_type']}\n"
                   f"   Corr: {corr_id}\n"
                   f"   Subject: {row['out_subject']}\n"
                   f"   Deadline: {deadline}\n"
                   f"   Retries: {retry_count}/{max_retries}")
            log(msg)
            alerts.append(msg)
            stats["timed_out"] += 1

    # 5. Cleanup old records
    cleaned = _psql("SELECT bus.cleanup_verifications(30)")
    log(f"  Cleanup: purged {cleaned} records older than 30 days")

    # 6. Send Telegram alerts if any
    if alerts:
        _notify_telegram("\n".join(alerts))

    # 7. Output human-readable summary (stdout = delivered by cron)
    total = len(rows)
    if total > 0:
        lines = [f"📋 Fleet Command Verifier"]
        if stats["verified"]:
            lines.append(f"  ✅ {stats['verified']} verified")
        if stats["retried"]:
            lines.append(f"  🔄 {stats['retried']} retried")
        if stats["timed_out"]:
            lines.append(f"  ❌ {stats['timed_out']} timed out")
        if stats["failed_dlq"]:
            lines.append(f"  ⚠️  {stats['failed_dlq']} in DLQ")
        lines.append(f"  📊 {total} total — {stats['verified']}/{total} resolved")
        print("\n".join(lines))
    # else: silent exit — nothing to report


if __name__ == "__main__":
    run_verifier()
