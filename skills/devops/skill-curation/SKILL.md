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
3. **Redirects carry real bodies AND the redirect in their `description`.** A
   deprecated skill keeps a body that explicitly routes to the replacement —
   never a placeholder — and the SAME routing text in its `description`, because
   a loader REFUSES a SKILL.md whose description is absent or blank: the stub is
   then never loaded, so its "merged into X, load X instead" body reaches nobody
   and the tombstone is pure context cost with zero effect. An
   `aliases: [<old-name>]` entry on the TARGET is the belt-and-braces form;
   the stub alone is what actually resolves the old name. Deleting a redirect
   without a forwarding target orphans every reference to the old name. The
   doctor's `Skills loadable` check FAILs on exactly this class — a missing or
   blank description, a name outside `[a-z0-9-]`, frontmatter that does not parse,
   a duplicate mapping key PyYAML accepts but a loader rejects — so run it after
   any consolidation pass instead of eyeballing the tombstones.
4. **Check consumers before pruning.** A deployed-only skill may
   be referenced by crons, manifests, or other skills. Grep jobs.json,
   install-crons.sh, and skills before `delete`. Deploy warnings are not
   deletes. A deployed-only skill is also an **orphan** — no repo source, so
   the doctor reports `Stale skills: orphaned` and one deploy can remove it.
   Import it into the repo or delete it deliberately; never leave it
   half-owned, and same for a `references/` file that exists only deployed.

   **A third-party PLUGIN dump is a third case: neither import nor delete.** A
   directory carrying its own plugin manifest (`package.json`,
   `<tool>.plugin.json`, `_meta.json`) whose `SKILL.md` has no frontmatter has no
   repo source to import and no owner left to repair it. Check the RUNTIME first
   (`command -v <tool>`; its config directory) — the skills such a dump ships are
   instructions to call tools that exist only while that plugin is loaded, so with
   the runtime gone they are prompts to call nothing. Then PRESERVE it by MOVING it
   into a dot-directory inside the same skills tree
   (`<skills>/.archive/<name>-<tool>/`) rather than deleting: loaders skip dot-dirs,
   so it leaves every agent's view and stays recoverable. Assert
   destination-absent before the move (never clobber), then assert the file COUNT
   at the destination matches the source's.

   **A ROOT-LEVEL skill directory is never pruned by a deploy** — the updater's
   stale pass treats a path with no `/` in it as a Hermes default and skips it. So
   a removal like that is not undone by an update, and it does not propagate
   either: another host carrying the same dump still gets the doctor WARN, which is
   the correct behaviour — report it there, do not delete it fleet-wide from one
   host's evidence.
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

7. **A same-name collision from a `local-*` skill is the OVERRIDE WORKING — do not
   "fix" it.** A host-local `local-<x>` skill deliberately keeps the fleet skill's
   `name: <x>`, so it wins the name collision and the fleet copy is skipped: that IS
   the per-host override mechanism, and the harness reports it as a collision
   warning rather than an error. Renaming the local skill's `name:` to match its
   directory makes BOTH load and the override silently stops working.
   `cortex-update.sh`'s stale pass preserves every `local-*` directory for the same
   reason. A `local-*` skill that carries a real frontmatter defect (a duplicate
   key, a name outside the charset) is still broken, though — the collision is
   expected, the parse failure is not.

   **How a collision arises at all — the name falls back to the DIRECTORY.** A
   loader uses `frontmatter.name`, and when that is absent it uses the skill
   directory's own basename, so a directory carrying no `name:` is advertised under
   its DIRECTORY name and can collide with a different skill that declares that name
   in frontmatter. On collision the loser is skipped and the winner is whichever the
   traversal reached first — decided by readdir order, not by intent — which is
   precisely the mechanism a `local-*` override exploits on purpose. Note the
   interaction with rule 3: a SKILL.md with no DESCRIPTION never reaches the name
   map at all, so a no-frontmatter dump is dropped outright and its only effects are
   the diagnostic and the index cost. Read the loader's own DIAGNOSTICS LIST before
   calling something a collision — the two failures look identical in a directory
   listing and are different findings.

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
