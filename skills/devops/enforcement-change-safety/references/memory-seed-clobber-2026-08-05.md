# Memory-Seed Clobber — Root Cause Chain and Fix (2026-08-05)

**Symptom:** on hosts where the deploy target is the live memory file,
cortex-update.sh overwrote personalized MEMORY.md with the blank seed template
on EVERY deploy — 7 clobbers in one day (16:46, 17:02, 19:05 post-merge/manual
deploys), saved only by the `deploy-backups/MEMORY.md.<ts>.bak` mechanism and
manual restore. First reported by Joseph (non-orchestrator) with evidence.

## Root cause chain (all three layers verified by reading the code)

1. **The register comment lied.** `ops/scripts/cortex-update.sh` (~line 512):
   ```bash
   # Templates → ~/.hermes/memories/ (guarded — only if dest missing)
   register "docs/templates/MEMORY.seed.md" "${CORTEX_DEPLOY_HOME}/memories/MEMORY.md"
   ```
   The comment claims dest-missing-only. The actual `needs_update()` (~line 595)
   overwrites whenever hashes differ: `[[ "$src_hash" != "$dest_hash" ]] && return 0`.

2. **The hash ALWAYS differs.** The live file is personalized (custom notes
   appended); the seed is a blank template. Once any memory is written, the
   hashes can never match → every full-mode deploy (full mode is the DEFAULT;
   the post-merge hook runs `bash cortex-update.sh` with no flags → full mode)
   overwrites real memory with the 1283-byte template.

3. **The doctor check was inverted.** `cortex_doctor/checks.py`
   `check_deploy_checksums` Category 1 (line ~3107) parses EVERY `register `
   line in cortex-update.sh and content-compares deployed vs repo source:
   - Clobbered (blank) → matches seed → doctor ✅ PASSES (broken state = healthy)
   - Restored (personalized) → differs → doctor ❌ FAILS + "Run: cortex-update.sh
     to resync" — exactly the destructive action.

## Topology: which memory file is LIVE? (verified on esther host)

| Path | On esther | Role |
|---|---|---|
| `~/.hermes/memories/MEMORY.md` | 2150 B, personalized | LIVE — Hermes reads `get_hermes_home()/memories`, default `HERMES_HOME=~/.hermes` (hermes_constants.py; no override in host .env) |
| `~/.hermes-cortex/memories/MEMORY.md` | 1283 B = pristine seed | Deploy target — dead copy unless `HERMES_HOME=$HOME/.hermes-cortex` (commented option in `hermes-cortex.env.example`) or `~/.hermes/memories` → symlink |

So on most hosts the clobber hits a dead copy (harmless but the doctor check is
meaningless there); on hosts with the HERMES_HOME override / symlink it hits
LIVE memory (data loss). Joseph's host is the live case. **Always determine
which path a host loads before diagnosing "memory wiped".**

Note: `memory-architecture` skill's install-step-9 table claimed seeds go to
`~/.hermes/memories/` — WRONG, they go to `${CORTEX_DEPLOY_HOME}/memories`
(install.sh line 1585: `HERMES_MEMORIES="${CORTEX_DEPLOY_HOME}/memories"`).
That wrong path claim is exactly why the topology is confusing.

## Fix design (agreed, orchestrator-only — esther landed it)

1. **Deploy — `register_seed()` in cortex-update.sh**: new map + function;
   copy ONLY when dest is missing, in BOTH full and delta modes:
   ```bash
   SEED_MAP=()
   register_seed() { local s1="${1:-}" s2="${2:-}" s3="${3:-}" s4="${4:-}"; SEED_MAP+=("${s1}|${s2}|${s3}|${s4}"); }
   ```
   Switch the 3 memory lines (MEMORY.seed.md, USER.seed.md, memory-readme.seed.md)
   from `register` to `register_seed`. Seed loop in `check_each_mapped_file`
   before the MAP loop: `[[ ! -f "$dest" ]] && copy_file "$full_src" "$dest"`.
   Cover seed dests in `clean_stale_deploys` (it builds dest lists from
   MAP/ORCH_MAP only — seed dests must be added or they look stale; note it only
   scans `${CORTEX_DEPLOY_HOME}/scripts`, so memories/ is safe today, but the
   doctor's check_stale_deploys must also recognize register_seed lines).

2. **Doctor — existence-only for seeds**: `check_deploy_checksums` already
   skips lines not starting with `register ` (so `register_seed` lines fall
   through the regex) — add an explicit Category 1b: parse `register_seed`
   lines, PASS if dest exists, WARN if missing, NEVER content-compare.

3. **Scope (Luke correction mid-session: "We shouldn't touch the hermes one")**:
   fix stays in the hermes-cortex repo (`ops/scripts/cortex-update.sh` +
   `cortex_doctor/checks.py` + docs). Do NOT write to `~/.hermes/memories/`
   (Hermes owns that file) and do NOT patch `~/.hermes/hermes-agent` upstream
   code. Upstream preference unchanged: local workaround + environment
   protection, no upstream PR unless Luke asks.

## Verification plan (used / to use)

1. Back up `~/.hermes-cortex/memories/MEMORY.md`; write a personalized marker
   line into it (simulating Joseph's state).
2. Run `bash ~/hermes-cortex/ops/scripts/cortex-update.sh` (full mode) → assert
   the personalized file is UNTOUCHED (hash identical), no backup created.
3. Remove the file → deploy → assert it re-seeds from template (dest-missing
   path still works).
4. Run cortex doctor → assert the Checksum/Memory-seed check is PASS with the
   personalized file present, WARN when missing — never FAIL.
5. Restore the original seed copy. Commit via governance pipeline; pre-push
   dogfood gate runs the deploy + doctor automatically.
