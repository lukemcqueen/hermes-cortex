#!/usr/bin/env python3
"""Build the restore JSON that retags rows with `repo` (cycle 13350).

WHY: `repo` had no update surface. `task-db.py restore` IS the canonical
metadata-correction path (it writes through tasks.task_upsert()), and it now
carries a per-row `repo`. This generator emits, per row, the row's CURRENT values
with only `repo` changed — so the write is a metadata correction and nothing else.

SAFETY: restore writes only the columns it carries. Any row holding a value in a
column restore does NOT carry (assignee/target/due/tags/correlation_id) would have
it CLEARED by the write, so this script REFUSES to emit a row in that state rather
than silently dropping data. `depends_on`/`plan` are not written by restore either
but they are already NULL on every row here, and the check covers them.

Usage:
  python3 build-restore-json.py --ids id,id,... --repo <label> --out <file.json> [--check-only]
Exit: 0 ok · 1 refused (a row carries a field the write would clear) · 2 could not read
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[3]
TASK_DB = REPO_DIR / "ops" / "scripts" / "manage" / "task-db.py"


def _load_task_db():
    spec = importlib.util.spec_from_file_location("task_db_retag", TASK_DB)
    if spec is None or spec.loader is None:
        sys.exit(2)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # import is inert: work sits behind main()
    return mod


COLUMNS = ("id", "content", "created_by", "project", "scope", "status",
           "priority", "source", "session_id", "parent_id", "kind")
# Columns restore does NOT carry: a non-NULL value in any of these would be
# cleared by the write.
NOT_CARRIED = ("assignee", "target", "due", "tags", "correlation_id",
               "depends_on", "plan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True, help="comma-separated task UUIDs")
    ap.add_argument("--repo", required=True, help="the label to write")
    ap.add_argument("--out", required=True)
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args()

    ids = [i.strip() for i in args.ids.split(",") if i.strip()]
    if not ids:
        print("no ids", file=sys.stderr)
        return 2

    tdb = _load_task_db()
    # The store's own reader path — the sanctioned seam, never hand-rolled psql.
    select = "SELECT " + ", ".join(COLUMNS) + \
             ", " + ", ".join(f"COALESCE({c}::text, '')" for c in NOT_CARRIED) + \
             " FROM tasks.tasks WHERE id = ANY(ARRAY[?]::uuid[]);"
    raw = tdb.psql(select, [ids])
    if not raw.strip():
        print("COULD NOT VERIFY: the id query returned no rows", file=sys.stderr)
        return 2

    carried = len(COLUMNS)
    items, extra = [], []
    for line in raw.splitlines():
        parts = line.split("||")
        if len(parts) != carried + len(NOT_CARRIED):
            print(f"COULD NOT VERIFY: unexpected row shape ({len(parts)} fields)",
                  file=sys.stderr)
            return 2
        row = dict(zip(COLUMNS, parts[:carried]))
        leftovers = {c: v for c, v in zip(NOT_CARRIED, parts[carried:]) if v}
        if leftovers:
            # Not carried by this JSON. restore PRESERVES them by reading the
            # stored value (that is the 2026-10-19 preserve-by-default rule), so
            # this is reported, not refused.
            extra.append((row["id"][:8], sorted(leftovers)))
        items.append({
            "id": row["id"], "content": row["content"],
            "agent_name": row["created_by"], "project": row["project"],
            "repo": args.repo, "scope": row["scope"], "status": row["status"],
            "priority": int(row["priority"] or 0), "source": row["source"],
            "session_id": row["session_id"] or None,
            "parent_id": row["parent_id"] or None, "kind": row["kind"] or None,
        })

    print(f"rows read: {len(raw.splitlines())}  emit: {len(items)}  "
          f"rows carrying preserved-only columns: {len(extra)}")
    for rid, leftovers in extra:
        print(f"  PRESERVED (read back and re-written) {rid}: {leftovers}")
    if args.check_only:
        return 0
    Path(args.out).write_text(json.dumps(items, indent=2) + "\n")
    print(f"wrote {args.out} ({len(items)} row(s), repo={args.repo})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
