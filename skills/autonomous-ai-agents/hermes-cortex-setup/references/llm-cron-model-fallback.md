# LLM Cron Model & Fallback Chain — Reference

Session provenance: 2026-08-31, fleet host (Esther). User request: "add the
free deepseek flash or pro from opencode as primary and deepseek flash as
fallback 1 and opencode deepseek flash as fallback 2 — for the LLM crons."

## Resulting chain (applied live)

- Primary (per-job pin on all 21 LLM crons): `opencode-free` / `deepseek-v4-flash-free`
- Fallback 1 (global `fallback_providers`): `deepseek` / `deepseek-v4-flash`
- Fallback 2 (global `fallback_providers`): `opencode-zen` / `deepseek-v4-flash`
  (base_url `https://opencode.ai/zen/v1`, api_mode `chat_completions`)
- Removed: `custom:ollama-local` / `qwen2.5:3b` — known-bad fallback model
  (emits token garbage in agentic loops; watchdog `KNOWN_BAD_FALLBACK_MODELS`
  flags `qwen2.5-coder:3b` — see `agent-cron-quality-watchdog.py`)

## Why the live repin alone was reverted

1. `hermes cron edit <id> --model X --provider Y` updates `~/.hermes/cron/jobs.json` per-job (CLI only — MCP cronjob tool has no model/provider params).
2. Next `cortex-update.sh` → `install-crons.sh`/`install-orch-crons.sh` → `create_cron()` drift-edit path → `pin_cron_model "$name" "$model" "$provider"` — and `pin_cron_model()` reads `ops/install/cron-manifest.yaml` FIRST; a manifest entry's model/provider **override** the env fallback `$LLM_CRON_MODEL` and the live pin.
3. Result: 14/21 pins silently reverted to the manifest's old values on the first deploy.

**Correct sequence (verified):** patch `ops/install/cron-manifest.yaml` entries → `hermes cron edit` each live job → `cortex-update.sh` → verify `jobs.json` still shows the new pins (0 mispinned).

## Env-driven fallback chain (fleet convention added 2026-08-31)

`ops/scripts/install-fallback-providers.py` was converted from hardcoded
(opencode-zen + qwen) to env-driven. It reads:

- `LLM_CRON_FALLBACK1_PROVIDER` / `LLM_CRON_FALLBACK1_MODEL` (default `deepseek` / `deepseek-v4-flash`)
- `LLM_CRON_FALLBACK2_PROVIDER` / `LLM_CRON_FALLBACK2_MODEL` (default `opencode-zen` / `deepseek-v4-flash`)

An empty model OR provider drops that tier (adversarially tested — a naive
`os.environ.get` produced a garbage entry with empty strings). Sourced from
`~/hermes-cortex/.env` (repo root). Run: `set -a && source .env && set +a &&
python3 ops/scripts/install-fallback-providers.py`.

`hermes fallback add/remove/clear` are TTY-interactive pickers — no flags.
Non-interactive alternative: `hermes config set fallback_providers '<json list>'`
(current `set_config_value` YAML-parses list/mapping-looking values).

## Verification recipe (end-to-end, no cron tick needed)

```bash
hermes chat -q "Reply with exactly: CHAIN_OK" -m deepseek-v4-flash-free --provider opencode-free
# expect: "⚠️ Model fallback: deepseek-v4-flash-free via opencode-free unavailable
#          (provider failure); using deepseek-v4-flash via deepseek." then CHAIN_OK
```

Also verify the chain config:

```bash
hermes fallback list                      # shows primary + fallback chain
grep -A8 '^fallback_providers:' ~/.hermes/config.yaml
python3 -c "import json; j=json.load(open('$HOME/.hermes/cron/jobs.json'))['jobs']; \
print(sum(1 for x in j if x.get('no_agent') not in (True,) and x.get('model')=='deepseek-v4-flash-free'))"
# count should equal total LLM crons after the repin
```

## opencode provider tiers (live-verified 2026-08-31)

| Provider | Auth | Aliases | Notes |
|---|---|---|---|
| `opencode-free` | keyless | `free`, `opencode_free` | Free tier on `https://opencode.ai/zen/v1`; empty Authorization header; no account needed |
| `opencode-zen` | `OPENCODE_ZEN_API_KEY` | `opencode`, `zen` | Paid tier, same base URL |
| `opencode-go` | `OPENCODE_GO_API_KEY` | `go` | `https://opencode.ai/zen/go/v1` |

- **Free deepseek does not exist right now.** `deepseek-v4-flash-free` is in the live `/zen/v1/models` list but a chat-completions POST returns `{"error":{"type":"server_error","message":"Error from provider (Console): Upstream request failed: Model is unavailable."}}` — promo ended. There is no `deepseek-v4-pro-free` at all (checked the live list).
- `OPENCODE_ZEN_API_KEY` / `OPENCODE_GO_API_KEY` ship as commented + EMPTY placeholders in `~/.hermes/.env` — a fallback entry referencing opencode-zen auth-fails until the user fills them in.
- **Never trust the model list for availability** — the relay lists delisted models. Prove with a real completion POST.
- Cron sessions consume the GLOBAL `fallback_providers` chain (`hermes_cli/fallback_config.get_fallback_chain`, used by `cron/scheduler.py`) when the pinned job model fails — the chain is not per-cron.
