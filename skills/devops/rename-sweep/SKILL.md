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
the 2026-08-21 legacy-system→mycortex purge: 168 files, 0 residual tokens). The
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

Delete the dead artifacts FIRST (git rm), then sweep references to them — but
verify a suspected DUPLICATE tree is really a duplicate before `rm -rf` (see
Pitfalls: a copy can hold the only copy of some files).

### 2. Replacement engine — guards BEFORE catch-all, in one ordered pass

Blind `term → newterm` breaks everything. Use this order per file:

1. **Exact functional tokens** (case-sensitive, applied first): keys
   (`legacy-system_sources_ok`), var names (`V_LEGACY_SYSTEM`), file/service names
   (`import-legacy-system.py`, `com.legacy-system.autopilot`), env vars
   (`LEGACY_SYSTEM_PG_PASSWORD`), issue keys. A word-boundary catch-all
   (`\blegacy-system\b`) MISSES underscore compounds (`legacy-system_search`,
   `legacy-system_legacy_*`, `FIXED_LEGACY_SYSTEM`) — list them explicitly.
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
- Case-insensitive label guard swallowed a COMMAND: `"Legacy Sync"` guard
  also matched `legacy-system sync --source X` → `"Mycortex Sync --source X"`.
  Scan for title-case command garbles; the CLI command is lowercase.
- Catch-all hit a path that meant the OLD home dir: `~/.legacy-system` →
  `~/.mycortex` (wrong product!) — paths must map to the neutral slug.
- `\bterm\b` misses `term_compound` — the residual grep catches these;
  fix each with an exact-token replacement.

Finish with `git grep -i <term>` == 0 AND a token-mangle grep
(`legacy brain/`, `install-legacy `, `~/.legacy `) == 0.

### 3b. Sweeping a PATH, not just a bare term

When the target is a file PATH (`~/.dir/old.conf` → `~/newdir/.env`), the
replacement changes BOTH the directory and the basename. A bare-filename
catch-all (`old.conf` → `.env`) then rewrites variable- and call-composed
forms into paths that still aim at the OLD directory:

```python
OLD_HOME / "old.conf"                  →  OLD_HOME / ".env"          # ✗ old dir!
Path.home() / ".dir" / "old.conf"      →  Path.home()/".dir"/".env" # ✗ old dir!
```

Enumerate the FORMS first, then give each its own rule, most specific first:
`$HOME/.dir/old.conf`, `${VAR}/old.conf`, `~/.dir/old.conf`, `%h/.dir/old.conf`,
`Path.home()/".dir"/"old.conf"`, `HOME/".dir"/"old.conf"`, `.dir/old.conf`,
and only then the bare basename. Finish with the residue grep — the NEW
basename still sitting in the OLD directory
(`grep -rnE '"\.dir" */ *"\.env"'`) — that grep, not the old-name grep, is
what finds these mangles. Dry-run the table and read the plan before writing.

### 4. Deleted-artifact cross-reference sweep

Deleting files breaks things that assert their existence:

- **DOCS-INDEX.md** entries for deleted docs/scripts (remove the rows).
- **Test fixtures** asserting paths to deleted files
  (`test_golden_expected_paths_exist_in_repo` FAILs on stale expected_top3 —
  delete the stale query entry, keep count invariants like "25-30 queries").
- **register() lines** in cortex-update.sh for deleted scripts (remove both
  the line and any update/stub functions that call them).
- **Skills referencing the deleted skill** (governance-sentinel listed
  legacy-system-maintenance) — reword or drop the pointer.
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

### 6. Land it fleet-wide — 0 residuals is NOT done

A sweep that only changes files is finished on YOUR host and broken
elsewhere. A fleet-wide rename/config move is done when every other host
converges without a human, and agents can see what changed. Ship all four
with the sweep, in the same change:

1. **An automatic per-host migration** on the update path — make the deploy
   script RUN the consolidation (idempotently) before anything reads the moved
   thing, and make the migration script seed the new location from the old one
   rather than failing when it is absent. A host that still has only the old
   layout must self-heal on the next `cortex-update.sh`.
2. **An enforcement check in the doctor** — FAIL on the new invariant (target
   exists, right perms, old path absent or a symlink to it, and a `fix:` line
   naming the exact script to run). A sweep with no check silently regresses
   the first time someone recreates the old artifact.
3. **A runbook** (`docs/runbooks/<topic>-migration.md`) — the convention table
   (which path is canonical, which are symlinks, which are not ours), how to
   apply on Linux AND macOS, how to verify, the changes to implement, and a
   symptom→cause→fix table. Index it in DOCS-INDEX.
4. **Agent-facing skill notes** — update the setup/troubleshooting skill the
   agents actually load, and fix any prose your own sweep mangled (check every
   line you rewrote reads sensibly; a rename can turn a sentence into a
   tautology).

The user WILL ask "will agents be able to implement this?" if you skip 1–4 —
treat that as part of the deliverable, not a follow-up.

## Pitfalls

- **A directory that LOOKS like a duplicate copy is not provably one — diff it
  file-by-file before deleting anything.** The same sub-path appearing twice
  (`<dir>/docs/…` alongside `<dir>/docs/new/<project>/docs/…`) usually means a
  stale copy, but the copy can hold files the canonical tree lacks. Hash both
  trees (`find <a> <b> -name '*.md' -exec md5sum {} + | sort`) and print BOTH
  the duplicate hashes AND the files present in only one tree — in the real
  case 15 of 38 files were byte-identical while **23 existed only in the copy**,
  so deleting on the assumption of duplication would have destroyed the only
  copy of real content. Procedure: merge the uniques up into the canonical tree
  (preserving relative paths — some may land OUTSIDE the subtree you are
  keeping, e.g. a sibling `spec/`), then delete only the residual duplicates.
  The proof is `duplicate hashes == 0` afterwards, not the deletion itself.
- **A prefix-INSERTION sweep is not idempotent — the new text still contains the
  old pattern.** Renaming a bare term never re-matches itself; INSERTING a path
  segment does (`docs/<x>/` → `docs/older/<x>/`), so a second rule in the same
  pass — or any re-run — matches inside the already-rewritten string and produces
  `docs/older/older/<x>/`. Guard the replacement with a negative lookbehind
  (`(?<!older/)docs/<x>/`) or match only the un-prefixed form, then assert exactly
  one pass's worth of change before writing.
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
- **Exclude the tool that PERFORMS the migration.** A script that merges the
  old artifact into the new one legitimately references the old name (its
  idempotency check depends on it). A blanket rename breaks the very mechanism
  you are migrating to — add it to the skip list explicitly, and say so in the
  commit message so a later reader does not "fix" it.
- **Exclude the tool that DETECTS and REPORTS the old artifact.** A checker or
  doctor check whose *message* names the old path must keep that literal — there
  the old name is the SUBJECT of the sentence, not a reference to a path. A
  blanket replace turns `stray ~/old/dir/.env` into a message naming the
  CANONICAL file: a tautology that now misreports which path is wrong.
- **A clean residue grep does not prove the surviving text is TRUE.** It only
  proves no old token survives. This is the code-side twin of the prose-mangle
  check in step 6.4 — re-read every string the run changed, error/warning
  message strings included, and confirm each still describes what it claims.
- **Exclude same-basename files in other directories.** `~/.dir/conf.d/old.conf`
  and `~/.other/old.conf` are DIFFERENT files; a basename rule rewrites them
  happily. Guard per-line on the full distinguishing path, and verify the
  genuine ones survived.
- **After a path sweep the repo can still WORK while being wrong.** A symlink
  at the old location hides every missed reference until the symlink is
  removed — so residue-grep the source, then remove the symlink deliberately,
  never assume "the tests pass" means the sweep is complete.
- **A background result can be SUPERSEDED — check it is the latest run before
  acting.** A long test/deploy run finishing late reports the tree from when it
  STARTED. Two completion notices can disagree (an older 7-failure run landing
  after the fixed 5-failure run). Compare against the current HEAD and re-run
  the pair/suite if in doubt; never report a stale FAIL list as the state, and
  never "fix" what a superseded run complained about.

## Verification

- `git grep -i <term>` returns 0 (tracked tree).
- Token-mangle grep returns 0.
- Tests that assert paths/fixtures pass.
- Deployed copies clean; doctor shows no ❌; push landed on origin.

See `references/legacy-system-to-mycortex-2026-08-21.md` for a worked example:
token list, guard table, every mangle class with its fix, and the
concurrent-push rebase sequence.
