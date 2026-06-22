#!/usr/bin/env python3
"""Check Alembic migrations for:
   1. Multiple heads (forks) — exit 1 if found.
   2. Revision IDs longer than 32 chars — exit 1 if found
      (alembic_version.version_num is varchar(32)).

Uses re.DOTALL to correctly parse multiline down_revision tuples
(merge revisions with two parents spread across multiple lines).
"""

import re
import sys
from pathlib import Path

migrations_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("alembic/versions")

children_of: dict[str, list[str]] = {}  # parent -> [child revisions]
all_revs: set[str] = set()
long_revs: list[str] = []

for path in sorted(migrations_dir.glob("*.py")):
    content = path.read_text()
    rev_m = re.search(r'^revision(?::\s*\w+)?\s*=\s*[\'"]([a-zA-Z0-9_]+)[\'"]', content, re.MULTILINE)
    down_m = re.search(
        r'^down_revision(?::\s*.*?)?\s*=\s*(\(.*?\)|[\'"]([a-zA-Z0-9_]+)[\'"])',
        content,
        re.MULTILINE | re.DOTALL,
    )
    if not rev_m:
        continue
    rev_id = rev_m.group(1)
    all_revs.add(rev_id)

    # Check revision ID length
    if len(rev_id) > 32:
        long_revs.append(f"{path.name}: revision ID '{rev_id}' is {len(rev_id)} chars (max 32)")

    if down_m:
        parent_str = (down_m.group(1) or f"'{down_m.group(2)}'").strip()
        if parent_str.startswith("("):
            parent_str = parent_str.strip("()")
        parent_ids = [p.strip().strip("'\"") for p in parent_str.split(",") if p.strip()]
        for pid in parent_ids:
            children_of.setdefault(pid, []).append(rev_id)
        all_revs.update(parent_ids)

# Check 1: long revision IDs
if long_revs:
    print("ERROR: Migration revision ID(s) too long (max 32 chars for alembic_version.varchar(32)):")
    for msg in long_revs:
        print(f"  {msg}")
    print("Fix: rename the file and update the revision ID inside to <= 32 characters.")
    sys.exit(1)

# Check 2: multiple heads
all_keys = set(children_of.keys())
heads = sorted(all_revs - all_keys)

if len(heads) > 1:
    print(f"ERROR: {len(heads)} Alembic heads found: {', '.join(heads)}")
    print("Fix: create a merge migration (alembic merge heads -m 'merge heads')")
    sys.exit(1)

print(f"✓ Alembic: single head ({heads[0] if heads else 'none'}), all revision IDs within 32 chars")
sys.exit(0)
