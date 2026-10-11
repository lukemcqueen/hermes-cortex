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

Detector attribution (proof C in the script): the residual drift set is exactly
`{devops/governance-closeout}` — the script asserts equality against that single
expected path and fails otherwise. That file is a PURE SUPERSET (0 repo-only
lines, 2 deployed-only lines), and the lock that owns it is open and belongs to
a different cycle:

```
task_id = memory-pruning-push-12144
status  = executing
owner   = the peer agent-memory-pruning session
          (its lock file sits under ~/.hermes-cortex/state/)
```

That is not this cycle's file: SOUL Principle 9 / "don't race a peer's in-flight
update" forbids syncing it. Recorded as issue #88. The FAIL(1) is therefore
attributed to the peer's open-lock artifact; the six files this cycle owned are
all `OK` / PASS.

## ADV-12154-3 (scope-drift: memory-pruning / stale-check evidence files)

Those files are **NOT in this cycle's diff**. They are the working-tree state of
the peer `agent-memory-pruning` session (task `memory-pruning-push-12144`), which
is mid-cycle on this shared checkout; the adversarial reviewer diffs the whole
working tree, so it sees them. They are unstaged and were never staged or
committed by this cycle. This cycle's commits touch only:

```
d91f3a61  skills/{devops/cortex-deployment-sync,cron-job-management,
          enforcement-change-safety,enforcer-modification-considerations,
          software-development/hermetic-python-testing,session-manager}/SKILL.md
4a74b701  skills/research/job-board-research/SKILL.md (+ delete job-market-research)
82f2d9c1  docs/SKILLS-MANIFEST.md
```

Nothing removed — the peer's uncommitted evidence stays exactly where its own
cycle will commit it.
