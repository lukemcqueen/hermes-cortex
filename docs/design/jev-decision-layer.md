# The Jev decision layer — install, shadow, and swapping the decision model

Status: installed and verified on one host (esther, 2026-10-28); routing is **on** (since
2026-10-28) and per-turn reasoning-effort routing is **on** (2026-10-29, see
«Per-turn reasoning-effort routing» below). This is the reference for the fleet rollout.

Upstream: `github.com/kerpopule/hermes-jev-skills` (MIT), 13 `SKILL.md` files + a Hermes plugin
(`hermes-jev`) + a stdlib-only `jev` CLI. TypeSafe Jev is a *decision* model: you hand it a state
and typed questions (`noul` yes/no, `choice`, `score`) and it returns calibrated answers. It never
writes text.

## Why this is worth having

Our turns burn frontier tokens on things that are not thinking: which model a turn needs, which of
~400 skills to load, which retrieved passages matter, which search results to open. Those are
decisions, not prose.

**Honest reading for this fleet:** our default model is already the cheap tier
(`openrouter:deepseek/deepseek-v4.1-flash`, $0.196/M blended). So routing mostly *keeps* what we
have; the saving is **escalation discipline** (pay for hard work, not for everything) plus the
non-model decisions — skill selection, memory filtering, search screening. Do not quote the
marketing multiple on this host; measure it.

## Install

```bash
git clone https://github.com/kerpopule/hermes-jev-skills ~/hermes-jev-skills
python3 ~/hermes-jev-skills/install.py --check     # ALWAYS first: it changes nothing
python3 ~/hermes-jev-skills/install.py
jev doctor                                          # key present, Jev reachable, pools
jev models suggest --write                           # create the routing pools
```

What it writes: plugins into `$HERMES_HOME/plugins/`, 13 skills into `$HERMES_HOME/skills/jev/`
(symlinked into `~/.claude/skills` and `~/.agents/skills`), one script, a `jev` symlink in
`~/.local/bin` and `$HERMES_HOME/bin`, and **two lines added to `$HERMES_HOME/config.yaml`** to
enable the two plugins. It backs that file up first. Nothing else is touched — verify with
`diff` against the backup it leaves, not by trusting the report. It creates no cron or systemd
units. `install.py --uninstall` reverses it.

It never reads, asks for, or prints the API key: `jev setup-key` is a separate private step.

## Shadow first (this is the contract, verified)

```text
/jev                    status
/jev routing shadow     decide and log, switch nothing   <- start here
/jev routing on         switch models
/jev notice on          show the one-line routing notice on routed replies
```

Verified by driving the plugin's own `llm_request` middleware (not by reading its docs):

| mode | decision | outgoing model |
|---|---|---|
| `shadow` | `medium · coding → openrouter:deepseek/deepseek-v4.1-flash · 179 ms` | **unchanged** (middleware returned `None`) |
| `on` | same decision | **swapped** — `{"request": {"model": "<the pool's pick>", …}}` |
| `off` | none | unchanged |

Decisions are logged, without prompt text, to `$HERMES_HOME/logs/jev-decisions.jsonl` — that log is
what you tune the pools from.

**⚠️ Pool order IS the money — the suggested order cost more, so it was replaced.** Measured
catalog prices ($/M blended, `jev models list`):

| model | price | role |
|---|---|---|
| `openrouter:qwen/qwen3.7-flash` | **$0.05** | first in `simple` — 1M ctx, vision, 3.9x under our default |
| `openrouter:deepseek/deepseek-v4.1-flash` | **$0.196** | first in `medium` — the model we already run and trust |
| ~~`openrouter:moonshotai/kimi-k2.7-code`~~ | ~~$1.068~~ | **REJECTED, in no pool** — what the suggested order picked for medium coding: 5.4x our default |

`jev models suggest --write` bands by price, but on this host it put `kimi-k2.7-code` first in
`medium/coding`, so turning `routing on` with the suggested pools would have **raised** spend on
medium turns by ~5x. `routing.json` was therefore reordered so the cheap trusted model is first in
every `simple`/`medium` pool (first fit wins); `hard` is left as frontier escalation, which is
deliberate spend. **No `moonshotai/kimi` reference remains in any pool.** Verified after the
reorder: a real medium coding turn resolves to `openrouter:deepseek/deepseek-v4.1-flash`
(`tier: medium · reason: medium coding · 179 ms`) — the same model, so no cost change, instead of a
5.4x one. Re-check after a day of shadow data, never from a hunch.

## Swapping the decision model (steadfaste / self-hosted von)

The decision model is **not** locked to TypeSafe. Three env vars move it, with no consumer-code
change, because both speak the typed `/v1/systemone` wire format:

```bash
TYPESAFE_BASE_URL=https://<steadfaste-host>/jev   # or http://127.0.0.1:<port> for a local model
TYPESAFE_MODEL=<model-id>                          # optional: which decision model answers
JEV_PROXY_API_KEY=<that gateway's key>             # the ONLY credential an override may receive
```

Verified properties (see `docs/evidence/jev-swap-seam-2026-10-28/`, re-runnable):

- **It works end to end.** With the override pointed at a local `/v1/systemone` stub, `jev route`,
  `jev ask` (`noul` + `choice` + `score` all validated) and `jev doctor` all answered **from that
  endpoint** — `doctor` names it as `endpoint_override`.
- **The real provider key never travels.** The stub recorded `bearer_is_expected_proxy_key: true`
  and `bearer_equals_env_typesafe_key: false`: the override receives `JEV_PROXY_API_KEY` only,
  never `TYPESAFE_API_KEY`.
- **Fail-open.** A dead endpoint leaves the turn on its current model (`routed: false`, reason
  `Jev unavailable (network)`, exit 0) — never a blocked or failed turn.
- **SSRF guard.** Plaintext to a non-loopback host is refused with
  `invalid_endpoint: use https:// (or http:// on 127.0.0.1 or ::1)`; redirects are not followed.

So "swap to a steadfaste model later" is a config change plus an endpoint that speaks the typed
wire format. Nothing in our consumers changes.

## Relationship to our own judgment client

The fleet already has `ops/scripts/judgment.py` + `judgment-providers.yaml` with the same wire
format and the same hot-swap premise (see the `judgment-integration` and `system-one-judgment`
skills). The rule that keeps them from drifting: **fleet code keeps calling `judgment.py`**;
`jev` is the agent-facing decision layer (model routing, skill selection, search screening) and
its `jevkit` is not a second integration point for our scripts.

## Per-turn reasoning-effort routing

The routing difficulty answer already buys the model; the same answer now also buys the
`reasoning_effort` level for that turn (reused, no second Jev call). Every reasoning-capable
pool model is asked the same mechanical prompt at each level to record (a) which levels it
accepts and (b) how many output tokens each buys — see
`docs/evidence/jev-effort-levels-2026-10-29/` (re-runnable `probe-effort-levels.sh`).

Measured: `none` turns thinking OFF on every reasoning model (0 reasoning tokens); `low` /
`medium` / `high` buy comparable thinking on mechanical turns. So the ladder is the cost
control: trivial→`low`, routine→`low`, substantial→`medium`, expert→`high` (chosen over
`none` on trivial to avoid the recorded "tool-needing turn answered without calling a tool"
regression when thinking is off).

- `effort.enabled` + `effort.levels` + `effort.models` (capability map) + `effort.excluded`
  live in the ONE reviewable artifact `config/jev-router-models.json`; `jev-router-pools.py
  --write` projects them into each host's `~/.hermes/jev/routing.json`, and `--check` /
  `--selftest` fail on drift or an unsound map.
- The capability map is exact `provider:model` (verified against the probe). Untested models
  keep their existing effort — the plugin only applies a level when that model's own list
  contains it.
- Two distinct non-acceptance cases, recorded separately: `z-ai/glm-5.3` refuses `none`
  (reasoning mandatory → listed without `none`); `qwen/qwen3.7-flash` 404s on every level
  AND the no-effort baseline on the probe key (OpenRouter data-policy guardrail → NOT an
  effort problem, so it is listed in `effort.excluded`, not in `effort.models`).

## Fleet rollout (not done)

One host is installed. A rollout needs the same three things on every host: the installer run,
`jev models suggest --write`, and the gateway restarted before `/jev routing shadow`. Do it on
this host first, with shadow data, then decide.
