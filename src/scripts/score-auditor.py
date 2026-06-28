#!/usr/bin/env python3
"""
score-auditor.py — no_agent watchdog: flag unscored file changes

Watchdog pattern:
  Empty stdout → silent (all changes scored)
  Text output  → delivered to user (unscored changes found)

Scans repos under ~/Developer/ for files modified in the last N hours,
cross-references against the loop-governance DB, and reports any that
don't have a corresponding score-cycle entry.

QUIET when nothing to report — only produces output when unscored
changes are detected.
"""
import json, os, subprocess, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from state_tracker import StateTracker

# ── Config ──────────────────────────────────────────────────
LOOKBACK_HOURS = int(os.environ.get("SCORE_AUDITOR_LOOKBACK", "24"))
MAX_FILES_SHOWN = 15
DB_PATH = os.path.expanduser(
    os.environ.get(
        "SCORE_DB_PATH",
        "~/.hermes/data/loop-governance.db"
    )
)
SCANNED_DIRS = [
    os.path.expanduser("~/Developer"),
    os.path.expanduser("~/hermes-cortex"),
]
EXCLUDE_PATTERNS = [
    "__pycache__", ".venv", "node_modules", ".git",
    ".hermes", ".hermes-cortex", ".next", "target",
    "vendor", ".bun", ".cache", "go/pkg",
    "test-results", "playwright-report",
]

# ── Helpers ──────────────────────────────────────────────────
HOME = os.path.expanduser("~")

def should_exclude(path: str) -> bool:
    """Check if path should be excluded from scanning."""
    parts = path.split(os.sep)
    return any(p in parts for p in EXCLUDE_PATTERNS)

def find_recent_files() -> list[dict]:
    """Find files modified in the lookback window across scanned dirs."""
    cutoff = time.time() - (LOOKBACK_HOURS * 3600)
    results = []

    for scan_dir in SCANNED_DIRS:
        if not os.path.isdir(scan_dir):
            continue

        try:
            for root, dirs, files in os.walk(scan_dir):
                # Prune excluded directories
                dirs[:] = [d for d in dirs if d not in EXCLUDE_PATTERNS
                           and not d.startswith(".git")
                           and d not in ["node_modules", "__pycache__",
                                         ".venv", ".next", "target",
                                         "vendor", ".bun"]]

                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        mtime = os.path.getmtime(fpath)
                        if mtime < cutoff:
                            continue
                        # Only track source-like files
                        ext = os.path.splitext(fname)[1].lower()
                        if ext not in (
                            ".py", ".js", ".ts", ".tsx", ".jsx", ".rb",
                            ".go", ".rs", ".java", ".kt", ".sh", ".bash",
                            ".yaml", ".yml", ".json", ".toml", ".cfg",
                            ".md", ".html", ".css", ".scss", ".sql",
                            ".plist", ".conf", ".env.example", ".gitignore",
                        ):
                            continue

                        # Check git tracking — only flag tracked files
                        repo_root = _find_git_root(root)
                        if repo_root:
                            rel = os.path.relpath(fpath, repo_root)
                            # Check if tracked in git
                            r = subprocess.run(
                                ["git", "-C", repo_root, "ls-files",
                                 "--error-unmatch", rel],
                                capture_output=True, text=True, timeout=5
                            )
                            if r.returncode != 0:
                                continue  # untracked file

                            # Skip files that match HEAD — they were pulled,
                            # not locally edited. Only flag dirty files.
                            r2 = subprocess.run(
                                ["git", "-C", repo_root, "diff", "--quiet",
                                 "HEAD", "--", rel],
                                capture_output=True, timeout=5,
                            )
                            if r2.returncode == 0:
                                continue  # clean vs HEAD → pulled, skip

                        results.append({
                            "path": fpath.replace(HOME, "~"),
                            "mtime": datetime.fromtimestamp(mtime,
                                                           tz=timezone.utc),
                            "repo": os.path.basename(repo_root) if repo_root
                                    else "unknown",
                        })
                    except (OSError, subprocess.TimeoutExpired):
                        continue
        except (OSError, PermissionError):
            continue

    return results

def _find_git_root(path: str) -> str | None:
    """Walk up from path to find .git directory."""
    p = Path(path)
    for parent in [p] + list(p.parents):
        if (parent / ".git").exists():
            return str(parent)
    return None

def get_scored_tasks() -> set[str]:
    """Get task IDs from the loop-governance DB."""
    if not os.path.exists(DB_PATH):
        return set()

    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        # Try different possible table schemas
        tables = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]

        if "cycles" in table_names:
            rows = cur.execute(
                "SELECT DISTINCT task_id FROM cycles"
            ).fetchall()
        elif "cycle_scores" in table_names:
            rows = cur.execute(
                "SELECT DISTINCT task_id FROM cycle_scores"
            ).fetchall()
        else:
            return set()

        conn.close()
        return {r[0] for r in rows if r[0]}
    except Exception:
        return set()

# ── Main ─────────────────────────────────────────────────────
def main() -> None:
    recent = find_recent_files()
    if not recent:
        return  # silent exit — nothing changed

    scored = get_scored_tasks()
    unscored: list[dict] = []
    now = datetime.now(timezone.utc)

    for f in recent:
        # Build expected task id patterns
        age_hours = (now - f["mtime"]).total_seconds() / 3600
        # If file was modified more than LOOKBACK_HOURS ago, skip
        if age_hours > LOOKBACK_HOURS:
            continue

        # Check if ANY scored task mentions this repo/file
        repo = f["repo"]
        basename = os.path.basename(f["path"])
        found = False
        for task_id in scored:
            if repo in task_id or basename in task_id:
                found = True
                break

        if not found:
            unscored.append(f)

    if not unscored:
        # Clear prior error state
        StateTracker("score-auditor").evaluate("healthy", has_issues=False)
        return  # silent — all changes accounted for

    # State tracking — suppress duplicates
    hostname = os.uname().nodename.split(".")[0]
    fp = f"host={hostname}|count={len(unscored)}"
    action = StateTracker("score-auditor").evaluate(fp)

    if action == "silent":
        return  # same unscored count as last time

    # ── Report ──
    ts = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST")
    print(f"[{ts}] [score-auditor] {hostname} — {len(unscored)} unscored change(s)")
    print(f"  Lookback: {LOOKBACK_HOURS}h  |  DB: {DB_PATH}")
    print("")

    # Group by repo
    by_repo: dict[str, list[dict]] = {}
    for f in unscored:
        by_repo.setdefault(f["repo"], []).append(f)

    for repo_name, files in sorted(by_repo.items()):
        print(f"  📁 {repo_name}/ ({len(files)} files)")
        shown = files[:MAX_FILES_SHOWN]
        for f in shown:
            mtime_local = f["mtime"].strftime("%H:%M %Z")
            print(f"      {f['path']}  ({mtime_local})")
        remaining = len(files) - MAX_FILES_SHOWN
        if remaining > 0:
            print(f"      … and {remaining} more file(s)")
        print("")

    print("  💡 Score them: score-cycle --task <task-id> ...")
    print("  💡 Or ignore:   add to AGENTS.md or lesson DB")
    print("")

    # Exit 0 — watchdog pattern (output is the message)
    # Exit non-zero if we want the system to flag this as an error
    sys.exit(0)

if __name__ == "__main__":
    main()
