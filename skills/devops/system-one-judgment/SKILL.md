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
- **Exact live shapes (verified against the hosted API, not inferred from the
  client):** `model` is REQUIRED — omitting it is a 422 with
  `loc: ["body","model"]`. A `choice` question's `criteria` is a **DICT mapping
  each option to what that option means**, never a list: a list returns 422 with
  `loc: ["body","questions","<id>","choice","criteria"]`,
  `msg: "Input should be a valid dictionary"`. Choice answers carry `confidence`
  alongside `probabilities`. A list here is not documentation shorthand — it is a
  failed request.
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
- **Resolve the credential from the env FILES, not `os.environ` alone.** A
  consumer running inside a long-lived server (a gate daemon spawned by a
  supervisor) usually does NOT inherit the judge's key: the supervisor started
  long before the key was configured, so `os.environ` is empty there while the
  key sits in the host's env file. Resolve in order — process env, then the
  host's own env (`CORTEX_ENV_FILE`, else `<repo>/.env`, else the deploy root),
  then the Hermes env last — extracting ONLY the named key and re-reading per
  call. Fall back to the named env var, never to a DIFFERENT credential:
  silently judging with a key the operator did not choose is worse than
  `unavailable`.
- **Validate the question SHAPES you send, locally.** Response validation is
  only half the contract; a locally-wrong REQUEST is the expensive direction,
  because it costs a round trip and returns `unavailable` — which reads as "the
  judge is down" when the judge is fine. Reject a non-dict `criteria` or an
  unknown `type` before the call, so the mistake fails in milliseconds with a
  reason that names the field.
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

## Consumers (who can actually answer typed questions)

- **A typed judgment needs a provider that speaks typed questions.** Chat-completions and embedding models cannot serve a `noul`/`choice`/`score` set: an embedder produces no judgment output at all, and a small chat model needs a shim parsing a JSON blob with no schema guarantee — never a reliable backstop for a gate. So "primary judge + local backup" is realistically **one judge + a fail-safe**: on `unavailable`, the consumer keeps the existing verdict (reviewer's severities, LLM's judgement) and proceeds with no judgment rather than a fabricated or half-parsed answer.
- **Two routes to Jev, and they are not equivalent:** on OpenRouter `typesafe/jev-router` is reachable today with the existing `OPENROUTER_API_KEY`, but it is a dynamic router (pricing reported as `-1`, `endpoints: 0`) and carries **no tier metadata**, so a `min_tier` gate cannot apply to it; TypeSafe-direct `jev-latest` is deterministic and tier-gated but needs its own secret. Choose deliberately — availability vs gateability.
- **Thresholds and question wording live in the consumer.** The client returns the answer; only the caller may own the cutoff that consumes it, so a threshold is a versioned, reviewable configuration change, never a literal buried at the call site.
- **Classification-only triage is the safe shape:** ask the judge to *classify* (does this finding cite a real artifact? administrative or judgement? low/medium/high?) and let code apply the policy. A judgment may lower administrative noise; it must never raise a severity or pass a gate. On `unavailable` the consumer proceeds with the original severities, so a judge outage can never relax enforcement.
- **Question ids must bind to the subject** — embed the finding id (`A1.cites_artifact`). The client's exact-match validation then turns a dropped or invented answer into a hard failure instead of a silently mis-assigned classification.
- **A typed triage is a question TRIPLE per subject, with the cutoff in the consumer.**
  For an adversarial-gate finding: `<fid>.cites_artifact` (`noul`), `<fid>.class`
  (`choice`: administrative|judgement), `<fid>.severity` (`choice`: low|medium|high).
  Code then applies policy — e.g. "administrative AND noul < 0.7 → annotate as LOW",
  and never a raise. The question set IS the interface, so it is versioned together with
  the threshold that consumes it; a numeric literal at the call site is unreviewable.
- **An ineligible fallback being SKIPPED is correct — never lower `min_tier` to make a
  fallback "work".** A protocol-compatible local provider below the class's tier is not a
  backstop; the call fails closed and the consumer keeps the original verdict. Triage
  failing without changing any verdict is safe by construction; a fallback quietly serving
  a class above its measured accuracy is not.
- **Deploy the client and its config together.** The client resolves its provider file as
  `Path(__file__).parent/<config>` (plus an env override), so registering one without the
  other leaves every call `unavailable` while the config looks present — and a consumer
  script absent from the deploy map exists only in the repo.

## Pitfalls

- **A client that discards the response body hides the cause of its own
  failure.** `unavailable` carrying only a status code (`HTTP Error 422`) is not
  a diagnosis. Capture the error BODY of one raw call before theorising: the
  validation detail names the offending field in `loc`, which turns a mystery
  into a one-line fix. Distinguish the classes — 401/403 is the credential,
  400/422 is the request shape, a timeout is the provider — because each has a
  different repair.
- **`unavailable` from inside the gate while a direct probe succeeds is a
  process-environment gap, not a judge outage.** A probe that sets the key
  itself proves the judge works, never that the consumer can reach the key.
  Check the LIVE process's environment (`/proc/<pid>/environ`, count occurrences
  only — a value must never be printed) for the key's env var; if it is absent,
  the fix is the client resolving the file (above), not the operator
  re-exporting the variable.
- **Log the client's error text alongside its status.** A consumer that logs
  only `status=unavailable` forces an extra investigation round; the client's
  error field names the cause (`missing API key env X`, `HTTP Error 422`, a
  timeout), and each class has a different repair.
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
- **Steadfaste's Ledger rejects IEEE-754 floats in hashed content** — a Jev
  answer is a probability (`noul: 0.87`, `score: 1.4`, `confidence`) and the
  Ledger's `canonical_bytes` returns `FloatRejected` for any float spelling
  (`-0`, `0.0`, `1e2`, nested). A `JudgmentEvent` that logs answers as
  decimals cannot be appended. Store each probability as an integer
  (parts-per-million) and keep the raw provider response by hash — never
  inline a decimal in the append payload.
- **A judgment is evidence, never authority, and monotone toward caution.**
  A machine-native output may route work or add scrutiny (escalate, raise
  review level) but may never remove scrutiny that readable policy sets, and
  never ratifies or passes a gate. Legibility moves from the answer to the
  question: the alien answer (`0.41`) need not be explained, but the
  question, the threshold that consumed it, and the resulting action must be
  versioned, Steward-ratified configuration. In steadfaste the judge is a
  governed worker role (like `critic`), never an in-core client.
