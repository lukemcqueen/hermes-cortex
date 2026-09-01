# LLM Cron Model & Fallback Chain — 2026-08-31 Trace

Full worked example of reconfiguring the LLM-cron model chain on a Hermes
Cortex fleet host. Complements `deploy-load-verification` SKILL.md
(Deploy ≠ Durable section).

## The request

"Add the free deepseek flash or pro from opencode as primary, deepseek flash
as fallback 1, opencode deepseek flash as fallback 2 — for the LLM crons."

Target chain:
1. Primary: `opencode-free` / `deepseek-v4-flash-free` (free tier, keyless)
2. Fallback 1: `deepseek` / `deepseek-v4-flash`
3. Fallback 2: `opencode-zen` / `deepseek-v4-flash` (needs OPENCODE_ZEN_API_KEY)

## Facts established (live, not from docs)

- `curl https://opencode.ai/zen/v1/models` is the authoritative model list.
- `deepseek-v4-pro-free` does NOT exist. Only `deepseek-v4-flash-free` exists
  on the free tier — and it returns `{"error":{"type":"server_error",...}:
  "Model is unavailable"}` on chat completion (promo ended; curated models.py
  agrees: "delisted (promo ended, now 401s)"). Set it as primary anyway: the
  chain falls through every run until the promo returns — that is the design.
- `deepseek-v4-flash` via opencode-zen without a key → `AuthError: Missing
  API key.` — the free tier is NOT a keyless backdoor to paid models.
- Free-tier working models (2026-08-31): laguna-s-2.1-free, nemotron-3-ultra-
  free, nemotron-3.5-lightning-free, hy3-free, x-preview-f-free,
  muse-spark-1.2-contributor-free, mimo-v2.5-free, ling-3.0-flash-fin-free.
- Provider plugins: `opencode-free` (keyless, alias `free`), `opencode-zen`
  (alias `opencode`, needs `OPENCODE_ZEN_API_KEY`), `opencode-go` (alias
  `go`). Live under `hermes-agent/plugins/model-providers/`.

## The #1 gotcha: manifest beats live pins

Sequence that bit us:
1. `hermes cron edit <id> --model deepseek-v4-flash-free --provider
   opencode-free` for all 21 LLM jobs → jobs.json correct (21/21).
2. `cortex-update.sh` ran → **14 repo-managed crons reverted** to
   deepseek/deepseek-v4-flash.
3. Cause: `install-crons.sh` drift-edit path calls `pin_cron_model`, which
   reads `ops/install/cron-manifest.yaml` FIRST; manifest model/provider WIN
   over the env fallback AND over the live pin (comment in install-crons.sh:
   "a per-cron model switch in the manifest is never reverted by a
   re-install").
4. Fix: patch `cron-manifest.yaml` (14 entries → deepseek-v4-flash-free /
   opencode-free), re-apply live pins, re-run cortex-update, verify pins
   survived. The 7 non-manifest jobs (local-*, job-opportunity-scanner,
   orch-task-*) kept live pins without manifest changes.

**Rule: manifest = durable source of truth for repo-managed crons. Live
pins are provisional until they survive a cortex-update.**

## Where each knob lives

| Knob | File | Who wins |
|---|---|---|
| Cron primary model | `ops/install/cron-manifest.yaml` (per-cron) vs `~/hermes-cortex/.env` `LLM_CRON_MODEL/PROVIDER` | manifest > env |
| Live job pin | `~/.hermes/cron/jobs.json` via `hermes cron edit --model --provider` | reverted by manifest on next deploy |
| Fallback chain | `~/.hermes/config.yaml` `fallback_providers` | only changes when `install-fallback-providers.py` RUNS (registered, never auto-run) |
| Chain env vars | `~/hermes-cortex/.env` `LLM_CRON_FALLBACK1/2_MODEL/PROVIDER` | consumed by install-fallback-providers.py when invoked |
| API keys | `~/.hermes/.env` (`OPENCODE_ZEN_API_KEY`) | secrets only; models/chain go in HC .env |

Env-file trap: `~/hermes-cortex/.env` (repo root, gitignored, real config) is
NOT the same file as `~/.hermes-cortex/.env` — on Esther the latter is a
SYMLINK to `~/langfuse/.env`. `install-crons.sh` sources
`${HOME}/hermes-cortex/.env` (repo root). Verify with `ls -la` before
editing; a model change written to the symlink target silently does nothing.

## Non-interactive paths

- `hermes fallback add|remove|clear` are INTERACTIVE TTY pickers — no flags,
  unusable in scripts/automation.
- Non-interactive chain write: `hermes config set fallback_providers
  '[{"provider":"deepseek","model":"deepseek-v4-flash"},...]'` —
  `set_config_value` YAML-parses structured values (`_looks_structured_value`
  → `yaml.safe_load`) and stores a real list, not a string.
- Canonical env-driven path (fleet convention): set
  `LLM_CRON_FALLBACK1/2_MODEL/PROVIDER` in HC .env, then
  `set -a; source ~/hermes-cortex/.env; set +a; python3
  ops/scripts/install-fallback-providers.py`. Empty model OR provider env var
  drops that tier (adversarially verified — the naive
  `os.environ.get(..., default)` version wrote a garbage
  `{provider:"", model:"", base_url:...}` entry for empty env; the fixed
  `_env_entry()` helper returns None and the list comp drops it).

## Verify end-to-end (real path)

```bash
# Primary currently unavailable → chain must fall through:
hermes chat -q "Reply with exactly: CHAIN_OK" -m deepseek-v4-flash-free --provider opencode-free
# Expect: "⚠️ Model fallback: deepseek-v4-flash-free via opencode-free
# unavailable (provider failure); using deepseek-v4-flash via deepseek." → CHAIN_OK

# Fallback 2 after key added:
hermes chat -q "Reply with exactly: ZEN_OK" -m deepseek-v4-flash --provider opencode-zen
# Expect: ZEN_OK with no fallback banner (primary succeeded)

# Key presence WITHOUT printing the secret:
python3 - <<'EOF'
import re
for line in open('/home/esther/.hermes/.env'):
    if line.strip().startswith('#'): continue
    m = re.match(r'^(OPENCODE_(?:ZEN|GO)_API_KEY)=(.*)$', line.strip())
    if m:
        v = m.group(2).strip().strip('"').strip("'")
        print(m.group(1), '=', 'SET len %d' % len(v) if v else 'EMPTY')
EOF
# then confirm `hermes auth list` shows the provider + credential.
```

## Fleet propagation gap (answer to "will all agents update?")

- Repo files (manifest, install-fallback-providers.py, docs) reach all agents
  via `agent-hermes-cortex-sync` (daily pull) + `cortex-update.sh` deploy →
  their crons DO get repinned on next install-crons run (manifest wins).
- BUT config.yaml `fallback_providers` is per-host and only changes when
  `install-fallback-providers.py` runs on THAT host — it is registered in
  cortex-update.sh but never invoked by it or by install-crons.sh. Peers keep
  stale chains (incl. qwen garbage tier) until the script runs there.
- API keys are secrets: `OPENCODE_ZEN_API_KEY` must be added per-host to
  `~/.hermes/.env`; cannot propagate.
- Closing the gap = wire `install-fallback-providers.py` into
  cortex-update.sh / install-crons.sh (small repo change), or dispatch a
  fleet command to run it on every host once.

## Governance notes hit during this change

- A stale PENDING loop-governance cycle from a dead session blocks `git push`
  (doctor FAILs on PENDING cycles → pre-push dogfood gate fails closed).
  Orchestrator remedy: `feedback_accept` the stale cycle with a note (it is
  cleanup, not interference), then re-run doctor to confirm 0 fail, then push.
- Foreign unstaged changes (another session's in-flight work) block
  `git pull --rebase`. Use `git -c rebase.autoStash=true pull --rebase` —
  autostash preserves the peer's working tree; never stash/clean/commit their
  files. The pre-push dogfood gate may still demand `cortex-dogfood.sh
  --force`; satisfy it, don't bypass.
