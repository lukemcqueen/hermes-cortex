#!/usr/bin/env python3
"""Static Alembic migration-head checker.

Fail-fast integrity check for a repo's migration chain, meant to run at
PR/merge time and inside `./run build` — NEVER auto-merge multiple heads.
Auto-merging inside a container produces ephemeral state that disappears on
rebuild and, worse, can generate corrupt merge files with `revision = None`,
which crash every subsequent Alembic operation with:
    TypeError: 'NoneType' object is not iterable

Checks (all static — no DB, no import of alembic required):
  1. Exactly one migration head (a revision that no other revision lists
     as its down_revision). More than one ⇒ exit 1 with fix instructions.
  2. Every `revision` id is ≤ 32 chars (Alembic's hard limit).

Usage:
    python3 check-alembic-heads.py [PATH_TO_ALEMBIC_VERSIONS]

    PATH_TO_ALEMBIC_VERSIONS   dir containing the migration .py files
                               (default: alembic/versions)

Exit codes:
    0  OK — single head, all revision ids valid
    1  multiple heads OR an over-length revision id

Notes:
    - Pure static analysis via regex, so it never needs `alembic` installed
      or a configured alembic.ini/DATABASE_URL. Runs anywhere.
    - Uses re.DOTALL so multiline `down_revision` tuples (two parents spread
      across lines) parse correctly.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REVISION_RE = re.compile(
    r"^revision\s*(?::\s*[^=]+)?\s*=\s*(['\"])(?P<id>[^'\"]+)\1\s*$",
    re.MULTILINE,
)
# down_revision can be: 'xxxx', None, or ('aaaa', 'bbbb') possibly spanning
# multiple lines. DOTALL lets the group cross newlines.
DOWN_REVISION_RE = re.compile(
    r"^down_revision\s*(?::\s*[^=]+)?\s*=\s*(?P<value>"
    r"None"
    r"|['\"][^'\"]+['\"]"
    r"|\([^)]*\)"
    r")\s*$",
    re.MULTILINE | re.DOTALL,
)

MAX_REVISION_LEN = 32


def parse_down_revision(value: str) -> list[str]:
    """Return the list of parent revision ids referenced by a down_revision value.

    Handles: None, 'single_id', and ('a', 'b') tuples — including tuples
    split across multiple lines (inner whitespace/newlines stripped).
    """
    value = value.strip()
    if value == "None" or not value:
        return []
    # Strip surrounding parens for a tuple, then split on commas.
    if value.startswith("("):
        value = value[1:-1]
    parts = re.split(r",", value)
    ids: list[str] = []
    for part in parts:
        part = part.strip().strip("'\"").strip()
        if part:
            ids.append(part)
    return ids


def check_versions_dir(versions_dir: Path) -> int:
    if not versions_dir.is_dir():
        print(f"✗ Versions dir not found: {versions_dir}")
        return 1

    files = sorted(versions_dir.glob("*.py"))
    if not files:
        print(f"✗ No migration files found in {versions_dir}")
        return 1

    revisions: dict[str, set[str]] = {}  # revision_id -> set(parent ids)
    errors: list[str] = []
    revision_sources: dict[str, Path] = {}

    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"{f.name}: cannot read: {exc}")
            continue

        rev_m = REVISION_RE.search(text)
        if not rev_m:
            # Some files in versions/ may be helpers, not revisions — skip
            # anything that doesn't declare a revision id.
            continue
        rev_id = rev_m.group("id")
        revision_sources[rev_id] = f

        if len(rev_id) > MAX_REVISION_LEN:
            errors.append(
                f"{f.name}: revision id '{rev_id}' is {len(rev_id)} chars "
                f"(max {MAX_REVISION_LEN})"
            )

        down_m = DOWN_REVISION_RE.search(text)
        parents = parse_down_revision(down_m.group("value")) if down_m else []
        revisions[rev_id] = set(parents)

    if errors:
        for e in errors:
            print(f"✗ {e}")
        return 1

    if not revisions:
        print(f"✗ No migration revisions found in {versions_dir}")
        return 1

    # Heads = revisions that no other revision references as a parent.
    referenced: set[str] = set()
    for parents in revisions.values():
        referenced.update(parents)
    heads = [r for r in revisions if r not in referenced]

    if len(heads) != 1:
        print(f"✗ {len(heads)} Alembic heads detected: {sorted(heads)}")
        for h in sorted(heads):
            src = revision_sources.get(h)
            print(f"    {h}  ({src.name if src else 'unknown source'})")
        print("  Fix: alembic merge heads -m 'merge' (or rebase your branch).")
        print("  Do NOT auto-merge at container start — run this at PR/merge time.")
        return 1

    print(f"✓ single head: {heads[0]}")
    n = len(revisions)
    print(f"✓ {n} migration revision(s), all ids ≤ {MAX_REVISION_LEN} chars")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    target = argv[0] if argv else "alembic/versions"
    versions_dir = Path(target).expanduser()
    return check_versions_dir(versions_dir)


if __name__ == "__main__":
    sys.exit(main())
