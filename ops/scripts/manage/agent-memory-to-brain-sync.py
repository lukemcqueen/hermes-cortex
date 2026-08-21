#!/usr/bin/env python3
"""memory-to-brain-sync.py — Sync Hermes agent memory → shared brain (mycortex source)

Reads MEMORY.md and USER.md from the active Hermes profile,
formats them as searchable pages under ~/brain/shared/hermes-memory/,
then git-commits. The hermes-cortex source is ingested by mycortex
(the knowledge brain) like any local source.

Designed to run as a cron job alongside conversation export.
No mycortex binary or public.* table dependency (S-011 keep-rule).
"""

import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from hermes_tz import get_timezone

KST = get_timezone()

def _ts() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M %Z")

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
BRAIN_SHARED = Path.home() / "brain" / "shared"
MEMORY_DIR = Path(os.environ.get("HERMES_MEMORY_DIR", str(HERMES_HOME / "memories")))
OUT_DIR = BRAIN_SHARED / "hermes-memory"
ENTRY_DELIMITER = "\n§\n"


def read_entries(filepath: Path) -> list[str]:
    """Read a §-delimited memory file and return non-empty entries."""
    if not filepath.exists() or filepath.stat().st_size == 0:
        return []
    text = filepath.read_text(encoding="utf-8")
    entries = [e.strip() for e in text.split(ENTRY_DELIMITER) if e.strip()]
    return entries


def build_current_md(memory_entries: list[str], user_entries: list[str]) -> str:
    """Build the full markdown snapshot."""
    lines = [
        "---",
        "type: note",
        "tags: [hermes, memory, agent, automation]",
        "---",
        "",
        "# Hermes Agent Memory Snapshot",
        "",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
        "",
    ]

    if memory_entries:
        lines.append("## Agent Notes (MEMORY.md)")
        lines.append("")
        for entry in memory_entries:
            lines.append(entry)
            lines.append("")

    if user_entries:
        lines.append("---")
        lines.append("")
        lines.append("## User Profile (USER.md)")
        lines.append("")
        for entry in user_entries:
            lines.append(entry)
            lines.append("")

    return "\n".join(lines)


def write_snapshot(content: str):
    """Write current snapshot and archived copy."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Current authoritative copy
    current_path = OUT_DIR / "current.md"
    current_path.write_text(content, encoding="utf-8")
    print(f"✓ Written: current.md ({len(content)} bytes)")

    # Monthly archive for history
    archive_dir = OUT_DIR / "archive" / datetime.now().strftime("%Y-%m")
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"
    archive_path.write_text(content, encoding="utf-8")
    print(f"✓ Archived: {archive_path}")


def git_commit():
    """Git commit in the shared brain repo so sync daemon picks it up."""
    if not (BRAIN_SHARED / ".git").exists():
        print(f"⚠  {BRAIN_SHARED} is not a git repo — skipping commit")
        return

    os.chdir(str(BRAIN_SHARED))
    subprocess.run(["git", "add", "hermes-memory/"], capture_output=True)

    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        capture_output=True,
    )
    if result.returncode == 0:
        print("No changes to commit")
        return

    msg = f"hermes-memory: auto-sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    subprocess.run(["git", "commit", "-m", msg], capture_output=True)
    print(f"✓ Git committed to shared brain")


def main():
    ts = _ts()
    print(f"[{ts}] memory-to-brain-sync: starting")

    memory_file = MEMORY_DIR / "MEMORY.md"
    user_file = MEMORY_DIR / "USER.md"

    if not memory_file.exists() and not user_file.exists():
        print(f"[{ts}] Neither MEMORY.md nor USER.md found — nothing to sync.")
        return

    memory_entries = read_entries(memory_file)
    user_entries = read_entries(user_file)
    print(f"  Memory entries: {len(memory_entries)}")
    print(f"  User entries: {len(user_entries)}")

    content = build_current_md(memory_entries, user_entries)
    write_snapshot(content)
    git_commit()

    print(f"[{_ts()}] memory-to-brain-sync: done")


if __name__ == "__main__":
    main()
