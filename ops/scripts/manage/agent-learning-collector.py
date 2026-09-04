#!/usr/bin/env python3
"""
agent-learning-collector.py — Agent-side: collect learnings, skills, and session data
and report to Moses via Agent Bus.

Runs as a no_agent cron (every 6h). Collects five data sources:

  1. Skills delta — new/modified SKILL.md files since last report
  2. Lessons delta — new lesson files in ~/brain/lessons/
  3. Learnings (ad-hoc) — pending .md files in ~/brain/learnings/pending/
  4. Session stats — recent session activity from Hermes session DB
  5. System context — agent hostname, OS, hermes version

Session mining (running session-mine to extract lessons) is handled by a
separate overnight cron (agent-session-mine) that dumps mined lessons into
~/brain/lessons/. The collector picks them up instantly via source #2 above.

Sends a compact structured Learning Report to inbox_orchestrator (the shared
orchestrator inbox) via PGMQ.
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

# Agent identity — env → agent.env → .env. NEVER hostname: a machine name
# is not an agent name and would report learnings under the wrong identity
# (Luke directive 2026-08-14). Missing identity fails loudly.
AGENT_NAME = os.environ.get("AGENT_NAME", "").strip()
if not AGENT_NAME:
    for _idf in (HOME / ".hermes-cortex" / "agent.env", HOME / "hermes-cortex" / ".env"):
        try:
            if _idf.is_file():
                for _line in _idf.read_text().splitlines():
                    _line = _line.strip()
                    if _line.startswith("AGENT_NAME="):
                        _val = _line.split("=", 1)[1].strip().strip("\"'")
                        if _val:
                            AGENT_NAME = _val
                            break
        except OSError:
            continue
if not AGENT_NAME or AGENT_NAME == "unknown":
    print("❌ AGENT_NAME not configured — set AGENT_NAME= in "
          "~/.hermes-cortex/agent.env / ~/hermes-cortex/.env or export AGENT_NAME",
          file=sys.stderr)
    sys.exit(1)

# Repo path
CORTEX_REPO = Path(os.environ.get("CORTEX_REPO", HOME / "hermes-cortex"))

# ── Report thresholds ─────────────────────────────────────────
MAX_SKILLS_IN_REPORT = 20       # don't send more than this per cycle
MAX_SESSION_DAYS = 1            # look back this many days for sessions
SILENT_IF_NO_CHANGE = True      # watchdog pattern: no output = nothing

# Pending learnings — agents write .md files here during sessions
LEARNINGS_PENDING_DIR = HOME / "brain" / "learnings" / "pending"
LEARNINGS_SENT_DIR = HOME / "brain" / "learnings" / "sent"
MAX_LEARNINGS_IN_REPORT = 10

MAX_REPORT_CHARS = 80000        # keep under bus message limit (~100KB)


def load_state() -> dict:
    """Load last-run state (timestamps, checksums)."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass  # expected — silently handled
    return {
        "last_run": 0,
        "skill_hashes": {},
        "lesson_count": 0,
        "last_session_id": 0,
        "sent_learning_hashes": {},
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

        # ── Stub guard (2026-08-05): never report pruned/placeholder skills ──
        # A skill whose body was replaced by a compression/pruning placeholder
        # (e.g. "--- Full content ---\n(content unavailable)") must NOT be
        # reported as a healthy delta — upstreaming propagates the stub
        # fleet-wide (history: 8587b511 auto-upstreamed 32 pruned marketing
        # skills from esther). The hash is already tracked above, so the stub
        # stays silent on subsequent runs; it is simply excluded from the
        # report so the orchestrator never re-upstreams it.
        # Match the EXACT placeholder block (both markers together) so guard
        # comments that merely MENTION the marker are never misflagged.
        _body = text.split("---", 2)[-1] if text.count("---") >= 2 else text
        _is_stub = (len(_body) < 2048 and "--- Full content ---" in _body and "content unavailable" in _body) \
            or ("[SKILL_PRUNED]" in _body and len(_body) < 2048)
        if _is_stub:
            continue

        delta.append({
            "name": name,
            "category": category,
            "size": size,
            "mtime": mtime,
            "description": desc,
            "is_new": rel not in old_hashes,
        })

    # Cap the REPORT at MAX_SKILLS_IN_REPORT, but never break out of the
    # hashing loop early: a break here left alphabetically-late skills
    # (web-development/*, workflow/*, x-twitter-growth, yuanbao) unrecorded
    # in new_hashes, so they were re-reported as [NEW] every cycle
    # (fixed 2026-08-14).
    delta = delta[:MAX_SKILLS_IN_REPORT]

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
        # Strip leading YAML frontmatter so the preview shows the lesson
        # BODY, not just metadata (fixed 2026-08-14: report previews were
        # 100% frontmatter, making lesson evaluation blind fleet-wide).
        body = text
        if body.startswith("---"):
            fm_end = body.find("\n---", 3)
            if fm_end > 0:
                body = body[fm_end + 4:]
        body = body.strip()
        # Extract title from first heading or frontmatter
        title = f.stem.replace("-", " ").title()
        for line in text.split("\n")[:5]:
            m = re.match(r"^#\s+(.+)", line)
            if m:
                title = m.group(1).strip()
                break
        if not body:
            # Frontmatter-only lesson (session-mine artifact) — surface it
            # with the raw head so the orchestrator can still see the tags.
            body = text[:500]

        new_lessons.append({
            "title": title,
            "file": f.name,
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "preview": body[:500],
        })

    state["lesson_count"] = current_count
    return new_lessons


def _hash_learning_file(filepath: Path) -> str:
    """Stable hash combining filename + content for dedup (first 200 chars)."""
    import hashlib
    try:
        content = filepath.read_bytes()
        return hashlib.md5(content).hexdigest()[:16]
    except OSError:
        return ""


def _parse_learning_frontmatter(text: str) -> dict[str, str]:
    """Extract title and type from YAML frontmatter."""
    meta = {"title": "", "type": "discovery"}
    if text.startswith("---"):
        end = text.find("---", 3)
        if end > 0:
            for line in text[3:end].split("\n"):
                line = line.strip()
                if line.startswith("title:"):
                    meta["title"] = line[len("title:"):].strip().strip("'\"")
                elif line.startswith("type:"):
                    t = line[len("type:"):].strip().strip("'\"")
                    if t in ("discovery", "lesson", "improvement"):
                        meta["type"] = t
    return meta


def _extract_heading_title(text: str) -> str:
    """Fallback: extract first # heading as title."""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("##"):
            return line[2:].strip()
    return ""


def _get_pending_learnings(state: dict) -> list[dict]:
    """Find pending learning .md files that haven't been sent yet."""
    sent_hashes = state.get("sent_learning_hashes", {})
    new_learnings = []

    if not LEARNINGS_PENDING_DIR.is_dir():
        return new_learnings

    for f in sorted(LEARNINGS_PENDING_DIR.glob("*.md")):
        if not f.is_file():
            continue

        file_hash = _hash_learning_file(f)
        if file_hash in sent_hashes:
            continue

        text = f.read_text(errors="replace")
        meta = _parse_learning_frontmatter(text)
        title = meta["title"] or _extract_heading_title(text) or f.stem.replace("-", " ").title()

        new_learnings.append({
            "file": f.name,
            "path": str(f),
            "hash": file_hash,
            "title": title,
            "type": meta["type"],
            "preview": text[:1000],
            "size": f.stat().st_size,
        })

        if len(new_learnings) >= MAX_LEARNINGS_IN_REPORT:
            break

    return new_learnings


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
                    "SELECT COUNT(*), MAX(last_activity_at) FROM sessions WHERE last_activity_at > ?",
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
                pass  # expected — silently handled

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
        pass  # expected — silently handled
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
                print("expected — silently handled", file=sys.stderr)
    return default


def _build_auth_headers(url: str) -> dict[str, str]:
    """Build auth headers for the PGMQ bus.
    
    Primary: Basic auth via CORTEX_BASIC_AUTH (or CORTEX_BUS_AUTH).
    Fallback: Bearer token via CORTEX_BUS_TOKEN (for local/bare PGMQ)."""
    import base64
    basic = _resolve_env("CORTEX_BASIC_AUTH") or _resolve_env("CORTEX_BUS_AUTH")
    if basic and ":" in basic:
        encoded = base64.b64encode(basic.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}
    token = _resolve_env("CORTEX_BUS_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def send_report(report: dict, dry_run: bool = False) -> list[str] | None:
    """Send learning report to Moses via PGMQ bus.

    Returns list of file paths that were successfully sent (learning files),
    or None on send failure. Empty list = sent OK but no learning files.
    """
    from urllib.request import Request, urlopen
    from urllib.error import URLError

    bus_url = (
        _resolve_env("CORTEX_BUS_URL") or
        _resolve_env("CORTEX_BUS_FALLBACK_URL") or
        ""
    )
    if not bus_url:
        return []  # No bus configured — silent. Health pipeline handles this.

    bus_url = bus_url.rstrip("/")
    hostname = AGENT_NAME

    # Build message
    skills = report.get("skills", [])
    lessons = report.get("lessons", [])
    stats = report.get("sessions", {})
    learnings = report.get("learnings", [])

    lines = []
    lines.append(f"━━━ Learning Report — {hostname} ━━━")
    lines.append(f"Generated: {report.get('generated', '')}")
    has_content = bool(skills) or bool(lessons) or bool(learnings)
    lines.append(f"Type: full" if has_content else "Type: heartbeat")
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

    if learnings:
        lines.append(f"\n== Learnings ({len(learnings)} pending) ==")
        for lrn in learnings[:MAX_LEARNINGS_IN_REPORT]:
            tag = {"discovery": "💡", "lesson": "📘", "improvement": "🔧"}.get(lrn['type'], "📄")
            lines.append(f"  {tag} [{lrn['type']}] {lrn['title']}")
            lines.append(f"    {lrn['preview'][:300]}")

    # Truncate to bus limit
    body_text = "\n".join(lines)
    if len(body_text) > MAX_REPORT_CHARS:
        body_text = body_text[:MAX_REPORT_CHARS] + "\n... [truncated]"

    # Build subject line
    subject_parts = []
    if skills:
        subject_parts.append(f"{len(skills)} skills")
    if lessons:
        subject_parts.append(f"{len(lessons)} lessons")
    if learnings:
        subject_parts.append(f"{len(learnings)} learnings")
    subject = "Learning Report: " + (", ".join(subject_parts) if subject_parts else "heartbeat")

    payload = {
        "queue": "inbox_orchestrator",
        "message": json.dumps({
            "from": hostname,
            "subject": subject,
            "body": json.dumps({
                "topic": "reports",
                "text": body_text,
            }),
            "priority": "high" if (skills or learnings) else "normal",
        }),
    }

    # Collect file paths to return on success
    sent_files = [lrn["path"] for lrn in learnings] if learnings else []

    if dry_run:
        print(f"[DRY RUN] Would send to {bus_url}")
        print(f"  Subject: {payload['message']['subject']}")
        print(f"  Body: {len(body_text)} chars")
        return sent_files if sent_files else ["(dry-run)"]

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
        print(f"Sent: {subject} (msg_id={str(msg_id)[:8]})", flush=True)
        return sent_files
    except URLError as e:
        body = ""
        if hasattr(e, 'read'):
            try:
                body = e.read().decode()[:200]
            except Exception:
                body = str(e)
        print(f"ERR: Send failed: {getattr(e, 'code', '?')} {body}", file=sys.stderr, flush=True)
        return None
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERR: Send failed: {e}", file=sys.stderr, flush=True)
        return None


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

    # Self-heal: ensure the learnings dirs exist. Agents write ad-hoc
    # learnings to ~/brain/learnings/pending/ during sessions; the dir may
    # not exist on fresh installs. Creating it here means every fleet agent
    # bootstraps it on the next collector tick (runs every 6h).
    try:
        LEARNINGS_PENDING_DIR.mkdir(parents=True, exist_ok=True)
        LEARNINGS_SENT_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # silent — watchdog pattern; next tick retries

    state = load_state()
    t0 = time.time()

    # Phase 0: Session mining is handled by a separate overnight cron
    # (agent-session-mine) — it dumps mined lessons into ~/brain/lessons/
    # which _get_lesson_delta() picks up instantly here.

    # Phase 1: Collect
    skills_delta = _get_skill_delta(state)
    lessons_delta = _get_lesson_delta(state)
    pending_learnings = _get_pending_learnings(state)
    session_stats = _get_session_stats()
    agent_ctx = _get_agent_context()

    # Phase 2: Decide if there's something to report
    has_data = bool(skills_delta) or bool(lessons_delta) or bool(pending_learnings)
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
        "learnings": pending_learnings,
        "is_heartbeat": not has_data and is_heartbeat_due,
    }

    # Phase 4: Send
    # None = send failed (bus unreachable) — do NOT save state so the delta
    # is retried next run. [] = sent OK but no learning files.
    sent_files = send_report(report, dry_run=dry_run)
    # ⚠️ dry-run must NOT count as "sent": the dry-run path returns a non-None
    # sentinel (["(dry-run)"]), which would otherwise persist state and
    # swallow the pending delta. Verified 2026-08-05: a --dry-run at 04:04
    # consumed a real 60-lesson delta that the 06:00 run then never sent.
    send_ok = sent_files is not None and not dry_run

    # Phase 5: Post-send cleanup — move sent learning files to sent/ dir
    if sent_files and not dry_run:
        LEARNINGS_SENT_DIR.mkdir(parents=True, exist_ok=True)
        sent_hashes = state.get("sent_learning_hashes", {})
        for fpath in sent_files:
            src = Path(fpath)
            if not src.exists():
                continue
            dest = LEARNINGS_SENT_DIR / src.name
            # Avoid overwriting: append timestamp if conflict
            if dest.exists():
                stem = src.stem
                ts = datetime.now().strftime("%Y%m%d%H%M%S")
                dest = LEARNINGS_SENT_DIR / f"{stem}-{ts}.md"
            src.rename(dest)
            # Record hash so we don't re-send if agent recreates same content
            sent_hashes[_hash_learning_file(dest)] = src.name
        state["sent_learning_hashes"] = sent_hashes

    # Phase 6: Save state (only if successfully sent or dry run)
    # NOTE: sent_files is only non-empty when learnings were sent. When only
    # skills/lessons changed (no learnings), sent_files is [] — so the old
    # `if sent_files or dry_run` skipped saving, and skill_hashes/lesson_count
    # never persisted → the SAME delta re-sent every 6h (verified 2026-08-03:
    # "20 skills, 297 lessons" identical since 07-28). Save whenever a report
    # was actually sent (has_data or heartbeat) AND the send succeeded.
    if send_ok:
        state["last_run"] = t0
        # Skill hashes were updated inside _get_skill_delta
        # Lesson count was updated inside _get_lesson_delta
        save_state(state)

    if not sent_files and not dry_run:
        # Bus unreachable is expected when no local bus is configured.
        # Don't exit non-zero — health pipeline handles bus alerts.
        pass


if __name__ == "__main__":
    main()
