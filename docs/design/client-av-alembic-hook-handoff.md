# Task 2 handoff — client-av dead alembic hook migration

**For titusclaude (on Titus, client-av checkout).** Verified by Esther
2026-08-24 from hermes-cortex side. The cortex pre-commit already auto-runs
`$REPO_ROOT/ops/scripts/change-validate.sh` when present (pre-commit-score
line 895) — the migration target is ready.

## Context (verified)

- `.git/githooks/pre-commit` in client-av is **shadowed** by the global
  `core.hooksPath=~/.hermes-cortex/hooks` — it never fires on commit.
- It enforced alembic revision IDs ≤ 32 chars (varchar(32) in
  `alembic_version`; longer IDs crash container startup).
- **Currently NOT enforced on commit** — real gap.

## The fix (3 steps in client-av)

### 1. Add the alembic check to `ops/scripts/change-validate.sh`

Insert before the final `HAS_ISSUES` summary (after section 5). Logic:
block any staged migration file whose `revision` line exceeds 32 chars.

```bash
# ── 6. Alembic revision length (migrated from .githooks/pre-commit) ──
# alembic_version.rev_num is varchar(32); longer revision IDs crash
# container startup. Check staged migrations' revision/down_revision lines.
for f in $STAGED; do
  case "$f" in
    */versions/*.py)
      while IFS= read -r rev_line; do
        # Extract the string literal: revision = '...'
        rev_id=$(echo "$rev_line" | sed -n "s/.*revision.*= *['\"]\([^'\"]*\)['\"].*/\1/p")
        if [[ -n "$rev_id" && "${#rev_id}" -gt 32 ]]; then
          error "Alembic revision ID in $f is ${#rev_id} chars (>32) — will crash container startup (varchar(32))"
          HAS_ISSUES=1
        fi
      done < <(grep -E "^(revision|down_revision)" "$f" 2>/dev/null || true)
      ;;
  esac
done
```

Note: `error`/`warn`/`pass`/`HAS_ISSUES` are already defined at the top of
change-validate.sh — reuse them, don't redefine.

### 2. Delete the dead hook

```bash
rm -f .git/githooks/pre-commit
# or empty it:  printf '#!/usr/bin/env bash\n' > .git/githooks/pre-commit
```

### 3. Update docs

- `docs/project_structure.md` (~line 88, the "shadowed" note): point at
  `ops/scripts/change-validate.sh` as the new home of the alembic check.
- `AGENTS.md`: update any reference to `.git/githooks/pre-commit` → the
  change-validate.sh section.

## Verification (must show evidence)

1. Create a test migration with a 40-char revision ID, stage it, run
   `bash ops/scripts/change-validate.sh` — expect the error + HAS_ISSUES=1.
2. Fix to a 12-char ID — expect no error.
3. `git commit` a real migration — confirm the check fires via the cortex
   pre-commit hook (not the dead local one).
4. Report the two outputs (fail + pass) back to the fleet.

## Why this is correct

- The cortex pre-commit auto-runs change-validate.sh when present — the
  check now fires on EVERY commit through the enforced hook chain.
- change-validate.sh is warn/error + HAS_ISSUES — the block comes from
  the same mechanism as all other cortex checks (fail-closed on error).
- No bypass path: the global hooksPath can't be overridden by a local
  .git/githooks file (that's the shadowing that killed the old hook).
