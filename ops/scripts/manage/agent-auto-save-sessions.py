#!/usr/bin/env python3
"""Unified auto-save: discover active projects from session DB, archive to each."""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone, timedelta

HERMES_DB = os.path.expanduser("~/.hermes/state.db")
SESSION_WINDOW_HOURS = 72  # how far back to consider "active"

KST = timezone(timedelta(hours=9))
NOW = datetime.now(KST)
NOW_TS = NOW.timestamp()


def kst(ts: float) -> str:
    """Format unix timestamp as KST string."""
    dt = datetime.fromtimestamp(ts, tz=KST)
    return dt.strftime("%Y-%m-%d %H:%M KST")


def kst_slug() -> str:
    return NOW.strftime("%Y%m%d-%H%M%S")


def get_active_cwds(db_path: str, hours: int) -> list[dict]:
    """Return list of {cwd, session_count, last_seen, sessions} for active projects."""
    if not os.path.isfile(db_path):
        print(f"ERROR: DB not found: {db_path}")
        return []

    cutoff = NOW_TS - hours * 3600

    # Retry guard: the live gateway state.db can transiently raise
    # 'database disk image is malformed' during a concurrent write/checkpoint.
    # Retry the whole read a few times before giving up.
    import time

    last_err = None
    for attempt in range(4):
        try:
            return _read_active_cwds(db_path, cutoff)
        except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    print(f"ERROR: persistent DB read failure after retries: {last_err}")
    return []


def _read_active_cwds(db_path: str, cutoff: float) -> list[dict]:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get unique cwds with activity in window
    cur.execute(
        """
        SELECT cwd, COUNT(*) as session_count,
               MAX(started_at) as last_seen,
               MAX(ended_at) as last_ended
        FROM sessions
        WHERE cwd IS NOT NULL
          AND cwd != ''
          AND started_at > ?
        GROUP BY cwd
        ORDER BY COUNT(*) DESC
        """,
        (cutoff,),
    )
    rows = cur.fetchall()

    results = []
    for r in rows:
        cwd = r["cwd"]
        # Skip the hermes-agent internal directory
        if ".hermes" in cwd and "hermes-agent" in cwd:
            continue
        if not os.path.isdir(cwd):
            continue

        # Get individual session summaries
        cur2 = conn.cursor()
        cur2.execute(
            """
            SELECT id, title, datetime(started_at, 'unixepoch') as started,
                   datetime(ended_at, 'unixepoch') as ended,
                   message_count, input_tokens, output_tokens, cwd
            FROM sessions
            WHERE cwd = ?
              AND started_at > ?
            ORDER BY started_at DESC
            LIMIT 20
            """,
            (cwd, cutoff),
        )
        sessions = [dict(s) for s in cur2.fetchall()]
        cur2.close()

        results.append({
            "cwd": cwd,
            "session_count": r["session_count"],
            "last_seen": r["last_seen"],
            "last_ended": r["last_ended"],
            "sessions": sessions,
        })

    conn.close()
    return results


def project_name_from_cwd(cwd: str) -> str:
    """Derive a short project name from the cwd path."""
    return os.path.basename(cwd)


def has_hermes_cortex(cwd: str) -> bool:
    """Check if the project has .hermes-cortex/ directory."""
    return os.path.isdir(os.path.join(cwd, ".hermes-cortex"))


def ensure_archive_dir(cwd: str):
    """Create .hermes-cortex/sessions/archive/ if needed. Return path or None."""
    archive = os.path.join(cwd, ".hermes-cortex", "sessions", "archive")
    try:
        os.makedirs(archive, exist_ok=True)
        return archive
    except OSError as e:
        print(f"  WARN: cannot create archive dir {archive}: {e}")
        return None


def get_git_summary(cwd: str) -> str:
    """Get a one-line git status summary."""
    lines = []
    try:
        # Last 3 commits
        log = subprocess.run(
            ["git", "log", "--oneline", "-3", "--no-decorate"],
            capture_output=True, text=True, cwd=cwd, timeout=10,
        )
        if log.returncode == 0 and log.stdout.strip():
            lines.append("### Recent Commits")
            for line in log.stdout.strip().split("\n"):
                lines.append(f"- `{line.split()[0]}` {' '.join(line.split()[1:])}")
    except Exception:
        lines.append("  (git log unavailable)")

    try:
        # Working tree status
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, cwd=cwd, timeout=10,
        )
        if status.returncode == 0:
            dirty = [s for s in status.stdout.strip().split("\n") if s]
            if dirty:
                modified = sum(1 for s in dirty if s.startswith(" M") or s.startswith("M "))
                untracked = sum(1 for s in dirty if s.startswith("??"))
                lines.append(f"### Working Tree\n- {len(dirty)} dirty files "
                             f"({modified} modified, {untracked} untracked)")
            else:
                lines.append("### Working Tree\n- Clean ✅")
    except Exception:
        lines.append("  (git status unavailable)")

    return "\n".join(lines)


def write_archive(project: dict):
    """Write a session archive file. Returns path or None."""
    cwd = project["cwd"]
    name = project_name_from_cwd(cwd)
    archive_dir = ensure_archive_dir(cwd)
    if not archive_dir:
        print(f"  SKIP {name} — no .hermes-cortex (or inaccessible)")
        return None

    slug = kst_slug()
    filename = f"{slug}_auto-save.md"
    filepath = os.path.join(archive_dir, filename)

    sessions = project["sessions"]

    # Build content
    content = [f"# Session Archive — {name}"]
    content.append(f"**Auto-saved**: {kst(NOW_TS)}")
    content.append(f"**Activity window**: last {SESSION_WINDOW_HOURS}h")
    content.append(f"**Total sessions**: {project['session_count']}")
    content.append(f"**Last session**: {kst(project['last_seen'])}")
    content.append("")

    # Individual sessions
    content.append("## Recent Sessions")
    for i, s in enumerate(sessions, 1):
        started = s.get("started", "?")[:16]
        ended = s.get("ended", "?")[:16] if s.get("ended") else "ongoing"
        title = s.get("title") or "(untitled)"
        msg_count = s.get("message_count", 0)
        inp_tok = s.get("input_tokens", 0)
        out_tok = s.get("output_tokens", 0)
        content.append(f"{i}. **{title}** — {started} → {ended}")
        content.append(f"   - Messages: {msg_count} | Input tokens: {inp_tok} | Output tokens: {out_tok}")

    content.append("")
    git_section = get_git_summary(cwd)
    if git_section:
        content.append("## Git Status")
        content.append(git_section)

    content.append("")
    content.append("---")
    content.append(f"*Auto-saved by unified cron at {kst(NOW_TS)}*")

    try:
        with open(filepath, "w") as f:
            f.write("\n".join(content) + "\n")
        return filepath
    except OSError as e:
        print(f"  ERROR writing {filepath}: {e}")
        return None


def main():
    active = get_active_cwds(HERMES_DB, SESSION_WINDOW_HOURS)

    if not active:
        sys.exit(0)

    results = []
    for project in active:
        name = project_name_from_cwd(project["cwd"])
        if not has_hermes_cortex(project["cwd"]):
            results.append({"name": name, "status": "skipped"})
            continue

        path = write_archive(project)
        if path:
            slug = os.path.basename(path)
            print(f"{name} -> {slug}")
            results.append({"name": name, "status": "archived", "path": path})
        else:
            results.append({"name": name, "status": "failed"})

    # Summary line
    archived = [r for r in results if r["status"] == "archived"]
    skipped = [r for r in results if r["status"] == "skipped"]
    failed = [r for r in results if r["status"] == "failed"]
    print(f"Summary: {len(archived)} archived, {len(skipped)} skipped, {len(failed)} failed")

    # Machine-readable summary (for Moses / monitoring)
    summary = {
        "timestamp": kst(NOW_TS),
        "window_hours": SESSION_WINDOW_HOURS,
        "active_projects": len(active),
        "archived": len(archived),
        "skipped": [r["name"] for r in skipped],
        "failed": [r["name"] for r in failed],
    }
    summary_path = os.path.expanduser(f"~/.hermes/cron/output/auto-save-sessions-summary.json")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)


if __name__ == "__main__":
    main()
