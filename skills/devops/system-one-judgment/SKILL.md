---
name: system-one-judgment
version: 1.0.0
category: devops
description: "Use when integrating Jev/von judgment providers or clients."
platforms: [linux]
---

# System One Judgment Integration

Typed AI decisions: send `state` + typed questions to a model, get calibrated
answers (Noul yes/no probability, Choice pick+distribution, Score ordinal) that
code composes with thresholds. Covers replacing an LLM prompt-and-parse step
with a cheap typed judgment, wiring a judgment model into a cron/gate, and the
hot-swap provider abstraction (design doc: steadfaste
`docs/design/judgment-abstraction.md`; reference client: hermes-cortex
`ops/scripts/judgment.py`).

## Canonical interface

- The wire format is `POST {base_url}/v1/systemone` with
  `{model, state, questions:{id:{type, instructions, criteria?}}}` →
  `{answers:{id:{type,...value}}, usage}`. Both Jev (hosted) and von
  (github wfzyx/von, Apache-2.0) speak it — adopt it AS the internal
  interface so hot-swapping is a config change (`base_url` + `api_key_env`
  + `model_id`), never consumer code.
- Docs are Mintlify: append `.md` to any docs.typesafe.ai page path;
  start from `https://docs.typesafe.ai/llms.txt`.
- Live docs are the source of truth for request/response shape — read the
  API page before assuming an unknown field is tolerated.

## Client rules (ops/scripts/judgment.py in hermes-cortex is the reference)

- **Validate every provider response**: answers must be a dict whose keys
  exactly match the question ids with matching `type`s. Anything else is a
  FAILURE — fall through the fallback chain and end `status="unavailable"`.
  A provider bug must never ship a silent missing/wrong answer.
- **Fail closed**: no eligible provider → `unavailable` and the caller
  escalates (LLM session / human). No silent defaults, ever.
- **Tier gating**: each provider profile carries a measured accuracy tier;
  a provider may serve a decision class only if its tier ≥ the class's
  `min_tier`. Unknown tier = ineligible.
- **Send the `Authorization: Bearer <key>` header** — the API 403s without
  it. Do not add extra top-level request fields — unknown keys 400.
- **Inject the transport** (`fn(url, body, timeout)`) so tests never hit the
  network; keep the API-key check on the real adapter only.
- **SSRF-guard `base_url`**: https required for public hosts; plain http
  only for loopback/LAN; link-local is NEVER allowed over http (cloud
  metadata surface).
- Keep the client stdlib-only and thin (~250 LOC): state assembly, weights,
  thresholds, and escalation live in the caller's code, not the client.

## Shadow mode (candidate validation)

- Shadow NEVER affects the primary answer or status: fire-and-forget, short
  timeout, failures logged not raised.
- Probation-gated, not default-on: a class gets a `shadow:` entry only while
  a candidate provider is under evaluation; `JUDGMENT_SHADOW=off` is a global
  kill switch.
- **Intelligent/adaptive shadow**: uncertainty first — shadow any call whose
  primary confidence (per-type floor) is below the floor, 100%; confident
  calls are sampled at `sample_rate`, which decays ×0.5 after a clean streak
  down to a permanent 2% drift canary. Tag every shadow record with its
  stratum reason (`uncertain`/`sampled`/`always`) — divergence stats must be
  aggregated per stratum or the uncertain-only bias overstates error.
- Read the decay state file on every call (no process cache); writers use
  tmp-file + rename.

## Pitfalls

- Score answers without level probabilities have no computable confidence —
  treat as uncertain (shadow) unless the provider sends an explicit field.
- Log every call (primary + shadow pair) to JSONL with provider, schema
  version, request, and answers — that log is the fine-tuning corpus for a
  future in-house model. flock the append; concurrent crons interleave
  otherwise.
- Calibration ≠ accuracy: von matches Jev on calibration but trails badly on
  accuracy — never let calibration parity justify auto-serving high-stakes
  classes; the tier gate exists for exactly this.
- Jev answers a narrow judgment only: no text generation, no reasoning, no
  tool use. If the task needs synthesis or explanation, keep the LLM session.
- The DeepSeek direct key may be unfunded — prefer the OpenRouter fallback
  (`deepseek/deepseek-v4-pro` via OPENROUTER_API_KEY) for pro-model reviews.
