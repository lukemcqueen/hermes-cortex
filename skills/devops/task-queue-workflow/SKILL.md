---
name: task-queue-workflow
version: 1.0.0
category: devops
description: "Use when claiming task-db slices under task model v3."
author: Hermes Cortex
platforms: [linux, macos]
metadata:
  hermes:
    tags: [tasks, task-model-v3, orchestrator, worker, claim, verify, review, board]
    related_skills: [orch-backlog-driver, postgres-schema-design, loop-governance, change-test-loop]
---

# Task Queue Workflow — Task Model v3 (orchestrator-intelligence / worker-execution)

## When to Use

- Any agent claiming or executing a slice from the task queue
- Orchestrators decomposing stories, dispatching, or verifying completions
- Reading the task board or daily digest
- Design: `docs/design/task-model-v3.md`; schema: `ops/services/tasks/schema/v009__task-model-v3.sql` + `v010__task-model-v3-matrix-fix.sql`

## The Model

Two tiers, not role-locked domains (Luke 2026-08-24):

- **Orchestrators (esther/moses) = the intelligence layer** — decompose
  stories → planned slices, dispatch urgent work, VERIFY every completion.
  Strategy/research/verification/case-study authoring are orchestrator work.
- **Every other agent = a general worker** — may claim and execute ANY slice
  (build, refactor, research, docs, infra). No role-lock.
- A worker may claim any pending slice; **only the orchestrator may verify**.

## Lifecycle

```
pending → (claim) → in_progress → (report) → review → (verify) → completed
              └── (unclaim) ──┘                    └── (verify --reject) → in_progress
```

- `review` = worker-done-AWAITING-VERIFICATION. **Not done.** The orchestrator's
  evening pass (19:00) clears it; a slice stuck >24h in review gets
  auto-re-queued by the handler's stale sweep (Arm 3) — never auto-completed.

## Worker commands (any agent)

```bash
task-db.py list --claimable                    # the worker queue: pending slices, no assignee, by priority
task-db.py claim <slice-id>                    # atomic pending→in_progress, assignee=me (self-only)
task-db.py unclaim <slice-id> --reason "<gap>" # return to pending (blocker, tool gap) — never fake progress
task-db.py report <slice-id> --evidence "<test output / measured numbers>"
                                               # in_progress→review, awaiting orchestrator verify
```

- Execute the orchestrator's PLAN (written in the slice content), don't
  improvise strategy. Too big or lacks a tool → unclaim with the gap named.
- Report with EVIDENCE, not prose (test output, measured numbers).

## Orchestrator commands (esther/moses only)

```bash
task-db.py verify <slice-id> --approve --note "<what was checked>"
task-db.py verify <slice-id> --reject --note "<the gap>"   # → back to in_progress
task-db.py list --board                                     # counts + per-agent + review queue
```

- **Never trust a self-reported done.** Verify the evidence is real (test
  output, measured numbers) before approving.
- Reject with the gap named — the slice returns to in_progress for the worker.

## Automated layers (no manual action needed)

- **orch-task-board-digest** — 08:30 KST zero-token no_agent cron → Telegram
  (Luke + Amy): open counts, per-agent in_progress, review queue, claimable.
- **orch-task-morning-pass** — 07:00 KST: decompose stories → planned slices,
  dispatch urgent via bus.
- **orch-task-evening-pass** — 19:00 KST: verify all review slices.
- **Stale sweep Arm 3** (agent-message-handler): review >24h → verify(false,
  'verify-stale') re-queues to in_progress.
- **Daily digest + board query** satisfy the visibility requirement (Luke:
  "1) visibility for tasks easily viewable 2) agents working truly
  autonomously and efficiently").

## Pitfalls

- **verify is orchestrator-only** — the function checks
  `profile_of(session_user) IN ('moses','esther')`; workers get `false`.
- **Claim is self-only** — `p_assignee` must equal `profile_of(session_user)`;
  you can claim only FOR YOURSELF, never assign work to others.
- **A claimed slice can't be re-claimed** — the single claimer holds it until
  unclaim/report.
- **Unclaim/claim/report work on YOUR OWN rows** — `created_by` must match the
  caller; you can't unclaim or report someone else's work.
- **Schema v009+ required** — these commands `_require_v4` (schema 9). On an
  older host, run `bash cortex-update.sh` first (the version-gated runner
  applies v009/v010).
- **report/verify set the derivation column too** — the functions keep the
  column-derivation CHECK in sync; hand-written UPDATEs that don't will fail.
- **review ≠ done** — reporting puts work in a queue, it does not close it.
  The orchestrator's evening pass is the closer.

## Compete mode (opt-in, orchestrator)

Slices can run as parallel candidates: `orch-compete-run.py <slice-id> --plan
"APPROACH: ..."` (≥2 approaches). Candidates judged DETERMINISTICALLY:
acceptance criteria met → fewest adversarial findings → lowest cost →
fastest. Never "which sounds better" (consistent with O4 autonomy rules).

## References

- `references/v009-schema-lessons.md` — the SQL/RLS gotchas behind the schema
  (SECURITY DEFINER + session_user, column-derivation CHECK, guarded grants)
- `docs/design/task-model-v3.md` — the full design
