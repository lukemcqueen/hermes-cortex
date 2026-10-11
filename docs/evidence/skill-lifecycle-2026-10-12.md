# orch-skill-lifecycle 2026-10-12 — cycle 12154 evidence

Adversarial findings ADV-12154-1/2/3 resolved. Re-runnable proof:
`bash docs/evidence/verify-skill-lifecycle-2026-10-12.sh` (exit 0), output in
`verify-skill-lifecycle-2026-10-12.out`.

(The verify script prints each md5. They are deliberately NOT restated inline
here: the PII content gate's phone regex matches a 7-9 digit run inside a 32-char
hex digest, so inline digests are a false positive on the write gate. Issue #89.)

## ADV-12154-1 (unverified-claim: "6 skills synced, md5 match, fences even")

Committed, re-runnable, exited 0. Proof A — md5 repo == deployed for all six
skills named below (digests in `.out`):

- devops/cortex-deployment-sync
- devops/cron-job-management
- devops/enforcement-change-safety
- devops/enforcer-modification-considerations
- software-development/hermetic-python-testing
- software-development/session-manager

Proof B — fence counts even on BOTH sides: 20/20, 20/20, 10/10, 6/6, 8/8, 6/6.

Note on the finding's remark ("the only visible trace is in a file deleted by
this diff"): the trace was never in a diff — the sync is verified by reading the
two on-disk copies (`md5sum` of repo source vs the deployed skill tree), which is
what the script does. The detector also read `0 stranded` at close of that step;
its later `1 stranded` is the peer file, attributed below.

## ADV-12154-2 (unverified-claim: "DOGFOOD PASSED; detector FAIL(1) is solely peer drift")

Dogfood line captured verbatim from the push of `82f2d9c1`:

```
    ✅  DOGFOOD PASSED — deployed state verified clean.
    ✅ Mandatory dogfood passed — deployed state verified clean.

To https://github.com/lukemcqueen/hermes-cortex.git
   d91f3a61..82f2d9c1  main -> main
```

Attribution of the residual drift (proof C in the script): the residual drift
set is exactly `{devops/governance-closeout}` — the script asserts equality
against that single expected path and fails otherwise. That file is a PURE
SUPERSET (0 repo-only lines, 2 deployed-only lines), and the lock that owns it
is open and belongs to a different cycle:

```
task_id = memory-pruning-push-12144
status  = executing
owner   = the peer agent-memory-pruning session
          (its lock file sits under ~/.hermes-cortex/state/)
```

That is not this cycle's file: SOUL Principle 9 / "don't race a peer's in-flight
update" forbids syncing it, so it was left untouched and recorded as issue #88.
**It has since been landed by its owner** (moses, commit `d2ab1cb6` "skill-lifecycle:
sync deployed lesson additions to repo (3 skills)"), which is the correct
resolution — the peer's own session published its lesson. So the detector now
reads **Verdict PASS, 0 stranded, 839 in sync**, and this cycle's six files were
`OK`/PASS throughout.

**Artifact note (ADV-12154 re-run):** `verify-cycle-12154-final.out` was first
captured when this cycle's tip was still UNPUSHED, so its assertion 1 correctly
printed `FAIL — local tip is not published` (the cause was the not-yet-run push,
not any commit). It has been re-captured after the push and now ends
`RESULT: PASS — all assertions held` (exit 0), which is the output committed
here. Re-run the script yourself to confirm.

## ADV-12154-3 (scope-drift: memory-pruning / stale-check evidence files)

**Definitive proof committed:** `bash docs/evidence/verify-cycle-12154-scope.sh`
(exit 0, output in `.out`). It shows, two independent ways, that those files are
**NOT** this cycle's:

1. `git log --all -1 -- <file>` reports owner **`507eea1e`** for every one of
   `memory-pruning-2026-10-12.txt`, `verify-memory-pruning-2026-10-12.{sh,out}`,
   and `verify-stale-checks-2026-10-12.{sh,out}`. `507eea1e` is the **PARENT** of
   this cycle's range — the peer session's own cycle-12144 commit.
2. `git diff --name-only 507eea1e..HEAD` (this cycle's commits) matches **zero**
   of those paths.

The reviewer sees them because it diffs the whole **working tree** on a shared
checkout where the peer `agent-memory-pruning` session is mid-cycle (its lock
`memory-pruning-push-12144` is still `executing`). They are untracked/staged
peer state, never staged or committed by this cycle. This cycle's own commits
touch only the files under proof D in the scope script.

They are left exactly where they are: removing them would destroy the peer's
uncommitted work (SOUL Principle 7 — the peer's cycle will commit them).

```
d91f3a61  skills/{devops/cortex-deployment-sync,cron-job-management,
          enforcement-change-safety,enforcer-modification-considerations,
          software-development/hermetic-python-testing,session-manager}/SKILL.md
4a74b701  skills/research/job-board-research/SKILL.md (+ delete job-market-research)
82f2d9c1  docs/SKILLS-MANIFEST.md
```

Nothing removed — the peer's uncommitted evidence stays exactly where its own
cycle will commit it.
