---
name: one-owner-migrations
version: 1.0.0
description: "Use when moving a job to a new owner system."
triggers:
  - "migrate crons"
  - "move off the scheduler"
  - "hand over ownership"
  - "standalone service migration"
  - "double-running jobs"
  - "jobs stopped running"
category: devops
platforms: [linux, macos]
---

# One-Owner Migrations

Moving a scheduled or triggered responsibility from one owner system to another:
a scheduler to systemd/launchd timers, an in-process plugin to a standalone
service or MCP server, a daemon's job to an external queue, one host to another.

**The whole game is ownership.** A responsibility must have exactly one owner at
all times — during the migration too.

## Why this needs a discipline (two opposite failures)

| Failure | Mechanism | What reports it |
|---|---|---|
| **Double-run** | the old owner was never removed, so both fire | sometimes — the duplicate is visible in output |
| **Orphaned work** | the old owner was removed but the new owner never took it, or took it only for some items | **nothing** — no scheduler is left looking, so nothing flags it |

The second is the dangerous one, and it is the failure a naive "count the owners
and confirm they are active" check cannot see. Completion is a THREE-way check,
not a boolean.

State matters too: *pausing* the old owner is not removal. A paused entry is an
owner-in-waiting — a reinstall, an `enable`, or a resume hands it the job back,
and it leaves two sources of truth for one responsibility. Treat pause as an
intermediate step, removal as the endpoint.

## Procedure

1. **Name both owner sets and the marker that distinguishes them.** Before
touching anything, write down how to enumerate "owned by A" and "owned by B"
in one command each. Prefer a marker needing no session/DBus/daemon — a symlink,
a state file, a row — because the check must also run from contexts that have
none (cron, installer, health check). Verify the marker distinguishes ENABLED
from merely-INSTALLED: an artifact present but not enabled is not an owner.
2. **Guard the CREATE path BEFORE you remove anything.** This is what makes
removal safe, and it is the step most often skipped. Anything that recreates a
missing item — an installer that "ensures" a job exists, a reconcile loop, a
bootstrap — resurrects the old owner the moment you delete it, and then the work
runs twice. Teach the creator to skip items the new owner already holds, then
remove. Prove the guard by re-running the creator, not by reading it.
3. **Sweep every EXPECTATION-holder in the same change.** Anything declaring
"what should exist" is an expectation: a manifest, an expected-list the health
check parses, a registry of deployed files, a documentation index, a schema.
They fail the moment the item is gone. The REMOVAL is usually correct and the
stale EXPECTATION is the bug — teach the check the new owner (skip items owned
elsewhere) rather than restoring the item, which re-creates the duplicate. Then
sweep REFERENCES to the moved thing: docs, runbooks, skills, test paths, and any
live record storing its name or path.
4. **Hand over, then remove — per item, not wholesale.** Enable the new owner
for the item, verify it holds it, and only then remove the old owner's entry. A
wholesale "enable everything, then delete everything" sweep leaves no coherent
point to stop at if one item fails partway.
5. **Audit all three failure modes and report COUNTS, never a boolean.** A
"looks right" answer hides the orphan class.
6. **Prove the guard held.** Re-run the creator (installer/reconciler/bootstrap)
end-to-end and assert the total did not grow. This is the only proof the removal
survives the next automated pass.

## The three-way audit

Build the two name sets from the two markers, then assert:

1. **`overlap == 0`** — no item in both sets (double-run).
2. **No intended item is in neither set** — walk the intended list item-by-item;
   an item in neither set is silently stopped. Detect by name-set difference
   (**never by counting** — counts can match while the items differ).
3. **No owner exists for a dead item** — an owner-artifact whose item no longer
   exists anywhere (leaked by a partial rollback).

Then the standing check: re-run the creator and assert the count is unchanged.

## Pitfalls

- **Counting instead of diffing.** "N owners, N items" passes while a completely
different item is orphaned. Compare name sets.
- **Reading the raw store's field name from the CLI's vocabulary.** A management
CLI and its state file often use DIFFERENT keys for the same id (the CLI takes
`job_id`, the file stores `id`). A mass loop reading the wrong key gets `None`
for every row, removes nothing, and still logs one success-shaped line per item
— a silent no-op that looks exactly like success. Print one row's keys first.
- **Deleting at the same time as moving a whole directory.** If the old copy has
tracked-but-deleted entries, a directory-level move refuses (`bad source`)
because it cannot resolve a path that no longer exists. Stage the deletions
first, then move.
- **Being too strict about "considered" items.** Deliberately excluded items
(paused for a reason, opted out, not applicable on this host) must still LOOK
considered — give them the marker in its disabled/not-enabled state — or the
check false-positives on them forever. Only a genuinely absent marker means the
item was never handled.
- **A check for a host-specific mechanism must be gated on that mechanism.** An
audit for systemd/launchd/Windows-only machinery that warns where the mechanism
does not exist warns forever and trains the reader to ignore it. Report
informational there instead.
- **Not moving the validation probe with the responsibility.** After a migration
the OLD probing path may still work while the new one does not — validate
through the new owner's real invocation, not by re-running the old entry point.

## Fleet instances — where the concrete commands live

This skill is the PATTERN; the fleet's instances of it:

- **Cron/scheduler → systemd user timers**: the `systemd-cron-bridge` skill (unit
generation, the `--deliver` routing decision, the ownership marker) plus
`docs/runbooks/cron-bridge-migration.md` (per-host procedure and verification).
- **The push-gate symptoms of a half-done handover** — `❌ Deploy sync`,
`❌ Cron manifest missing (<name>)`, `❌ Checksum: <file>` — are covered in
`shared-repo-push-gates`, including the rule that the removal is correct and the
stale expectation is the bug.
- **Skill-library instance** (a pipeline writing the deployed copy while the repo
is the source of truth, so a deploy overwrites the lesson): `skill-curation`
rule 6.
- **In-process plugin → standalone MCP server**: the design in
`docs/design/cortex-memory-session-mcp.md` — same shape, the host-coupled
registration is replaced by a process-independent surface.

- **Hermes Agent → cortex/steadfaste (framework-level, in flight)**: the framework
itself is being retired, so every Hermes-side extension point is an
**owner-in-waiting** — a Hermes plugin under `plugins/`, a harness extension under
`ops/install/harnesses/`, a core file re-patched on every `hermes update`. Fix them
only when they block production; do not add new ones, do not offer upstream PRs, and
surface an existing core patch to the user as a migration blocker instead of quietly
maintaining it. When a Hermes component is removed, revert the key that SELECTED it
(e.g. `cron.provider`, its sub-blocks) in the same change: the framework then falls
back to its own default but logs a fallback warning on every tick, which reads to the
user as the removed thing still causing issues.

## Reporting

Report the counts, the marker used for each set, and the two proofs (the audit
result and the creator-rerun count unchanged). "All migrated" without those
numbers is an assertion, not evidence.
