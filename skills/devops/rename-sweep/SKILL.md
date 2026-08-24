---
name: rename-sweep
description: Fleet-wide term/artifact renames and decommission sweeps.
version: 1.0.0
category: devops
platforms: [linux, macos]
metadata:
  hermes:
    tags: [rename, sweep, decommission, migration, bulk-edit]
    related_skills: [change-checklist, survey-before-action, enforcement-change-safety, cortex-bus]
---

# Rename Sweep — Fleet-Wide Terminology/Artifact Renames

Systematic method for removing or renaming a term, product name, or artifact
across an entire repo (decommission, rebrand, terminology migration — e.g.
the 2026-08-21 gbrain→mycortex purge: 168 files, 0 residual tokens). The
hard part is NOT the replacement — it is the compound tokens the catch-all
misses, the mangled tokens the guards create, and the deleted-file
cross-references that silently break tests and indexes.

## When to Use

- User says "remove ALL references to X", "rename X to Y everywhere", or a
  product/component is decommissioned and must be purged.
- A handoff/proposal claims a rename is "done" but the branch never landed —
  you must verify and often redo the sweep fleet-side.
- Don't use for: single-file renames (patch it), or docs-only path fixes
  (documentation-auditing covers stale paths).

## Prerequisites

- A governance lock (`begin_change`) — write tools block without it.
- Adversarial-verifier loaded (pre-commit blocks changed `ops/` paths).
- Enumerate the surface FIRST: `git grep -i <term>`, files named `*<term>*`,
  deployed copies (`~/.hermes-cortex/scripts/`), cron jobs (`jobs.json`),
  live configs. 200+ matches across 100+ files is normal for a real sweep.

## Procedure

### 1. Classify every occurrence into three buckets

| Bucket | Meaning | Action |
|--------|---------|--------|
| Functional | Keys, var names, service names, CLI commands, DB/role names, paths in code | Replace with the new term (exact tokens) |
| Dead artifact | Files/dirs/skills whose whole purpose was the old term | `git rm` |
| Historical | Dated docs, transcripts, review reports, design comparisons | Rephrase to a neutral descriptor ("the legacy brain"), never the new term |

Delete the dead artifacts FIRST (git rm), then sweep references to them.

### 2. Replacement engine — guards BEFORE catch-all, in one ordered pass

Blind `term → newterm` breaks everything. Use this order per file:

1. **Exact functional tokens** (case-sensitive, applied first): keys
   (`gbrain_sources_ok`), var names (`V_GBRAIN`), file/service names
   (`import-gbrain.py`, `com.gbrain.autopilot`), env vars
   (`GBRAIN_PG_PASSWORD`), issue keys. A word-boundary catch-all
   (`\bgbrain\b`) MISSES underscore compounds (`gbrain_search`,
   `gbrain_legacy_*`, `FIXED_GBRAIN`) — list them explicitly.
2. **Phrase guards** (case-insensitive): "X decommissioned/deprecated" →
   "legacy …", "(X replacement)" → dropped, "X→new" → "legacy→new".
3. **Mode-aware catch-all**: case-preserving replace of the bare word —
   "mycortex" in functional/active files, "legacy brain" in historical files.
4. **Skip surgical files** (register lines, stub removal, service-check
   deletion, test guards) and edit them by hand after the bulk pass.

### 3. Mangle scan (mandatory after the bulk pass)

Guards with spaces mangle compound tokens. Grep for these and fix:

- Space inside a token: `install-legacy sync.sh`, `~/.legacy brain`,
  `com.legacy brain.sync-watch`, `garrytan/legacy brain` (broken URL),
  `main.legacy brain` — re-slug to `legacy-brain`.
- Case-insensitive label guard swallowed a COMMAND: `"GBrain Sync"` guard
  also matched `gbrain sync --source X` → `"Mycortex Sync --source X"`.
  Scan for title-case command garbles; the CLI command is lowercase.
- Catch-all hit a path that meant the OLD home dir: `~/.gbrain` →
  `~/.mycortex` (wrong product!) — paths must map to the neutral slug.
- `\bterm\b` misses `term_compound` — the residual grep catches these;
  fix each with an exact-token replacement.

Finish with `git grep -i <term>` == 0 AND a token-mangle grep
(`legacy brain/`, `install-legacy `, `~/.legacy `) == 0.

### 4. Deleted-artifact cross-reference sweep

Deleting files breaks things that assert their existence:

- **DOCS-INDEX.md** entries for deleted docs/scripts (remove the rows).
- **Test fixtures** asserting paths to deleted files
  (`test_golden_expected_paths_exist_in_repo` FAILs on stale expected_top3 —
  delete the stale query entry, keep count invariants like "25-30 queries").
- **register() lines** in cortex-update.sh for deleted scripts (remove both
  the line and any update/stub functions that call them).
- **Skills referencing the deleted skill** (governance-sentinel listed
  gbrain-maintenance) — reword or drop the pointer.
- **Deployed copies**: after deploy, `rm` stale deployed artifacts the
  doctor flags ("Remove: …" in REQUIRED ACTIONS).

### 5. Verification battery

- `bash -n` every changed .sh; `py_compile` every changed .py; validate
  JSON/YAML (deleted files show as FAIL — ignore them, they're gone).
- Adversarial gate A2 on every changed script.
- Run the test suites that touch deleted paths (parity/golden tests).
- Live-service tests fail on deploy-order lag: a running service still
  serves the old label until `cortex-update.sh` redeploys — verify against
  the repo, not the live service, then re-test after deploy.
- `git grep -i <term>` == 0, doctor clean, deploy via cortex-update,
  then push.

## Pitfalls

- **git stash pop without `--index` silently unstages everything** — the
  staged index is lost; re-stage with `git add -A` before re-committing.
- **`git checkout --ours/--theirs <file>` during rebase restores the WHOLE
  file from that side** — auto-merged hunks in that file are reverted (a
  `--ours` on install.sh reverted an entire 16-file sweep's changes to it).
  Prefer per-hunk resolution or re-apply and re-verify with grep after.
- **A sibling push can land mid-sweep** (Moses committed Titus's resend
  while the sweep ran). The pre-push dogfood gate then blocks with
  "Deploy sync — HEAD ahead of last deploy". Fix: `git pull --rebase`,
  resolve (the sweep is usually a superset — origin's hunks are fine where
  cosmetic, re-apply yours where they conflict on substance), deploy,
  doctor, re-push. Check `git log origin/main -3` before pushing a big
  change.
- **Fence corruption is pre-existing, not yours**: the pre-commit fence
  check may flag an unbalanced file you merely touched. Verify at HEAD
  (`git show HEAD:<file> | grep -c '^```'`) before fixing; a dangling
  opener at EOF gets removed, not closed.
- **The word count in PII scans includes pre-existing patterns** — diff
  the flagged lines against what you actually changed before claiming
  your sweep introduced PII.

## Verification

- `git grep -i <term>` returns 0 (tracked tree).
- Token-mangle grep returns 0.
- Tests that assert paths/fixtures pass.
- Deployed copies clean; doctor shows no ❌; push landed on origin.

See `references/gbrain-to-mycortex-2026-08-21.md` for a worked example:
token list, guard table, every mangle class with its fix, and the
concurrent-push rebase sequence.
