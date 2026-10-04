# Task-queue remediation — acceptance evidence

Regenerate with: `bash ops/scripts/manage/run-task-queue-evidence.sh`

Every number below is RE-DERIVED from the live store and the live repo by
running this script. Aggregates only — no row identifiers, so the checks
keep holding for rows added later.

| Check | Result | Detail |
|---|---|---|
| No pending slice is assigned-and-unstarted | PASS | 0 stranded (baseline 6) |
| Pending-slice pool fully accounted for by its two views | PASS | claimable 16 + assigned 0 = 16 |
| The pool GREW by exactly the released slices (work is reachable again) | PASS | claimable 16 (baseline 9 + 6 released) |
| No row is left parked in `waiting` | PASS | 0 still waiting (baseline 6) |
| Parked rows can return to the claim pool | PASS | waiting->pending=t blocked->pending=t paused->pending=t |
| Every task migration is registered for deploy | PASS | 12 migrations; unregistered: none |
| Every task migration is on the deployed tree | PASS | 12 of 12 deployed |
| DB schema version matches the newest repo migration | PASS | DB=12 repo=12 |
| test_hc_harness failures reproduce WITHOUT this change (pre-existing) | PASS | with changes: ========================= 3 failed, 6 passed in 1.75s ========================== · HEAD~1 worktree: ========================= 3 failed, 6 passed in 1.73s ========================== |

**Verdict: PASS**
