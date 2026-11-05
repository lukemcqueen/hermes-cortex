# Pinning a model default fleet-wide (dated snapshot over alias)

When a model is used as a DEFAULT (adversarial reviewer, delegation, cron
provider, chat), an unpinned OpenRouter id (`deepseek/deepseek-v4-pro`) is an
ALIAS that resolves to whatever the provider currently maps it to. A provider
revision bump silently becomes a cost increase (and a behaviour change) with no
config edit. To freeze it at a known price/behaviour, pin a DATED SNAPSHOT
(`deepseek/deepseek-v4-pro-0813`).

## The surfaces to sweep — a pin that misses one drifts back

1. **Code default constants.** Every `os.environ.get("…", "<model>")` fallback and
   every `*_MODEL_DEFAULT`. grep the bare id before and after the edit — a model
   default usually lives in several files (an orchestrator cron script, the MCP
   server that gates closes, the agent-backend wrapper, `.env.example`).
2. **The env-override template AND each live `.env`.** An env override BEATS the
   code default, so a host that sets `ADVERSARIAL_REVIEWER_MODEL=deepseek/deepseek-v4-pro`
   in its gitignored `.env` keeps the expensive alias no matter what the code
   default says. Update `.env.example`; check each host's `.env` for the old value
   (the fleet per-host `.env` is the one that normally wins, not the repo file).
3. **Agent-facing skills/docs that RECOMMEND the model** (the highest-leverage miss).
   A stale doc telling agents to "use deepseek/deepseek-v4-pro" makes them re-apply
   the old value via the env override, silently reintroducing the expensive
   revision. Grep the DEPLOYED skills tree (`~/.steadfaste-fleet/skills`) AND the
   repo `skills/` plus the config/reviewer docs (`docs/env-vars.md`, runbooks). Zero
   remaining bare-id references is the "will agents implement it properly?" check.
4. **Tests that pin it.** A model default is asserted twice per test file: the inert
   fixture/label literal (`reviewer_label="deepseek/...v4-pro"`) AND the assertion
   (`assert row[model] == "deepseek/...v4-pro"`). Sweep BOTH shapes, then run the
   tests — an edit on one shape leaves the other stale and the test fails when it
   reads the new value back from the code while the fixture still feeds the old one.
   Dynamic trails (`chosen == mod.CONSTANT`) follow the constant on their own; only
   the places that write the value LITERALLY go stale.
5. **The doctor/check that reads the canonical value.** Prefer one that READS the
   default from the source (a regex on the constant) so it tracks the pin
   automatically. A hardcoded expected value must be updated in the SAME change or
   it flags the new snapshot as a deviation.

## Verification

- `grep` the tested tree + deployed skills for the bare id → 0.
- Run the model-default tests; one must print the new snapshot as the resolved judge.
- The doctor's model-config check passes with the snapshot (`... (code default)`),
  not a deviation.

## Beware of scope creep

One alias is often used by several DIFFERENT surfaces — the adversarial reviewer,
the system-one/triage judge, the delegation model, ad-hoc design consult. The
operator may want only ONE pinned; scope before sweeping every mention. The
system-one ROUTER config (`config/jev-router-models.json`) may already use the
snapshot while the skill prose lags it — pin the prose to match, and check whether
`delegation.model` is left empty (children inherit the parent model) rather than
assuming it is pinned.

Full config of the reviewer surfaces (backend, model, effort, light-tier opt-in)
and where each is set: see the fleet's `docs/env-vars.md` and
`skills/devops/governance-closeout/references/reviewer-transport.md`.
