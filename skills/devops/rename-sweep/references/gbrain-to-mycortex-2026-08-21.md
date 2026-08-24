# Worked example: gbrain → mycortex full sweep (2026-08-21)

Luke directive: "remove ALL gbrain references" → the 2026-08-21 purge.
168 files changed (+1017/−4569), 15 dead artifacts deleted, zero residual
tokens. All patterns below were observed live; the fixes are what shipped.

## Surface (before)

- `git grep -i gbrain` ≈ 281 matches across ~170 tracked files (200+
  truncated at the first pass — always get per-file counts before editing).
- Git-tracked files NAMED `*gbrain*`: 3 docs, gbrain-autopilot.service,
  migrate-gbrain-postgres-to-mycortex.sh, import-gbrain.py, gbrain-maintenance
  skill dir (3 files), 4 gbrain-* reference docs, gbrain-baseline.json.

## Classification outcome

- **Deleted (15):** 3 gbrain-*.md docs; gbrain-autopilot.service (orphaned —
  zero installer refs); migrate-gbrain-postgres-to-mycortex.sh (one-shot
  migration, done 08-05); import-gbrain.py (reads decommissioned gbrain
  tables); gbrain-maintenance skill (maintains a dead system); 4 gbrain-*
  reference docs; gbrain-baseline.json (baseline capture retired with the
  engine); a superseded .patch proposal.
- **Functional renames:** `gbrain_sources_ok`→`mycortex_sources_ok` (health
  vector key — registry template/.example, orch-fleet-watchdog.py,
  orch-health-report.py, health-vector-push.sh `V_GBRAIN*`→`V_MYCORTEX*`);
  `knowledge.gbrain`→`knowledge.mycortex` (agent card); `"GBrain Sync"`→
  `"Mycortex Sync"` (dashboard key + test); psql `-U gbrain -d gbrain`→
  `-U mycortex -d mycortex` (fleet verifier — was connecting to a
  nonexistent role, a live bug); `gbrain_search()`→`mycortex_search()`;
  `fix-gbrain`→`fix-mycortex`; `FIXED_GBRAIN`→`FIXED_MYCORTEX`;
  `gbrain_connection_failure`/`gbrain_health_check_failed`→mycortex_*;
  test-mycortex-schema.sh container `gbrain-postgres`→`mycortex-postgres`
  and hermeticity guard now refuses the live `mycortex` DB.
- **Dead code removed:** cortex-update.sh `update_gbrain_binary`/
  `restart_gbrain_sync` stubs + callers + register lines for deleted
  scripts + orch-cron grep pattern; doctor's gbrain stale-artifact
  detection block (decommission complete — leftovers no longer expected);
  heartbeat/remediation/remediate autopilot-sync monitoring blocks;
  install.sh `GBRAIN_PG_PASSWORD` migration block + legacy plugin-name
  grep + dead ollama-linux-*.tgz llama-server extraction (URL 404s;
  mycortex is pure Python); mycortex CLI + migrate.py `~/.gbrain/config.json`
  connection fallback.
- **Historical docs** got "legacy brain" (never the new term): elicit
  transcripts, research/review reports, design comparisons
  (mycortex-DESIGN.md "the legacy brain stored slug paths" — replacing
  with "mycortex" would have falsified the design).

## Guard table (order matters)

Exact tokens first, then phrases, then catch-all:
`gbrain→mycortex`/`gbrain -> mycortex` → `legacy → mycortex`;
`gbrain decommissioned|deprecated` → `legacy brain …`;
`(gbrain replacement)` → `` (drop); `gbrain-command` → `legacy brain command`;
`gbrain-autopilot` → `legacy autopilot`; `com.gbrain.autopilot` →
`legacy autopilot`; `gbrain-sync` → `legacy sync`; `gbrain-postgres` →
`legacy Postgres` (after a fix pass — see mangles); `gbrain_source` /
`gbrain_sources_ok` / `gbrain_sources` → mycortex_*; `V_GBRAIN` →
`V_MYCORTEX`; `gbrain-baseline` → `legacy-baseline`; `gbrain-maintenance` →
`legacy-brain-maintenance`; `import-gbrain` → `legacy import`;
`migrate-gbrain-postgres-to-mycortex` → `legacy-postgres-migration`;
`gbrain-doctor` → `legacy-brain-doctor`;
`gbrain_connection_failure` / `gbrain_health_check_failed` → mycortex_*;
`GBRAIN_PG_PASSWORD` → `MYCORTEX_PG_PASSWORD`; `GBrain Sync` → `Mycortex Sync`;
`knowledge.gbrain` / `gbrain Knowledge` → mycortex; then case-preserving
catch-all: active files → "mycortex", historical files → "legacy brain".

## Every mangle class observed, with fix

| Mangle | Cause | Fix |
|---|---|---|
| `install-legacy sync.sh` (space in filename) | guard `gbrain-sync`→`legacy sync` hit `install-gbrain-sync.sh` | re-slug → `install-legacy-sync.sh` |
| `~/.legacy brain` (space in path) | catch-all hit `~/.gbrain` | → `~/.legacy-brain` |
| `com.legacy brain.sync-watch` | guard hit `com.gbrain.sync-watch` | → `com.legacy-brain.sync-watch` |
| `garrytan/legacy brain` (broken URL) | catch-all hit `garrytan/gbrain` | → `garrytan/legacy-brain` (slug) |
| `main.legacy brain` | catch-all hit `main.gbrain` in a tree diagram | → `main.legacy-brain` |
| `"Mycortex Sync --source moses"` | case-insensitive guard `GBrain Sync` matched the COMMAND `gbrain sync --source` | → `mycortex sync --source` (lowercase command) |
| `~/.mycortex/sync-watch.sh` | catch-all hit the legacy home dir | → `~/.legacy-brain/sync-watch.sh` |
| `mycortex replaces mycortex` | both sides of "X replaces Y" replaced | rewrite → "the legacy brain was replaced by mycortex" |
| `gbrain_search`, `gbrain_legacy_*`, `FIXED_GBRAIN` SURVIVED | `\bgbrain\b` — underscore is a word char | exact-token replacements in pass 2 |
| `gbrain-baseline.json` refs survived | underscore/guard mismatch | exact-token fix |

Mangle scan commands after the bulk pass:
`git grep -n 'legacy brain/\|~/.legacy \|install-legacy \|legacy brain\.'` and
`git grep -n 'Mycortex Sync\|mycortex autopilot\|replaces mycortex'` — both
must return 0 (except intended service labels).

## Deleted-ref sweep (caught by tests, not by luck)

- `test_mycortex_parity.py::test_golden_expected_paths_exist_in_repo`
  FAILed on golden-queries.json HC-006 whose expected_top3 pointed at the
  deleted gbrain docs → deleted the HC-006 entry; count invariants
  (25≤queries≤30, exactly 10 isolated) still held.
- DOCS-INDEX.md rows for the deleted migrate script + parity `--mode
  baseline` (file gone) → removed/reworded.
- mycortex-DESIGN.md `tests/fixtures/legacy-baseline.json` mention (file
  deleted) → reworded to "retired with the legacy brain".
- cortex-update.sh register lines for the two deleted scripts → removed;
  the two stub functions + their call sites → removed.

## Concurrent-push rebase (the dogfood gate teaches you)

While the sweep ran, Moses committed Titus's resend (`fbe1d00a`,
"validate installer scripts…") + a doctor fix (`87c28488`). First push was
BLOCKED by the pre-push dogfood gate: "Deploy sync — HEAD (mine) ahead of
last deploy". `git pull --rebase origin main` → 3 conflicts (install.sh,
cortex-profile.sh, seed-project-brain.sh) — all trivial.

**Trap:** resolving with `git checkout --ours ops/install/install.sh`
reverted MY whole-file sweep for that file (origin's install.sh still had
16 gbrain refs — Titus's relabel was partial). cortex-profile.sh and
seed-project-brain.sh were fine (Titus's versions were already gbrain-free).
Fix: restore your version (`git show <my-sha>:<file> > <file>`), re-apply
the one good cosmetic hunk from origin (reworded to avoid the banned term),
re-verify `grep -ci gbrain` == 0, `git add`, `git rebase --continue`.

**Stash trap:** a `git stash`/`git stash pop` cycle to compare PII-scan
output silently UNSTAGED all 168 files (`git stash pop` without `--index`).
Re-stage with `git add -A` before continuing.

## Verification results (what a clean sweep looks like)

- `git grep -i gbrain` → 0; token-mangle greps → 0.
- bash -n × 16 OK, py_compile × 21 OK, JSON/YAML valid (deleted files
  report FAIL — ignore).
- Adversarial gate A2 PASS on all 20 changed scripts.
- test_mycortex_parity 14/14 (post HC-006 removal).
- Live dashboard test: "GBrain Sync" label fail was DEPLOY-ORDER lag — the
  running service still served old code; passes after cortex-update redeploy.
- PII scan warnings (curl -u examples, non-placeholder domains) were all
  pre-existing; 0 BLOCKs; verified by comparing flagged lines against the
  diff.
- Deploy: `cortex-update.sh` → doctor "Remove: …" for stale deployed
  artifacts (migrate-gbrain…sh, gbrain-maintenance skill dir) → rm → doctor
  clean (Deploy sync ✅).
