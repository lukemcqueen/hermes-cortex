#!/usr/bin/env python3
"""
agent-learning-collector.py — Agent-side: collect learnings, skills, and session data
and report to Moses via Agent Bus.

Runs as a no_agent cron (every 6h). Collects four data sources:

  1. Skills delta — new/modified SKILL.md files since last report
  2. Lessons delta — new lesson files in ~/brain/lessons/
  3. Session stats — recent session activity from Hermes session DB
  4. System context — agent hostname, OS, hermes version

Sends a compact structured Learning Report to inbox_moses via PGMQ.
Silent (exit 0) when nothing new to report.

Deployed to fleet agents via cortex-update.sh.

Usage:
    python3 agent-learning-collector.py              # collect and send
    python3 agent-learning-collector.py --dry-run    # preview without sending
    python3 agent-learning-collector.py --force      # collect fresh even if nothing new
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Config ──────────────────────────────────────────────────────
HOME = Path.home()
STATE_DIR = HOME / ".hermes-cortex" / "state"
SKILLS_DIR = HOME / ".hermes" / "skills"
LESSONS_DIR = HOME / "brain" / "lessons"
SESSION_DB = HOME / ".hermes-cortex" / "sessions.db"
STATE_FILE = STATE_DIR / "agent-learning-collector-state.json"

# Agent identity — use AGENT_NAME env var (e.g. "gisu", "titus", "moses"),
# fall back to hostname for backward compat
AGENT_NAME = os.environ.get("AGENT_NAME") or os.uname().nodename

# Repo path
CORTEX_REPO = Path(os.environ.get("CORTEX_REPO", HOME / "hermes-cortex"))

# ── Report thresholds ─────────────────────────────────────────
MAX_SKILLS_IN_REPORT = 20       # don't send more than this per cycle
MAX_SESSION_DAYS = 1            # look back this many days for sessions
SILENT_IF_NO_CHANGE = True      # watchdog pattern: no output = nothing

MAX_REPORT_CHARS = 80000        # keep under bus message limit (~100KB)


def load_state() -> dict:
    """Load last-run state (timestamps, checksums)."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "last_run": 0,
        "skill_hashes": {},
        "lesson_count": 0,
        "last_session_id": 0,
    }


def save_state(state: dict):
    """Persist state for next run."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def get_timestamp() -> float:
    """Current Unix timestamp."""
    return time.time()


# ── Collection Functions ──────────────────────────────────────

def _hash_file(path: Path) -> str:
    """Quick content hash for change detection."""
    try:
        import hashlib
        return hashlib.md5(path.read_bytes()).hexdigest()[:16]
    except (OSError, ImportError):
        return ""


def _get_skill_delta(state: dict) -> list[dict]:
    """Find new/modified skills since last run."""
    old_hashes = state.get("skill_hashes", {})
    new_hashes = {}
    delta = []

    if not SKILLS_DIR.is_dir():
        return delta

    for skill_file in sorted(SKILLS_DIR.rglob("SKILL.md")):
        if not skill_file.is_file():
            continue
        rel = str(skill_file.relative_to(SKILLS_DIR))
        h = _hash_file(skill_file)
        new_hashes[rel] = h

        # Skip if hash unchanged
        old_h = old_hashes.get(rel)
        if old_h == h:
            continue

        # Extract metadata
        name = skill_file.parent.name
        parent = skill_file.parent.parent
        try:
            category = str(parent.relative_to(SKILLS_DIR))
        except ValueError:
            category = "uncategorized"

        # Get file info
        stat = skill_file.stat()
        size = stat.st_size
        mtime = stat.st_mtime

        # Extract description from frontmatter
        text = skill_file.read_text(errors="replace")
        desc = _extract_description(text)

        delta.append({
            "name": name,
            "category": category,
            "size": size,
            "mtime": mtime,
            "description": desc,
            "is_new": rel not in old_hashes,
        })

        if len(delta) >= MAX_SKILLS_IN_REPORT:
            break

    # Update hashes for next run
    state["skill_hashes"] = new_hashes
    return delta


def _extract_description(text: str) -> str:
    """Extract description from YAML frontmatter."""
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            for line in text[3:end].split("\n"):
                line = line.strip()
                if line.startswith("description:"):
                    desc = line[len("description:"):].strip().strip("'\"")
                    if desc:
                        return desc
    return "(no description)"


def _get_lesson_delta(state: dict) -> list[dict]:
    """Find new lesson files since last run."""
    old_count = state.get("lesson_count", 0)
    new_lessons = []

    if not LESSONS_DIR.is_dir():
        return new_lessons

    all_lessons = sorted(LESSONS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime)
    current_count = len(all_lessons)

    # Only report new ones
    new_files = all_lessons[old_count:] if old_count < current_count else []

    for f in new_files:
        stat = f.stat()
        text = f.read_text(errors="replace")[:2000]  # first 2KB
        # Extract title from first heading or frontmatter
        title = f.stem.replace("-", " ").title()
        for line in text.split("\n")[:5]:
            m = re.match(r"^#\s+(.+)", line)
            if m:
                title = m.group(1).strip()
                break

        new_lessons.append({
            "title": title,
            "file": f.name,
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "preview": text[:500],
        })

    state["lesson_count"] = current_count
    return new_lessons


def _get_session_stats() -> dict:
    """Get recent session activity from Hermes session DB."""
    stats = {"total_sessions": 0, "recent_sessions": 0, "last_session_hours_ago": None}

    # Try Hermes state.db first (newer format)
    for db_path in [
        HOME / ".hermes" / "state.db",
        SESSION_DB,
    ]:
        if db_path.exists():
            try:
                conn = sqlite3.connect(str(db_path))
                cur = conn.cursor()

                # Total sessions
                cur.execute("SELECT COUNT(*) FROM sessions")
                stats["total_sessions"] = cur.fetchone()[0]

                # Sessions in last N days
                cutoff = time.time() - (MAX_SESSION_DAYS * 86400)
                cur.execute(
                    "SELECT COUNT(*), MAX(created_at) FROM sessions WHERE created_at > ?",
                    (cutoff,),
                )
                row = cur.fetchone()
                stats["recent_sessions"] = row[0] if row else 0

                if row and row[1]:
                    secs_ago = time.time() - row[1]
                    stats["last_session_hours_ago"] = round(secs_ago / 3600, 1)

                conn.close()
                break
            except (sqlite3.Error, OSError):
                pass

    return stats


def _get_agent_context() -> dict:
    """Get agent system context."""
    import platform
    ctx = {
        "agent_name": AGENT_NAME,
        "hostname": os.uname().nodename,
        "os": f"{platform.system()} {platform.release()}",
        "hermes_version": "unknown",
    }
    # Try to get Hermes version
    try:
        result = subprocess.run(
            ["hermes", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            ctx["hermes_version"] = result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return ctx


# ── Bus Sender ─────────────────────────────────────────────────

def _resolve_env(key: str, default: str = "") -> str:
    """Resolve env var from env → config files."""
    val = os.environ.get(key)
    if val:
        return val
    for cfg in [
        HOME / ".hermes-cortex" / "cortex-bus.conf",
        CORTEX_REPO / ".env",
    ]:
        if cfg.exists():
            try:
                for line in cfg.read_text().splitlines():
                    line = line.strip()
                    if line.startswith(f"{key}="):
                        return line.split("=", 1)[1].strip().strip("'\"")
            except OSError:
                pass
    return default


def _build_auth_headers(url: str) -> dict[str, str]:
    """Build auth headers for local vs remote."""
    host = url.split("://")[-1].split("/")[0].split(":")[0]
    if host in ("127.0.0.1", "localhost", "::1"):
        token = _resolve_env("CORTEX_BUS_TOKEN")
        return {"Authorization": f"Bearer {token}"} if token else {}
    import base64
    basic = _resolve_env("CORTEX_BASIC_AUTH") or _resolve_env("CORTEX_BUS_AUTH")
    if basic and ":" in basic:
        encoded = base64.b64encode(basic.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}
    return {}


def send_report(report: dict, dry_run: bool = False) -> bool:
    """Send learning report to Moses via PGMQ bus."""
    from urllib.request import Request, urlopen
    from urllib.error import URLError

    bus_url = (
        _resolve_env("CORTEX_BUS_URL") or
        _resolve_env("CORTEX_BUS_FALLBACK_URL") or
        ""
    )
    if not bus_url:
        print("WARN: No bus URL configured — report not sent", file=sys.stderr)
        return False

    bus_url = bus_url.rstrip("/")
    hostname = AGENT_NAME

    # Build message
    skills = report.get("skills", [])
    lessons = report.get("lessons", [])
    stats = report.get("sessions", {})

    lines = []
    lines.append(f"━━━ Learning Report — {hostname} ━━━")
    lines.append(f"Generated: {report.get('generated', '')}")
    lines.append(f"Type: full" if (skills or lessons) else "Type: heartbeat")
    lines.append(f"Sessions: {stats.get('total_sessions', 0)} total, "
                 f"{stats.get('recent_sessions', 0)} recent")

    if skills:
        lines.append(f"\n== Skills ({len(skills)} changed) ==")
        for s in skills[:10]:  # top 10
            tag = "  [NEW]" if s.get("is_new") else "  [MOD]"
            lines.append(f"{tag} {s['name']} ({s['category']})")
            lines.append(f"     {s['description']}")

    if lessons:
        lines.append(f"\n== Lessons ({len(lessons)} new) ==")
        for l in lessons[:5]:
            lines.append(f"  • {l['title']}")
            lines.append(f"    {l['preview'][:200]}")

    # Truncate to bus limit
    body_text = "\n".join(lines)
    if len(body_text) > MAX_REPORT_CHARS:
        body_text = body_text[:MAX_REPORT_CHARS] + "\n... [truncated]"

    payload = {
        "queue": "inbox_moses",
        "message": {
            "from": hostname,
            "subject": (
                f"Learning Report: {len(skills)} skills, {len(lessons)} lessons"
                if (skills or lessons)
                else f"Learning Report: heartbeat"
            ),
            "body": body_text,
            "topic": "reports",
            "priority": "high" if len(skills) > 0 else "normal",
        },
    }

    if dry_run:
        print(f"[DRY RUN] Would send to {bus_url}")
        print(f"  Subject: {payload['message']['subject']}")
        print(f"  Body: {len(body_text)} chars")
        return True

    api_url = f"{bus_url}/api/pgmq/send"
    headers = {"Content-Type": "application/json"}
    headers.update(_build_auth_headers(bus_url))

    req = Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
        msg_id = result.get("msg_id", "?")
        print(f"Sent: {payload['message']['subject']} (msg_id={str(msg_id)[:8]})", flush=True)
        return True
    except URLError as e:
        body = ""
        if hasattr(e, 'read'):
            try:
                body = e.read().decode()[:200]
            except Exception:
                body = str(e)
        print(f"ERR: Send failed: {getattr(e, 'code', '?')} {body}", flush=True)
        return False
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERR: Send failed: {e}", flush=True)
        return False


def _run_session_mining(state: dict, dry_run: bool = False) -> None:
    """Mine sessions for new lessons via session-mine CLI.
    First run: mines ALL past sessions (bootstrap).
    Subsequent: mines last 1 day (incremental).
    Uses state['session_mining_bootstrap_done'] to track."""
    import shutil
    session_mine = shutil.which("session-mine") or str(HOME / ".hermes" / "bin" / "session-mine")
    if not session_mine or not Path(session_mine).is_file():
        return  # session-mine not installed — unlikely, but skip silently

    # Bootstrap: mine all past sessions on first run, incremental after
    bootstrap_done = state.get("session_mining_bootstrap_done", False)
    days = 365 if not bootstrap_done else 1

    try:
        cmd = [session_mine, "mine", "--days", str(days), "--auto"]
        if dry_run:
            cmd.append("--dry-run")
            print(f"[DRY RUN] Would run: {' '.join(cmd)}", flush=True)
            return

        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            print(f"WARN: session-mine exited {result.returncode}: {result.stderr[:200]}", file=sys.stderr, flush=True)
        elif not bootstrap_done:
            state["session_mining_bootstrap_done"] = True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        print(f"WARN: session-mine failed: {e}", file=sys.stderr, flush=True)


# ── Main ──────────────────────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    state = load_state()
    t0 = time.time()

    # Phase 0: Mine sessions for new lessons (bootstrap: all past, then incremental)
    _run_session_mining(state, dry_run=dry_run)

    # Phase 1: Collect
    skills_delta = _get_skill_delta(state)
    lessons_delta = _get_lesson_delta(state)
    session_stats = _get_session_stats()
    agent_ctx = _get_agent_context()

    # Phase 2: Decide if there's something to report
    has_data = bool(skills_delta) or bool(lessons_delta)
    is_heartbeat_due = (t0 - state.get("last_run", 0) > 86400)  # heartbeat every 24h

    if not has_data and not is_heartbeat_due and not force:
        save_state(state)  # still save hashes so next run is faster
        return  # Silent — nothing new

    # Phase 3: Build report
    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "agent": agent_ctx,
        "sessions": session_stats,
        "skills": skills_delta,
        "lessons": lessons_delta,
        "is_heartbeat": not has_data and is_heartbeat_due,
    }

    # Phase 4: Send
    sent = send_report(report, dry_run=dry_run)

    # Phase 5: Save state (only if successfully sent or dry run)
    if sent or dry_run:
        state["last_run"] = t0
        # Skill hashes were updated inside _get_skill_delta
        # Lesson count was updated inside _get_lesson_delta
        save_state(state)

    if not sent and not dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
