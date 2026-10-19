# PLAN — give `repo` an update surface (restore), then retag the derivable untagged rows

Operator question (2026-10-19): "for your untagged rows, why don't you properly
tag them to the proper repo?"

Cycle 13350 `task-repo-tag-backfill`.

## 1. Why they are untagged (measured)

`ops/scripts/manage/task-db.py::cmd_add` passes `repo` through to
`tasks.task_upsert` with no default; no caller in the fleet sets it. Measured
2026-10-19: 49 of 50 rows in `tasks.tasks` have `repo IS NULL`. Cycle 13347 made
scoped queries strict, so those rows are now invisible to a session inside a repo
unless it asks for them. Tagging them is the right fix: the tag is a fact about
the work, not about the session that wrote it.

## 2. The blocker: `repo` has NO update surface

- `task-db.py update <id> --status` takes status/reason/notify only — no `--repo`.
- `task-db.py restore <json>` IS the sanctioned metadata-correction path (used
  2026-10-16 to re-project 7 slices' `project`; evidence
  `docs/evidence/slice-project-reproject-2026-10-16.txt`) and writes through
  `tasks.task_upsert()`.
- BUT its SQL hard-wires NULL at position 6 (`p_repo`) —
  `task-db.py:1189-1198` (`NULL, NULL` immediately after `? project`):

      "SELECT tasks.task_upsert(?::uuid, ?, ?, NULL, ?, NULL, NULL, ?, ?, "
      "NULL, NULL, ?, NULL, NULL, ?, NULL, ?, ?::uuid, ?, NULL);"

  So restoring a row that HAS a repo would silently CLEAR it. The same NULL slots
  also clear assignee/target/due/tags/correlation_id. Retagging through restore
  today is impossible, and restore is a data-loss hazard for any tagged row.

## 3. Proposed change (code, one file)

`ops/scripts/manage/task-db.py`:

1. `cmd_restore` accepts an optional per-row `"repo"` key:
   - present -> validated with the existing `_check_name("--repo", ...)` allowlist
     and written (tag or retag);
   - absent -> **PRESERVE**: before writing, restore reads the current repo for the
     ids it is about to write in ONE query
     (`SELECT id, repo FROM tasks.tasks WHERE id = ANY(ARRAY[...])`) and passes the
     stored value. A row's tag is never cleared by a restore that did not mention it.
2. The printed summary reports `repo: N changed, M preserved`, so neither a silent
   no-op nor a silent mass-tag can happen unnoticed.
3. `assignee`/`target`/`due`/`tags` keep their current (clearing) behaviour in this
   cycle — recorded as a separate issue, so the diff stays narrow and reviewable.
4. Tests in `tests/test_task_db_unit.py` (hermetic, psql mocked):
   - restore with `repo` set writes that label;
   - restore WITHOUT the key writes the row's stored repo (the fake returns it);
   - a row whose stored repo is NULL and whose JSON omits the key writes NULL
     (unchanged behaviour, not a regression).

## 4. Data step (after the surface ships, same cycle)

Retag the 18 rows whose repo is DERIVABLE from the row's own text (each names a
hermes-cortex file, script, migration or pipeline):

    c579ef95 5e875477 40cb307d 511ad057 66914fe1 2fc4d871 f97dcffe 3cc049e8
    8369bc52 762379ca 482de205 a6bb2da4 9fb2ddb6 0f727dfd caed9076 cf8f8e8d
    736a496b aa054b3e        -> repo=hermes-cortex

Left untagged DELIBERATELY (not because it is easier):
- 16 KAESA/client rows (82310c5e, c711e28d, 4f099ae2, a40e0282, a512e32a,
  0008c2ce, 72dc920b, 00562f6c, ac53a833, 02c20c1a, 17471ede, cbba59f8, 5c2f135b,
  1d09760f, ca282975, 1e8737fc) — business content whose deliverables are documents,
  not a code repo; tagging them `hermes-cortex` would be a false claim. Awaiting the
  operator's answer on whether a `kaesa` label is wanted.
- 15 bare-token mint-residue rows (content `ISSUES`/`PROPOSAL`) — slice caed9076
  tracks that mint defect; they are cancels, not tags.

Method: probe ONE row first, read it back, then the remaining 17. Evidence
artifact carries before/after census by repo, the 18 ids, and a preservation check
(status/scope/source/priority/kind/created_by/parent_id unchanged).

## 5. Rejected

- **Raw SQL `UPDATE tasks.tasks SET repo=...`** — bypasses `tasks.task_upsert()`,
  the single write path (explicit rule on slice 9fb2ddb6).
- **A new `--repo` on `update <id>`** — a second surface beside restore's for the
  same column; two paths to one column is how they drift. Restore already exists
  and is the documented metadata-correction route.
- **Tagging everything with the session repo** (all NULL rows -> hermes-cortex) —
  the false-claim version of the same mistake; the 16 client rows and 15 junk rows
  are the proof it would be wrong.
- **Guessing a `kaesa` label** — a wrong tag silently reassigns ownership; the
  operator holds that decision.
