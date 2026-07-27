# Full Review Checklist

## Pre-Work
- [ ] Load `cortex-preflight`, `documentation-auditing`, `change-checklist`
- [ ] `begin_change()` with task description

## Survey (Pass 1)
- [ ] List ALL directories under `ops/scripts/`
- [ ] List ALL docs in `docs/` (recursive)
- [ ] List ALL skill categories in `skills/`
- [ ] Check top-level structure (symlinks, caches, test files at root)

## Duplicate Detection (Pass 2)
- [ ] Find same-named files across directories: `find ... | sed 's|.*/||' | sort | uniq -d`
- [ ] Verify identical content via `md5sum`
- [ ] Check for deployment overlap (same script deployed to multiple paths)

## Naming Convention (Pass 3)
- [ ] Find underscore-named files: `find ops/scripts/ -name '*_*' -not -path '*/__pycache__/*'`
- [ ] Verify format: `.py` for Python, `.sh` for shell, no mixed extensions
- [ ] Check field names in JSON schemas for consistency

## Deployment Registration (Pass 4)
- [ ] Parse all `register('path')` calls from `cortex-update.sh`
- [ ] Compare against all `.py`/`.sh` files in `ops/scripts/` (exclude `__pycache__`)
- [ ] Flag unregistered scripts for review (many are intentionally unregistered — deployment via other means)

## Doc Cross-Reference (Pass 5)
- [ ] Collect all `.md` filenames in `docs/`
- [ ] Search `docs/*.md` + `AGENTS.md` + `README.md` + `CONTRIBUTING.md` for each filename
- [ ] Flag unreferenced docs (PRDs are expected to be unreferenced — note exception)
- [ ] Check zero-byte files (clearly stale)

## Stale Files (Pass 6)
- [ ] Root-level `__pycache__`
- [ ] Root-level `.pytest_cache`
- [ ] Test files at repo root (should be in `tests/`)
- [ ] `runtime` symlinks pointing to `core/`
- [ ] `.hermes-crontab` at root
- [ ] `.python-version` if stale
- [ ] Orphan `__pycache__` dirs in `ops/scripts/*/`

## Gap Analysis (Pass 7)
- [ ] Read all PRDs — check if features are actually built
- [ ] Check for PRD v1 vs v2 (supersession)
- [ ] Check `run-evals.py` standalone-execution gap (hermes_tools dependency)
- [ ] Cross-reference `cortex-doctor.py` vs `cortex-health.sh` — are they redundant?
- [ ] Check learning/knowledge pipeline scripts for consolidation opportunity

## Report
- [ ] Write structured report to `docs/repo-health-review-YYYY-MM-DD.md`
- [ ] List each finding with: file, issue, severity, action taken
- [ ] Separate "Fixed" from "Documented for Future"
- [ ] Include priority recommendations

## Clean Up
- [ ] Clean up temp files (test artifacts, temp dirs created during review)
- [ ] If files moved: update `cortex-update.sh` register/unregister
- [ ] If files renamed: update all cross-references
- [ ] Run doctor: `cortex-doctor.py --quiet` — 0 failures
- [ ] `git add -A`
- [ ] Verify adversarial gate didn't block false positives (bypass with `SKIP_ADVERSARIAL=1` for file moves)
