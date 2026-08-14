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
  CORTEX_BUS_URL   Bus server URL (default http://127.0.0.1:8903)
            On remote agents, set to e.g. https://your-domain:13004
  CORTEX_BUS_TOKEN  Bearer token for bus auth
  CORTEX_BUS_AUTH  Basic auth string (user:pass) as fallback
  AGENT_NAME     Agent identity (required; never hostname)

Usage:
  python3 agent-message-handler.py         # single poll (cron)
  python3 agent-message-handler.py --once      # same
  python3 agent-message-handler.py --watch     # continuous poll every 5m

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
# Derive AGENT_NAME from env (set by cron/launchd) or cortex-bus.conf (fleet setup)
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
  print(f"❌ AGENT_NAME not configured. Set AGENT_NAME= in ~/.hermes-cortex/cortex-bus.conf or export AGENT_NAME.", flush=True)
  sys.exit(1)
# Export for child modules (commands.py dispatch etc.) — identity is explicit,
# never hostname-derived (Luke directive 2026-08-10).
os.environ["AGENT_NAME"] = AGENT_NAME
# Ensure lib.cortex_bus is importable
from hermes_paths import ensure_scripts_path
ensure_scripts_path()

# State file to track processed correlation_ids for idempotency
STATE_DIR = HOME / ".hermes-cortex" / "state"
STATE_FILE = STATE_DIR / "agent-message-state.json"
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Agent labels file (created by cortex-agent-manager.py or manually)
LABELS_FILE = HOME / ".hermes-cortex" / "agent-labels.json"


def _load_agent_labels() -> dict:
    """Load agent metadata labels from local file. Returns dict or {}."""
    if LABELS_FILE.exists():
        try:
            raw = LABELS_FILE.read_text().strip()
            if raw:
                return json.loads(raw)
        except (json.JSONDecodeError, OSError):
            pass  # expected — silently handled
    return {}


def _should_process(body: dict, labels: dict) -> tuple[bool, str]:
    """Check if this message should be processed by this agent.
    
    Returns (should_process: bool, reason: str).
    If target_labels or target_agents is present, only matching agents process.
    If neither is present, all agents process (backward compatible).
    """
    target_agents = body.get("target_agents")
    target_labels = body.get("target_labels", {})
    
    # If nothing specified, all agents process (backward compatible)
    if not target_agents and not target_labels:
        return True, ""
    
    # Check exact agent name match
    if target_agents and AGENT_NAME in target_agents:
        return True, "agent_name_match"
    
    # Check label match (ALL must match — AND logic)
    if target_labels:
        for key, value in target_labels.items():
            if labels.get(key) != value:
                return False, f"label_mismatch: {key}={labels.get(key, '<missing>')} != {value}"
        return True, "label_match"
    
    return False, "no_match"


def log(msg: str):
  ts = datetime.now().strftime("%H:%M:%S")
  print(f"[{ts}] [{AGENT_NAME}] {msg}")


def notify_telegram(message: str, subject: str = ""):
  """Send a notification to Telegram via the shared lib/telegram_notify.

  Recipient comes from TELEGRAM_HOME_CHANNEL in ~/.hermes/.env — the
  canonical Hermes env var (never hardcoded; public-repo PII scrub
  2026-08-06). The shared module handles token read, PII scrub, HTML
  escaping, flock coalescing (<=1 msg/2s), 429 Retry-After backoff, and
  a persisted failure counter (docs/design/task-lifecycle-v2.md §8).
  Non-fatal: a notify failure never breaks message processing.
  """
  try:
    from lib.telegram_notify import notify
    notify(message, subject=subject)
  except Exception as e:
    log(f"Telegram notify failed: {type(e).__name__}: {e}")


# ── Bus → tasks bridge (TL-v2 S4) ─────────────────────────────
# Commands that create a tasks.tasks row (source='inbox') on receipt,
# link it to the bus message by correlation_id, and drive its lifecycle:
#   created(pending) on receipt → in_progress at dispatch → completed at
#   Result-receipt (EXEC_RESULT/UPDATE_RESULT handler path).
# Deny-by-default (Security R-8): anything not in this set creates NO row
# and NO notify. The `Task:`/`TASK:` prefix form normalizes to TASK_REQUEST
# before this check (poll_once does that).
TASK_CREATING_SUBJECTS = ("EXEC", "UPDATE_REQUEST", "TASK_REQUEST",
                          "PROPOSAL", "ISSUES", "IMPROVEMENTS")

# Deployed task-db.py path (repo path used when developing/deploying).
TASK_DB_PATH = HOME / ".hermes-cortex" / "scripts" / "task-db.py"
if not TASK_DB_PATH.exists():
    TASK_DB_PATH = CORTEX_REPO / "ops" / "scripts" / "manage" / "task-db.py"


def _taskdb(args: list[str], timeout: int = 20) -> tuple[int, str]:
    """Run task-db.py; return (returncode, stdout). Never raises."""
    try:
        r = subprocess.run([sys.executable, str(TASK_DB_PATH)] + args,
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        log(f"task-db failed: {type(e).__name__}: {e}")
        return -1, str(e)


def task_create_from_message(subject: str, correlation_id: str,
                             content: str) -> str | None:
    """Create a source='inbox' task row for a tracked subject (S4).

    Create-before-archive (SRE R-12): callers invoke this BEFORE archiving
    the message so a crash between leaves the row — the stale sweep is the
    safety net. Returns the task id, or None when the subject is not in the
    allowlist / no correlation_id / task-db unavailable (never raises).
    """
    if subject not in TASK_CREATING_SUBJECTS:
        return None
    if not correlation_id:
        log(f"task-create skipped: {subject} without correlation_id")
        return None
    # Scrub + cap content (R-4): bus content is untrusted — never store raw.
    try:
        from lib.telegram_notify import scrub_text
        safe = scrub_text(content or "")[:500]
    except Exception:
        safe = (content or "")[:500]
    rc, out = _taskdb(["add", safe or subject,
                       "--source", "inbox",
                       "--correlation-id", correlation_id])
    if rc == 0 and "added" in out.lower():
        # task-db prints: ✅ Task added: <8chars>... — extract nothing;
        # the correlation unique index means we can always look it up later.
        # Entry notify fires from task-db.py (R-14: replaces the handler's
        # pickup notify for tracked subjects — one EXEC = 1 entry message).
        log(f"🗂  task row created for {subject} (corr={correlation_id[:12]}…)")
        return correlation_id
    log(f"task-create failed for {subject}: rc={rc} {out[:120]}")
    return None


def _lookup_task_id(correlation_id: str) -> str | None:
    """Resolve the inbox task id for a bus correlation_id (S5, R-19)."""
    if not correlation_id:
        return None
    try:
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("task_db_lookup", TASK_DB_PATH)
        if spec is None or spec.loader is None:
            return None
        tdb = _ilu.module_from_spec(spec)
        spec.loader.exec_module(tdb)
        raw = tdb.psql(
            "SELECT id FROM tasks.tasks WHERE source = 'inbox' "
            "AND correlation_id = ? LIMIT 1;", [correlation_id])
        return raw.split("\n")[0] if raw.strip() else None
    except Exception as e:
        log(f"task id lookup failed: {type(e).__name__}: {e}")
        return None


def task_transition_by_correlation(correlation_id: str, status: str,
                                   reason: str | None = None) -> bool:
    """Transition the inbox task linked to a bus correlation_id (S4).

    completed at Result-receipt: the handler path that receives
    EXEC_RESULT/UPDATE_RESULT calls this to close the task. Never raises.
    """
    if not correlation_id:
        return False
    args = ["update", "--by-correlation", correlation_id,
            "--status", status]
    if reason:
        args += ["--reason", reason]
    # in_progress is transient churn — muted by default (R-14/R-20: the
    # meaningful events are entry and completed; per-status mute registry
    # can lift this via TASKS_NOTIFY_MUTE).
    if status == "in_progress":
        args += ["--no-notify"]
    rc, out = _taskdb(args)
    if rc == 0:
        log(f"🗂  task → {status} (corr={correlation_id[:12]}…)")
        return True
    log(f"task-transition {status} failed (corr={correlation_id[:12]}…): "
        f"rc={rc} {out[:120]}")
    return False


def task_stale_sweep(max_hours: float = 1.0) -> int:
    """Pause inbox tasks stuck in_progress beyond the threshold (S4).

    Runs on the handler tick. Bus tasks (source='inbox') older than
    max_hours in in_progress → paused with reason='stale' (R-16/M-2).
    Also completes pending inbox rows older than max_hours whose
    correlation_id is in the handler's processed_ids — the handler
    demonstrably processed the message (create-before-archive, corr in
    processed_ids) but the in_progress/completed transitions were lost
    (silent task-db failure or crash between create and dispatch),
    orphaning the row in pending forever (gisu PROPOSAL 2026-08-13;
    evidence: esther UPDATE_REQUEST corr=send-d13bfa25deab stayed
    pending 10.5h with update applied). The schema forbids a direct
    pending→completed, so the row goes pending→in_progress→completed
    (both legal). Report-type rows (PROPOSAL/ISSUES/IMPROVEMENTS) are
    EXCLUDED — those legitimately stay pending as the durable record
    for the orchestrator's inbox_read session. Returns the count
    swept. Never raises.
    """
    try:
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("task_db_bridge", TASK_DB_PATH)
        if spec is None or spec.loader is None:
            return 0
        tdb = _ilu.module_from_spec(spec)
        spec.loader.exec_module(tdb)
        swept = 0

        # Arm 1 (existing): in_progress older than threshold → paused
        sql = (
            "SELECT correlation_id FROM tasks.tasks "
            "WHERE source = 'inbox' AND status = 'in_progress' "
            "AND status_changed_at < now() - make_interval(hours => ?::int) "
            "LIMIT 50;"
        )
        raw = tdb.psql(tdb.build_query(sql, [max_hours]))
        corrs = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        for corr in corrs:
            if task_transition_by_correlation(corr, "paused", reason="stale"):
                swept += 1

        # Arm 2 (gisu PROPOSAL 2026-08-13): pending rows whose corr the
        # handler demonstrably processed but whose lifecycle transitions
        # were lost. Report-type rows stay pending on purpose — exclude.
        _state = load_state()
        _processed = set(_state.get("processed_ids", []))
        if _processed:
            sql2 = (
                "SELECT correlation_id FROM tasks.tasks "
                "WHERE source = 'inbox' AND status = 'pending' "
                "AND content NOT LIKE 'PROPOSAL%' "
                "AND content NOT LIKE 'ISSUES%' "
                "AND content NOT LIKE 'IMPROVEMENTS%' "
                "AND created_at < now() - make_interval(hours => ?::int) "
                "LIMIT 50;"
            )
            raw2 = tdb.psql(tdb.build_query(sql2, [max_hours]))
            for corr in (ln.strip() for ln in raw2.splitlines() if ln.strip()):
                if corr in _processed:
                    # pending→in_progress→completed: both legal; direct
                    # pending→completed is forbidden by the schema.
                    if task_transition_by_correlation(corr, "in_progress",
                                                      reason="stale-pending"):
                        if task_transition_by_correlation(corr, "completed",
                                                          reason="stale-pending"):
                            swept += 1
        if swept:
            log(f"🧹 stale sweep: closed {swept} inbox task(s) "
                f"(> {max_hours}h)")
        return swept
    except Exception as e:
        log(f"stale sweep error: {type(e).__name__}: {e}")
        return 0


def load_state() -> dict:
  if STATE_FILE.exists():
    try:
      return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
      pass # config read failure — non-fatal
  return {"processed_ids": [], "last_result": None}


def save_state(state: dict):
  STATE_FILE.write_text(json.dumps(state, indent=2))


def run_cortex_update() -> dict:
  """Run git pull then cortex-update.sh, capture output."""
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
      capture_output=True, text=True, timeout=300
    )
    result = {
      # exit=1 is a soft failure (cortex-update.sh uses set -euo pipefail
      # and needs_update returns 1 for unchanged files). Treat as success
      # when no stderr output indicates a real error.
      "success": r.returncode == 0 or (r.returncode == 1 and not r.stderr),
      "output": r.stdout[-2000:] if r.stdout else "",
      "stderr": r.stderr[-500:] if r.stderr else "",
      "exit_code": r.returncode,
    }
    # Log result for diagnostics
    stdout_tail = (r.stdout or "")[-200:].replace("\n", " ").strip()
    stderr_tail = (r.stderr or "")[-200:].replace("\n", " ").strip()
    log(f"cortex-update done: exit={r.returncode} {'✓' if result['success'] else '✗'}")
    if stdout_tail:
      log(f" stdout: {stdout_tail}")
    if stderr_tail:
      log(f" stderr: {stderr_tail}")
    return result
  except subprocess.TimeoutExpired:
    log("cortex-update TIMEOUT after 300s")
    return {"success": False, "output": "", "stderr": "TIMEOUT after 300s", "exit_code": -1}
  except Exception as e:
    log(f"cortex-update ERROR: {e}")
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
        pass # body parse failure — non-fatal
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
    # VT only needs to cover the read→archive window — the handler archives
    # the message immediately after reading (early archive, c7231c3), so VT
    # expiry can never re-expose a message mid-processing. The subprocess
    # timeout in run_cortex_update() (300s) is what bounds cortex-update
    # duration, not this VT.
    raw = bus_read(queue, vt=120)
    if raw and raw.get("msg_id"):
      # Normalize None fields that could cause subscript crashes downstream
      if raw.get("correlation_id") is None:
        raw["correlation_id"] = ""
      return raw
  except Exception:
    print("expected — silently handled", file=sys.stderr)
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
  # Use fail_count == 0 as the success metric (not doctor['healthy']
  # which also warns on `warn_count > 0`). Warnings like "behind
  # origin/main" or "uncommitted changes" are normal operational
  # states that shouldn't cause an UPDATE_RESULT to report failure.
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
    command: str  — relative path under ~/.hermes-cortex/scripts/
    params: list  — optional arguments to pass
    timeout: int  — max seconds (default 60)

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
    log(f"⚠️ Health degraded: {summary.get('fail', 0)} fail, {summary.get('warn', 0)} warn")
  elif healthy and not prev_healthy:
    level = "HEALTHY_NOW"
    log(f"✅ Health recovered: {prev_summary.get('fail', 0)}→{summary.get('fail', 0)} fail")
  else:
    level = "PERSISTENT_ISSUES"
    log(f"⚠️ Health still failing: {summary.get('fail', 0)} fail, {summary.get('warn', 0)} warn")

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
  # Orchestrators (moses/esther) ALSO poll the shared inbox_orchestrator
  # queue, where workers send fix requests / escalations. This is the
  # backup-orchestrator visibility path: Esther sees worker requests even
  # when Moses is down/degraded. Workers poll only their own inbox.
  extra_queues = []
  if AGENT_NAME in ("moses", "esther"):
    extra_queues.append("inbox_orchestrator")
  log(f"Starting — polling {inbox_queue}" + (f" + {extra_queues}" if extra_queues else ""))
  state = load_state()
  processed = set(state.get("processed_ids", []))

  def poll_once() -> bool:
    # Poll own inbox first, then the shared orchestrator inbox (if any).
    # One message per queue per tick keeps the loop bounded; the cron
    # re-runs every 5 min so both queues drain over successive ticks.
    msg = read_inbox(inbox_queue)
    source_queue = inbox_queue
    if not msg and extra_queues:
      for q in extra_queues:
        msg = read_inbox(q)
        if msg:
          # Process from the orchestrator queue: log which queue it came from
          log(f"  ← from shared queue {q}")
          source_queue = q
          break
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
          archive_message(source_queue, msg_id)
          return False

    # Re-check correlation_id from parsed body (hc send embeds it inside the body JSON string)
    if not correlation_id and isinstance(body, dict):
      # First try body dict level
      correlation_id = body.get("correlation_id", "") or ""
      # If still empty, try inner body string (hc send wraps payload in body["body"])
      if not correlation_id:
        inner_raw = body.get("body", "")
        if isinstance(inner_raw, str):
          try:
            inner = json.loads(inner_raw)
            if isinstance(inner, dict):
              correlation_id = inner.get("correlation_id", "") or ""
          except (json.JSONDecodeError, TypeError):
            pass # inner body parse — non-fatal


    subject = body.get("subject", "")

    # Normalize free-text subjects to known command subjects
    # "Task: fix the thing" → "TASK_REQUEST" (agents like Gisu use this format)
    if subject.startswith("Task:") or subject.startswith("TASK:"):
        task_desc = subject.split(":", 1)[1].strip()
        subject = "TASK_REQUEST"
        # Embed the task description into the body for the handler
        if isinstance(body, dict):
            body_body = body.get("body", {})
            if isinstance(body_body, dict):
                body_body["task"] = task_desc
            else:
                body["body"] = {"task": task_desc}

    # Check if this message targets this agent (labels, agent names) FIRST —
    # before task creation. A message aimed at other agents must not create
    # a stray task row here (S4 ownership: only the executing agent creates).
    agent_labels = _load_agent_labels()
    should_process, skip_reason = _should_process(body, agent_labels)
    if not should_process:
        log(f"Skipping {subject} — {skip_reason}")
        archive_message(source_queue, msg_id)
        return False

    # ── Bus → tasks: CREATE-BEFORE-ARCHIVE (TL-v2 S4, SRE R-12) ──
    # For tracked subjects with a correlation_id, create the source='inbox'
    # task row BEFORE archiving the message. A crash between the create and
    # the archive leaves the row — the stale sweep is the safety net. The
    # partial unique index (source='inbox' AND correlation_id) makes the
    # create idempotent across handler restarts.
    # Content for the row: subject + a short command/description preview.
    task_content = subject
    if isinstance(body, dict):
      inner = body.get("body", "")
      if isinstance(inner, dict):
        cmd = inner.get("command") or inner.get("task") or inner.get("reason")
        if cmd:
          task_content = f"{subject}: {str(cmd)[:120]}"
      elif isinstance(inner, str):
        task_content = f"{subject}: {inner[:120]}"
    task_create_from_message(subject, correlation_id, task_content)

    # --- EARLY ARCHIVE ---
    # Archive the message immediately after reading so the PGMQ
    # visibility timeout can never cause a re-read loop. Even if the
    # handler process crashes (uncaught BaseException, signal, OOM)
    # during processing, the message is already gone from the queue.
    # This is the primary archive; post-processing archives (in each
    # subject handler and the exception handler) are fallbacks that
    # silently succeed on already-archived messages.
    # (Task creation above happens FIRST — create-before-archive.)
    archive_message(source_queue, msg_id)
    # --- END EARLY ARCHIVE ---

    # Silent subjects — known noise: the doctor's own bus round-trip probe
    # (cortex_doctor checks.py _check_bus_e2e sends DOCTOR_TEST to
    # inbox_<agent> on EVERY doctor run — updates, dogfood, readiness-check,
    # manual runs). Archive and move on WITHOUT notifying Telegram. This MUST
    # precede the pickup notify: previously the notify fired first and every
    # drained test message became a chat message (flood observed 2026-08-08).
    if subject in ("DOCTOR_TEST", "STATUS_REQUEST", "HEARTBEAT", "PING"):
        log(f"Silently archived {subject} from {body.get('from', '?')}")
        archive_message(source_queue, msg_id)
        state.setdefault("last_noise", []).append(
          {"subject": subject, "from": body.get("from"), "t": time.time()}
        )
        state["last_noise"] = state["last_noise"][-40:]
        save_state(state)
        return True

    # Notify pickup — SKIPPED for tracked subjects: the task-entry notify
    # from task-db.py replaces it (R-14: one EXEC = 1 entry message, not 5).
    if subject not in TASK_CREATING_SUBJECTS:
      notify_telegram(
        f"📥 [{AGENT_NAME}] Received {subject} from {body.get('from', '?')}",
        f"📥 {AGENT_NAME}:{subject}",
      )

    # Idempotency check — skip for messages without correlation_id
    if correlation_id and correlation_id in processed:
      log(f"Skipping already-processed corr={correlation_id[:8] if correlation_id else ''}…")
      # Archive so it doesn't loop forever
      archive_message(source_queue, msg_id)
      return False

    try:
      # ── Dispatch via command registry ──
      start = time.time()  # init before any dispatch so except handler is safe
      from commands import dispatch as cmd_dispatch

      # in_progress at dispatch (S4 lifecycle)
      if subject in TASK_CREATING_SUBJECTS:
        task_transition_by_correlation(correlation_id, "in_progress")

      result_body = cmd_dispatch(subject, body, msg)

      if result_body is not None:
        # Command handled — track, notify, archive
        from commands import COMMANDS
        cmd_info = COMMANDS.get(subject)
        result_subject = cmd_info["result"] if cmd_info else f"{subject}_RESULT"

        # Duration tracking
        result_body.setdefault("duration_seconds", round(time.time() - start, 1))
        result_body.setdefault("success", True)  # assume success unless handler says otherwise
        # R-19/M-12: carry the task id so the orchestrator can join
        # reply ↔ task directly (by task id, not just correlation).
        if correlation_id:
          task_id = _lookup_task_id(correlation_id)
          if task_id:
            result_body["task_id"] = task_id

        archive_message(inbox_queue, msg.get("msg_id", ""))
        send_bus_result("inbox_moses", correlation_id, result_body, result_subject)

        # Completed at Result-receipt (S4): the task that this EXEC/UPDATE
        # created is closed once its result has been sent back. The
        # correlation unique index makes this idempotent.
        if subject in TASK_CREATING_SUBJECTS:
          task_transition_by_correlation(correlation_id, "completed")

        # State tracking — only track non-empty correlation_ids
        if correlation_id:
          processed.add(correlation_id)
          state.setdefault("processed_ids", [])
          state["processed_ids"].append(correlation_id)
          state["processed_ids"] = state["processed_ids"][-50:]
        state["last_result"] = result_body
        save_state(state)

        # Notification
        success = result_body.get("success", False)
        # Check both 'errors' (plural) and 'error' (singular) for flexibility
        err_list = result_body.get("errors", [])
        err_single = result_body.get("error", "")
        combined = err_list[:1] + ([err_single] if err_single else [])
        if not combined:
            combined = [result_body.get("stderr", "")]
        error_msg = (combined[0] or "unknown")[:120]
        if success:
          log(f"✅ {subject} completed")
        else:
          log(f"❌ {subject} had issues: {error_msg}")

        # Telegram — only for known actionable subjects, not STATUS or DOCTOR
        if subject not in ("STATUS_REQUEST", "DOCTOR_REQUEST"):
          emoji = "✅" if success else "❌"
          # Build richer summary for UPDATE_RESULT (git SHA + doctor counts)
          extra = ""
          sha_after = result_body.get("git_sha_after", "")
          doctor = result_body.get("doctor", {})
          doc_sum = doctor.get("summary", {}) if isinstance(doctor, dict) else {}
          doc_parts = []
          if doc_sum.get("pass"):      doc_parts.append(f"P{doc_sum['pass']}")
          if doc_sum.get("warn"):      doc_parts.append(f"W{doc_sum['warn']}")
          if doc_sum.get("fail"):      doc_parts.append(f"F{doc_sum['fail']}")
          if sha_after:
            extra = f" SHA={sha_after}"
          if doc_parts:
            extra += f" doctor={'/'.join(doc_parts)}"
          # Grab a preview from script output if available (only on failure, skip for clean UPDATEs)
          preview = ""
          if not success:
            out = result_body.get("stdout", result_body.get("update_output", ""))
            if out:
              for line in out.strip().split("\n"):
                clean = line.strip()
                if clean and not clean.startswith("═") and not clean.startswith("━"):
                  preview = f" — {clean[:120]}"
                  break
          notify_telegram(
            f"{emoji} [{AGENT_NAME}] {result_subject}: {'OK' if success else error_msg}{extra}{preview}",
            f"{emoji} {AGENT_NAME}:{subject.split('_')[0]}"
          )
        return True

      # ── Result subjects (*_RESULT) — expected replies from fleet agents ──
      if subject.endswith("_RESULT"):
        status = "✅" if body.get("body", {}).get("success") else "❌"
        result_from = body.get("from", "?")
        result_preview = ""
        result_body_data = body.get("body", {})
        if isinstance(result_body_data, dict):
          exit_code = result_body_data.get("exit_code", "")
          stdout_preview = (result_body_data.get("stdout", "") or "")[:60].replace("\n", " ")
          if exit_code != "":
            result_preview = f" exit={exit_code} {stdout_preview}"
        log(f"📬 Result {subject} from {result_from}:{result_preview}")
        # Completed at Result-receipt (S4): the orchestrator's handler that
        # receives EXEC_RESULT/UPDATE_RESULT closes the inbox task linked by
        # correlation_id. Idempotent via the partial unique index.
        if subject in ("EXEC_RESULT", "UPDATE_RESULT", "DIAGNOSTIC_RESULT",
                       "ROLLBACK_RESULT", "FIX_RESULT", "LEARNINGS_RESULT",
                       "STATUS_RESULT", "GIT_AUTH_RESULT"):
          task_transition_by_correlation(correlation_id, "completed")
        archive_message(source_queue, msg_id)
        state.setdefault("last_results", [])
        state["last_results"].append({
          "subject": subject, "from": result_from,
          "correlation_id": correlation_id,
          "timestamp": time.time(),
        })
        state["last_results"] = state["last_results"][-20:]
        save_state(state)
        return True

      # ── Skill Stub Recovery — stage payload for orchestrator restore ──
      # Fleet agents send full skill content here (agents cannot write the
      # repo). This is NOT noise and NOT an error: extract the payload, write
      # it to the staging dir, then archive the message. The orchestrator's
      # restore step reads the staging dir and replaces stub skills.
      if subject.startswith("Skill Stub Recovery"):
        try:
          payload = body.get("body", {})
          if isinstance(payload, str):
            payload = json.loads(payload)
          stage_dir = Path(os.environ.get("CORTEX_DEPLOY_HOME", Path.home() / ".hermes-cortex")) / "state" / "skill-stub-recovery"
          stage_dir.mkdir(parents=True, exist_ok=True)
          host = payload.get("hostname", body.get("from", "unknown"))
          part = payload.get("part", 0)
          parts = payload.get("parts", 1)
          skills = payload.get("skills", {})
          if isinstance(skills, dict) and skills:
            out_file = stage_dir / f"{host}-part{part}of{parts}.json"
            out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
            log(f"📦 Staged Skill Stub Recovery from {host} part {part}/{parts} ({len(skills)} skills) → {out_file.name}")
            archive_message(source_queue, msg_id)
            state.setdefault("last_staged", []).append(
              {"subject": subject, "from": body.get("from"), "skills": len(skills), "t": time.time()}
            )
            state["last_staged"] = state["last_staged"][-20:]
            save_state(state)
            return True
          log(f"⚠️ Skill Stub Recovery from {body.get('from', '?')} had no skills dict — archiving raw")
          archive_message(source_queue, msg_id)
          return True
        except Exception as e:
          log(f"❌ Failed to stage Skill Stub Recovery: {type(e).__name__}: {e}")
          archive_message(source_queue, msg_id)
          return False

      # Silent subjects — known noise, just archive and move on
      if subject in ("DOCTOR_TEST", "STATUS_REQUEST", "HEARTBEAT", "PING"):
        log(f"Silently archived {subject} from {body.get('from', '?')}")
        archive_message(source_queue, msg_id)
        state.setdefault("last_noise", []).append(
          {"subject": subject, "from": body.get("from"), "t": time.time()}
        )
        save_state(state)
        return True

      # Issue-report subjects — agents pushing findings TO the orchestrator
      # (ISSUES:, IMPROVEMENTS:, PROPOSAL:, RE: ...). These are reports, not
      # commands: a command registry lookup is the wrong shape (there is no
      # *_REQUEST to run). Do NOT error, do NOT archive — leave the message
      # in the queue so the orchestrator's inbox_read picks it up, and mark
      # processed so the next handler tick skips it (idempotency path below
      # archives it only after it has been surfaced). Fixes the "Unknown
      # subject" drop of kustos's doctor-fails report (2026-08-03).
      _issue_prefixes = ("ISSUES:", "🚨 ISSUES:", "IMPROVEMENTS:", "PROPOSAL:", "📝 PROPOSAL:", "RE: ")
      if subject.startswith(_issue_prefixes):
        log(f"📋 Issue report '{subject}' from {body.get('from', '?')} — left in queue for orchestrator")
        notify_telegram(
          f"📋 [{AGENT_NAME}] Issue report from {body.get('from', '?')}: {subject}",
          f"📋 {AGENT_NAME}:ISSUE_REPORT",
        )
        if correlation_id:
          processed.add(correlation_id)
          state.setdefault("processed_ids", [])
          state["processed_ids"].append(correlation_id)
          state["processed_ids"] = state["processed_ids"][-50:]
        save_state(state)
        return True

      # ── Learning Report — stage payload for orchestrator skill-lifecycle ──
      # Fleet agents' agent-learning-collector sends Learning Reports (skills
      # delta, lessons, session stats) every 6h. These are DATA for the
      # orchestrator's orch-skill-lifecycle pipeline, not commands. Mirror the
      # Skill Stub Recovery pattern: stage the body to a state dir so the
      # 04:00 pipeline can read it, then let the early-archive keep the queue
      # clean. Without this branch the report hits "Unknown subject" and the
      # content is lost from the live flow (regression: early-archive added
      # 2026-07-23 ate all reports; verified 2026-08-03 — queue empty at 04:00,
      # collector state frozen since 07-28).
      if subject.startswith("Learning Report"):
        try:
          stage_dir = Path(os.environ.get("CORTEX_DEPLOY_HOME", Path.home() / ".hermes-cortex")) / "state" / "learning-reports"
          stage_dir.mkdir(parents=True, exist_ok=True)
          src_agent = body.get("from", "unknown") if isinstance(body, dict) else "unknown"
          ts = datetime.now().strftime("%Y%m%d-%H%M%S")
          out_file = stage_dir / f"{src_agent}-{ts}.md"
          content = body.get("body", body) if isinstance(body, dict) else str(body)
          if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False, indent=2)
          out_file.write_text(f"# Learning Report — {src_agent}\n\n{content}\n")
          log(f"📦 Staged Learning Report from {src_agent} ({len(str(content))} chars) → {out_file.name}")
          state.setdefault("last_staged", []).append(
            {"subject": subject, "from": src_agent, "t": time.time()}
          )
          state["last_staged"] = state["last_staged"][-20:]
          save_state(state)
        except Exception as e:
          log(f"⚠️ Learning Report staging failed: {type(e).__name__}: {e}")
        return True

      # ── Skill Report — stage payload for orch-skill-evaluate pipeline ──
      # Fleet agents' agent-collect-skills.sh / send-skill-report.py send
      # chunked Skill Reports ("Skill Report: N custom skills (part X/Y)")
      # to inbox_orchestrator for the orch-skill-report-process.py digest.
      # These are DATA for the orchestrator's skill-evaluation pipeline, not
      # commands. Without this branch the report hits "Unknown subject" — the
      # early-archive destroys the live-queue copy the processor reads, an
      # error _RESULT fires to inbox_moses, and Telegram warns. Mirror the
      # Learning Report pattern: stage the full body to a state dir so the
      # weekly orch-skill-evaluate cron can compile the digest (esther's
      # 41-part / 310-skill report eaten part-by-part at 5-min cadence,
      # parts 2-31 archived 2026-08-14 01:00-02:15, verified same day).
      if subject.startswith("Skill Report:"):
        try:
          stage_dir = Path(os.environ.get("CORTEX_DEPLOY_HOME", Path.home() / ".hermes-cortex")) / "state" / "skill-reports"
          stage_dir.mkdir(parents=True, exist_ok=True)
          src_agent = body.get("from", "unknown") if isinstance(body, dict) else "unknown"
          ts = datetime.now().strftime("%Y%m%d-%H%M%S")
          content = body.get("body", body) if isinstance(body, dict) else str(body)
          if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False, indent=2)
          part_tag = ""
          for m_part in subject.split(" "):
            if m_part.startswith("(part"):
              part_tag = "-" + m_part.strip("()").replace("/", "of")
          out_file = stage_dir / f"{src_agent}-{ts}{part_tag}.md"
          out_file.write_text(f"# Skill Report — {src_agent}\n\n{content}\n")
          log(f"📦 Staged Skill Report from {src_agent}{part_tag} ({len(str(content))} chars) → {out_file.name}")
          state.setdefault("last_staged", []).append(
            {"subject": subject, "from": src_agent, "t": time.time()}
          )
          state["last_staged"] = state["last_staged"][-20:]
          save_state(state)
        except Exception as e:
          log(f"⚠️ Skill Report staging failed: {type(e).__name__}: {e}")
        return True

      # Unknown subject — send error response so orchestrator knows
      log(f"Unknown subject '{subject}', sending error (corr={correlation_id[:8]}…)")
      error_body = {
        "success": False,
        "error": f"Unknown subject: {subject}",
        "command": subject,
        "duration_seconds": round(time.time() - start, 1),
      }
      send_bus_result("inbox_moses", correlation_id, error_body, f"{subject}_RESULT")
      archive_message(source_queue, msg_id)
      notify_telegram(
        f"⚠️ [{AGENT_NAME}] Unknown subject '{subject}' from {body.get('from', '?')}, responded with error",
        f"⚠️ {AGENT_NAME}:UNKNOWN"
      )
      return False

    except Exception as e:
      log(f"❌ CRASH processing {subject}: {type(e).__name__}: {e}")
      import traceback
      traceback.print_exc()
      archive_message(source_queue, msg_id)
      send_bus_result("inbox_moses", correlation_id, {
        "success": False,
        "error": f"Handler crashed: {type(e).__name__}: {e}",
        "command": subject,
        "exit_code": -1,
        "duration_seconds": round(time.time() - start, 1),
      }, f"{subject}_RESULT")
      notify_telegram(
        f"❌ [{AGENT_NAME}] {subject} crashed: {type(e).__name__}: {str(e)[:80]}",
        f"❌ {AGENT_NAME}:{subject}"
      )
      return True

  # Health state tracking (report on state change, not every tick)
  last_doctor = state.get("last_doctor", {})

  def poll_and_check() -> None:
    nonlocal last_doctor
    # Heartbeat freshness marker: heartbeat.py's check_inbox_staleness() reads
    # HERMES_HOME/state/last-message-check (default ~/.hermes/state/). The old
    # file-based inbox (check-agent-messages.sh) wrote this file; the handler
    # is the inbox poller now, so it must keep the marker fresh or heartbeat
    # reports "Agent inbox scan: DOWN" permanently. Write both the HERMES_HOME
    # path (what heartbeat reads) and the legacy ~/.hermes-cortex/state path
    # (what older docs/crons referenced) — cheap and covers all hosts.
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for _state_dir in (
        Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "state",
        HOME / ".hermes-cortex" / "state",
    ):
        try:
            _state_dir.mkdir(parents=True, exist_ok=True)
            (_state_dir / "last-message-check").write_text(stamp)
        except OSError:
            pass  # best-effort — heartbeat may be absent on this host
    # Process up to 25 messages per tick, or until the queue is empty.
    # This prevents backlog: if Learning Reports or other non-urgent
    # messages accumulate ahead of an UPDATE_REQUEST, a single poll_once()
    # would take 5 ticks (25 min) to clear them. With the loop, the
    # handler drains the queue on every tick.
    # Stale sweep runs EVERY tick (R-16/M-2): catches inbox tasks stuck in
    # in_progress from a previous crashed handler, not just from this tick's
    # messages. Threshold: 1h default, TASKS_STALE_HOURS env override.
    try:
      stale_h = float(os.environ.get("TASKS_STALE_HOURS", "1"))
    except (TypeError, ValueError):
      stale_h = 1.0
    task_stale_sweep(max_hours=stale_h)

    had_work = False
    tick_start = time.time()
    for _ in range(25):
      msg = poll_once()
      if not msg:
        break
      had_work = True
      # Don't run doctor after every message — run once at the end
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
      last_doctor = doctor # silently update
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
