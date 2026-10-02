# Runbook — Re-point a Host's LLM Cron Model Chain

**Use when:** a host's LLM crons are landing on the wrong model, or a delivery
header shows `⚠️ Provider fallback: <x> unavailable; using <y>`, or a provider
or model name in the chain has stopped resolving.

Applies to every agent host. The change is **per-host** (`.env` is gitignored),
so each host runs the procedure for itself and there is nothing to sync.

---

## 1. The symptom, and why it is easy to miss

A job pinned to a provider that no longer resolves keeps its pin. The run then
falls through the operator `fallback_providers` chain to a **paid** route — and
still reports `status: ok`. The cost appears; the pin hides it.

The only visible signal is the delivery header line:

```
⚠️ Provider fallback: <dead-provider>/<model> unavailable; using <live>/<model>
```

That line is the trigger. Do not wait for a job to fail — a dead pin never fails,
it silently spends.

## 2. Root cause pattern

Two independent layers can hold a stale model/provider:

| Layer | File | Notes |
|---|---|---|
| Env chain (primary) | `~/hermes-cortex/.env` | `LLM_CRON_MODEL` + `LLM_CRON_PROVIDER` + `LLM_CRON_FALLBACK1..3_*`. Gitignored — host-local. |
| Per-job pin | `~/.hermes/cron/jobs.json` | Survives env changes; a job with `model`/`provider` set does **not** follow the env chain. |
| Operator fallback chain | `~/.hermes/config.yaml` → `fallback_providers` | Resolved at runtime when the pinned route fails. |

`pin_cron_model()` in `install-crons.sh` / `install-orch-crons.sh` returns early
whenever `LLM_CRON_MODEL` and `LLM_CRON_PROVIDER` are both set — **the env chain is
the declared single control point** and manifest pins are ignored. Fix the env
chain and re-installs cannot re-pin a dead model.

## 3. Procedure

**First, the mechanism — two different questions, two different control points:**

| Question | Control point |
|---|---|
| What model do crons actually RUN on? | The **main agent model** — `hermes model`, i.e. `~/.hermes/config.yaml` `model.default`. An unpinned job inherits it (verified: `cron/jobs.py::_main_model_pin()` returns `(None, None)` for unpinned jobs; the scheduler then uses the main model). |
| Will a future manifest sync RE-PIN jobs to a dead model? | The **env pair** `LLM_CRON_MODEL` + `LLM_CRON_PROVIDER`. When both are set, `install-crons.sh pin_cron_model()` returns early and applies no pin, so jobs stay unpinned. |

Nothing in Hermes reads `LLM_CRON_MODEL` at fire time, so editing it alone does
**not** change what crons run on. Set the main model for that; set the env pair
to stop the installer re-pinning it.

### 3.1 Set the env pair (prevents re-pinning)

Edit `~/hermes-cortex/.env`, changing **only** the `LLM_CRON*` keys:

```
LLM_CRON_MODEL=<model-id>
LLM_CRON_PROVIDER=<provider>
LLM_CRON_FALLBACK1_MODEL=<different family>
LLM_CRON_FALLBACK1_PROVIDER=<provider>
```

Rules that matter:

- **The model id form is provider-specific.** `deepseek/deepseek-v4.1-flash` on
  `openrouter`; `deepseek-v4.1-flash` on the native `deepseek` provider. Check the
  provider's own catalogue before writing the value.
- **Make the fallbacks a different model FAMILY from the primary.** A chain of
  three same-family entries fails together.
- **Do not put a free tier in the primary slot.** Free tiers disappear; see §5.
- Preserve file permissions (`0600`) and take a backup first — `.env` is a
  secret-bearing file, so edit it with a surgical script or `patch`, never a
  blind overwrite, and never print its values.

### 3.2 Release per-job pins

Every job still carrying an explicit `model`/`provider` must be unpinned so it
follows the main model again:

```bash
# list first — never guess IDs
hermes cron list
hermes cron edit <job_id> --unpin
```

`--unpin` is the supported path. Do **not** hand-edit `jobs.json`, and do not
re-pin to a different free tier as a substitute.

Jobs whose `model`/`provider` are already empty need no action — they already
follow the env chain / main model.

### 3.3 Check the operator fallback chain

`~/.hermes/config.yaml` → `fallback_providers` is separate from the env chain and
is what a failing primary falls into. Drop any entry that names a dead provider or
a retired model:

```bash
hermes config get fallback_providers
hermes config set fallback_providers.1.model <model-id>   # dotted path indexing works
```

## 4. Verification (do not skip)

1. **Read back** the env keys and the pin state — confirm the values, not the edit
   command's exit code.
2. **Check the main model** that unpinned jobs will follow:
   `hermes config get model.default` / `model.provider`.
3. **Fire one real job** and inspect its delivery header:
   ```bash
   # via the cron MCP: action='run', job_id=<id>
   ```
   The banner must be **absent**. If it still names a fallback, the fix is
   incomplete — trace fire-time provider resolution rather than re-editing values.
4. A manual run does not update `last_status`; the delivery header is the evidence.

## 5. Pitfalls

- **`jobs.json` uses `id`, not `job_id`.** Reading the wrong key yields
  `Job not found: None` for every job — and no writes. Read the schema before
  scripting an edit.
- **A free-tier pin is not a cost control.** It is a cost *hiding* device. If the
  free provider dies, the pin persists and the paid fallback runs.
- **Retired model names still resolve as aliases.** DeepSeek's docs retire names
  while continuing to serve them (billed at the successor's price), so a stale
  name looks healthy in testing and can break without warning. Prefer current
  names.
- **`.env` is host-local.** Editing it on one host does nothing for the rest of
  the fleet — each host runs this runbook. There is no repo file to sync.
- **Peak/off-peak pricing is real.** DeepSeek's Flash tier is 2× during peak
  (01:00–04:00 and 06:00–10:00 UTC, Mon–Fri = 10:00–13:00 and 15:00–19:00 KST;
  everything else off-peak). Size cost expectations off the off-peak rate.
- **Cache-hit rate dominates.** A model switch costs a cold-cache run, so a
  nominally cheaper model can cost more in total. Switch at job boundaries, and
  not more often than the price windows actually change.

## 6. Rollback

Restore the `.env` backup (`.env.bak-<timestamp>`) and re-run
`bash ~/hermes-cortex/ops/scripts/cortex-update.sh` to redeploy. Re-pin any job
that was previously pinned with `hermes cron edit <job_id> --pin`.

## Related

- `skills/devops/cron-job-management/SKILL.md` — cron lifecycle and pin policy
- `skills/devops/llm-cost-optimization/SKILL.md` — cache economics, the cost levers
- `skills/devops/cron-cost-scheduling/SKILL.md` — peak/off-peak windows
- `docs/env-vars.md` — env var reference
