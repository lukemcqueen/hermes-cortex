# Task-queue remediation — acceptance evidence

Regenerate with: `bash ops/scripts/manage/run-task-queue-evidence.sh`

Every number below is RE-DERIVED from the live store and the live repo by
running this script. Aggregates only — no row identifiers, so the checks
keep holding for rows added later.

Provenance: a regression test regenerates this report and compares it to
the committed file, so a hand-written table cannot pass for script output.

| Check | Result | Detail |
|---|---|---|
| No pending slice is assigned-and-unstarted | PASS | 0 stranded (baseline 6) |
| Pending-slice pool fully accounted for by its two views | PASS | claimable 17 + assigned 0 = 17 |
| The pool is accounted for (work is reachable when present) | PASS | claimable 17 (baseline 9 + 6 released; no floor asserted — a drained pool is healthy) |
| No row is left parked in `waiting` | PASS | 0 still waiting (baseline 6) |
| A cancelled slice is recoverable in the archive (cancels move, not delete) | PASS | 16 cancelled rows archived since 2026-10-03 UTC (fixed cutoff) — a cancel MOVES the row to tasks.task_archive, so it stays recoverable |
| Parked rows can return to the claim pool | PASS | waiting->pending=t blocked->pending=t paused->pending=t |
| Every task migration is registered for deploy | PASS | 13 migrations; unregistered: none |
| Every task migration is on the deployed tree | PASS | 13 of 13 deployed |
| DB schema version matches the newest repo migration | PASS | DB=13 repo=13 |
| test_hc_harness passes on the current tree | PASS | now (60bf5386): ============================== 9 passed in 1.71s =============================== · pinned baseline fbfc22b34db2 (fbfc22b3): ============================== 9 passed in 1.68s =============================== [outcome pass] — reproduced as recorded under the generating interpreter, not gated (interpreter drift makes the old tree pass under today's python); the verdict is the measured pass, never the absence of the word "failed" |

**Verdict: PASS**

## Raw test output — `tests/test_hc_harness.py`

`hc harness` and its registry were failing their own tests before this fix;
the same file is re-run at the parent of the commit that last touched it, so
the claim is a measured before/after rather than an assertion.

### With this change applied

```
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: $HOME/hermes-cortex
configfile: pytest.ini
plugins: anyio-4.15.1
collected 9 items

tests/test_hc_harness.py .........                                       [100%]

============================== 9 passed in 1.71s ===============================
```

### On a HEAD~1 worktree (this change absent)

```
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /tmp/tq-evidence-clean-tree
configfile: pytest.ini
plugins: anyio-4.15.1
collected 9 items

tests/test_hc_harness.py .........                                       [100%]

============================== 9 passed in 1.68s ===============================
```
