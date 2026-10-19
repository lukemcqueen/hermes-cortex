#!/usr/bin/env python3
"""Retag the 18 derivable rows and prove nothing else moved (cycle 13350).

Sequence, all through the sanctioned write path (`task-db.py restore` →
tasks.task_upsert()):
  1. snapshot the ids' full state to a file
  2. census by repo (before)
  3. run the restore (probe row first — it was already applied and verified
     separately, so the batch re-runs it and reports 0 changed for it)
  4. census by repo (after)
  5. re-read every id and assert ONLY `repo` differs from the snapshot

Usage: python3 verify-retag.py --snapshot|--verify [--json <file>]
Exit: 0 ok · 1 a field moved that should not have · 2 could not verify
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
TASK_DB = REPO / "ops" / "scripts" / "manage" / "task-db.py"

#: Every column a restore could touch, plus the identity fields it must not.
COLUMNS = ("id", "content", "created_by", "assignee", "project", "repo", "target",
           "scope", "status", "priority", "source", "session_id", "parent_id",
           "kind", "correlation_id", "due", "tags", "depends_on", "plan")
#: Fields allowed to differ between the snapshot and the re-read.
ALLOWED_CHANGES = {"repo"}


def _load():
    spec = importlib.util.spec_from_file_location("tdb_verify", TASK_DB)
    if spec is None or spec.loader is None:
        sys.exit(2)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sql_array(col: str) -> str:
    return f"COALESCE(array_to_string({col}, chr(31)), '')"


def read_rows(tdb, ids: list[str]) -> dict[str, dict]:
    sel = ", ".join(
        [f"t.{c}::text" for c in COLUMNS if c not in ("tags", "depends_on")] +
        [_sql_array("t.tags"), _sql_array("t.depends_on")])
    raw = tdb.psql(f"SELECT {sel} FROM tasks.tasks t "
                   "WHERE t.id = ANY(ARRAY[?]::uuid[]) ORDER BY t.id;", [ids])
    out: dict[str, dict] = {}
    for line in (raw or "").splitlines():
        parts = line.split("||")
        if len(parts) != len(COLUMNS):
            print(f"COULD NOT VERIFY: row shape {len(parts)} != {len(COLUMNS)}",
                  file=sys.stderr)
            sys.exit(2)
        out[parts[0]] = dict(zip(COLUMNS, parts))
    return out


def census(tdb) -> list[str]:
    raw = tdb.psql("SELECT COALESCE(t.repo, '(untagged)'), count(*) "
                   "FROM tasks.tasks t GROUP BY 1 ORDER BY 2 DESC;")
    return [line.replace("||", "  ") for line in (raw or "").splitlines()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", default=str(HERE / "retag.json"))
    ap.add_argument("--state", default=str(HERE / "retag-before.json"))
    args = ap.parse_args()

    tdb = _load()
    items = json.loads(Path(args.json).read_text())
    ids = [i["id"] for i in items]
    print(f"rows in {Path(args.json).name}: {len(ids)}")

    if args.snapshot:
        print("\n=== census BEFORE (repo | count) ===")
        for line in census(tdb):
            print("  " + line)
        rows = read_rows(tdb, ids)
        Path(args.state).write_text(json.dumps(rows, indent=2) + "\n")
        print(f"\nsnapshot: {len(rows)} row(s) -> {Path(args.state).name}")
        return 0 if len(rows) == len(ids) else 2

    if args.apply:
        r = subprocess.run([sys.executable, str(TASK_DB), "restore", args.json],
                           capture_output=True, text=True, timeout=120)
        print(r.stdout.strip() or r.stderr.strip())
        return r.returncode

    if args.verify:
        before = json.loads(Path(args.state).read_text())
        after = read_rows(tdb, ids)
        print("\n=== census AFTER (repo | count) ===")
        for line in census(tdb):
            print("  " + line)
        missing = [i for i in ids if i not in after]
        if missing:
            print(f"COULD NOT VERIFY: {len(missing)} row(s) unreadable after", file=sys.stderr)
            return 2
        print("\n=== per-row diff (only `repo` may differ) ===")
        moved, bad = [], []
        for i in ids:
            diffs = {c: (before[i][c], after[i][c]) for c in COLUMNS
                     if before[i][c] != after[i][c]}
            unexpected = {c: v for c, v in diffs.items() if c not in ALLOWED_CHANGES}
            tag = diffs.get("repo")
            print(f"  {i[:8]}  repo {tag[0] or '(null)'} -> {tag[1] or '(null)'}"
                  if tag else f"  {i[:8]}  repo UNCHANGED ({after[i]['repo'] or '(null)'})")
            if tag and (tag[1] or "") != "hermes-cortex":
                bad.append((i, "wrong target label", tag))
            if unexpected:
                bad.append((i, "unexpected field change", unexpected))
            moved.append(i)
        print(f"\nrows re-read: {len(moved)}")
        if bad:
            for i, why, detail in bad:
                print(f"  FAIL {i[:8]}: {why} {detail}")
            return 1
        print("PASS: every row re-read; no field outside `repo` changed")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
