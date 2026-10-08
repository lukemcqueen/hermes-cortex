---
name: skill-curation
version: 1.1.0
description: "Consolidate, dedupe, and prune the skill library — merge overlapping skills into one (absorbed_into), delete truly dead skills, and keep the manifest honest. Use when the doctor flags skill drift, two skills overlap, or a lifecycle run surfaces consolidation candidates."
triggers:
  - "curate skills"
  - "consolidate skills"
  - "merge skills"
  - "prune skills"
  - "skill dedupe"
---

# Skill Curation

Consolidate, dedupe, and prune the skill library. Curation is the
counterweight to creation: every new skill is debt until it earns its place,
and a merged skill serves better than two overlapping ones.

## When to Curate

- After a lifecycle run (orch-skill-lifecycle Monday deep eval)
- When 2+ skills overlap — `skills_list(category=...)` shows same-domain
  entries with similar descriptions
- On any deletion — always declare `absorbed_into=<umbrella>` (merged
  into an existing skill) or `absorbed_into=""` (true prune) so downstream
  tooling (cron-job skill references, the curator) knows intent
- When the doctor flags skill drift, duplicates, or deployed orphans

## Rules

1. **Prove duplication first.** Load both skills and compare structure AND
   content — descriptions alone lie. Overlap > 50% → merge; otherwise keep
   both and note the boundary.
2. **Improve existing before creating.** The merge target is the existing
   skill — extend it, never spawn a sibling. If the two are equal weight,
   keep the one with better structure, fold the other's unique sections in.
3. **Redirects carry real bodies.** A deprecated skill keeps a body that
   explicitly routes to the replacement (and an `aliases:` entry in
   frontmatter) — never a placeholder. Deleting a redirect without a
   forwarding target orphans every reference to the old name.
4. **Check consumers before pruning.** A deployed-only skill may
   be referenced by crons, manifests, or other skills. Grep jobs.json,
   install-crons.sh, and skills before `delete`. Deploy warnings are not
   deletes. A deployed-only skill is also an **orphan** — no repo source, so
   the doctor reports `Stale skills: orphaned` and one deploy can remove it.
   Import it into the repo or delete it deliberately; never leave it
   half-owned, and same for a `references/` file that exists only deployed.
5. **Verify after every merge/delete.** `skill_view` both skills, re-read
   the merged SKILL.md for fence balance, run the doctor, regenerate the
   manifest if skills/ changed.
6. **The REPO is the source of truth — a curatorial edit made on the DEPLOYED
   copy is STRANDED, not shipped.** `skill_manage` writes the DEPLOYED copy
   (`~/.hermes/skills/<...>`), while the fleet receives only
   `hermes-cortex/skills/<category>/<name>/`. A deploy then either overwrites
   that copy or — where the drift guardrail is in force — SKIPS it; either way
   the lesson reaches no other host, and the doctor reports it as skill drift
   (*"Deployed copy is newer than repo source"*). The doctor names it: *"Deployed copy is
   newer than repo source. Commit the repo source before cortex-update
   overwrites it."* After ANY skill edit, propagate the deployed skill back
   to the repo path (the whole dir, `references/` included) and commit it in
   the same run. Check for drifted pairs at the **start** of a pass too: drift
   means a previous run's lesson is still unlanded, and re-deriving it instead
   of propagating it duplicates the work. Verify with `diff` — the only
   acceptable difference is the deploy header.

   **Measure drift by CONTENT, never by mtime.**
   `python3 ops/scripts/manage/check-skill-drift-parity.py` (exit 1 = stranded;
   regenerates `docs/evidence/skill-drift-parity.txt`). A file is stranded when its
   DEPLOYED content appears neither in the repo working tree nor in any committed
   revision of that path. mtime is useless here — a clone or checkout resets every repo
   mtime to "now", so an mtime comparison reports "repo is newer" while the content
   exists nowhere in the repo and the drift goes unnoticed. It compares EVERY file under
   the deployed tree, not just `SKILL.md`, so a drifted `references/` file is visible too.

   **Decide the direction PER FILE by reading the diff — the deployed side is often the
   CURATED one.** A deployed lesson may have been rewritten to generalise, so it can ADD
   lines AND REMOVE lines the repo still has: never copy it in blind, and never assume
   the repo side is the superset. The deploy header sits AFTER the shebang and is closed
   by a blank line, so a fixed `tail -n +4` misaligns the comparison — strip the header
   LINES and diff what remains. Copy the canonical content in, re-run the parity check to
   `PASS`, then deploy to clear the doctor's warnings.

## Manifest Discipline

- After any skill add/rename/delete: regenerate
  `docs/SKILLS-MANIFEST.md` via `gen-skills-manifest.py` (never hand-edit).
- Keep category counts truthful — a stub or placeholder body in the repo is
  a curation debt: flag for restore, don't let it ship.

## Anti-Patterns

- Merging by description without reading both files
- Deleting a skill and leaving its references dangling
- "Fixing" a balanced file's fences (see orch-skill-lifecycle fence rule)
- Creating a new skill because the existing one needed a patch

## Bulk Curation Mechanics

- `skill_manage` **`delete` is a sole op** — it refuses to compose with other
  ops in a single `operations` array (rollback safety). Fire each `delete` as
  its own `skill_manage` call; issue several single-op calls in parallel when
  pruning a batch, but never put a `delete` alongside another action.
- Writing redirect bodies over many existing `SKILL.md` files hits the
  `write_file` read-before-write guard: it refuses to overwrite a file whose
  current content you have not fully read this task, and a `read_file(limit=N)`
  counts as a "partial view" that still blocks. For bulk redirects, delegate
  the mechanical overwrite to a subagent (it reads-then-writes cleanly), or
  read each file fully (no `limit`) first, or `patch` just the frontmatter
  lines instead of overwriting the whole file.
