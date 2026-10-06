# Reviewer transport — which engine runs the close-gate review

The material contract is in `adversarial-gate-material.md`. This file is the other
half: WHO performs the review, how it is dispatched, and how to tell which engine
actually ran.

## Two transports, one contract

`ADVERSARIAL_REVIEW_BACKEND` selects it. Default: `llm`.

| Transport | Key settings |
|---|---|
| `llm` | `ADVERSARIAL_REVIEWER_MODEL` (keep it DIFFERENT from the worker's model), `ADVERSARIAL_REVIEW_BASE_URL` (default OpenRouter — point it at a local or self-hosted endpoint to review offline), `ADVERSARIAL_REVIEW_API_KEY_ENV`, `ADVERSARIAL_REVIEW_TIMEOUT` |
| `agent` | `ADVERSARIAL_REVIEW_AGENT_CMD` (the CLI invocation; the prompt is passed on **stdin**), `ADVERSARIAL_REVIEW_AGENT_NAME`, `ADVERSARIAL_REVIEW_AGENT_TIMEOUT` |

Why an agent transport exists at all: an agent can open the repo, run the tests and
check the claims, which a single completion cannot. The recurring finding on this gate
is "a self-report is not execution evidence", so a reviewer that can go and measure is
a genuine upgrade — and it lets the review run on offline/local capacity.

## Rules that hold for EVERY transport

- **Configure the command; never infer it from a per-CLI flag table.** Agent CLIs each
  have their own flags, and a guessed one produces a wiring that exists and does
  nothing. A configured command also makes the transport open-ended: any agent works,
  including one this repo has never heard of.
- **A credential that is explicitly NAMED is honoured strictly.** When a named
  credential is absent the call REFUSES; silently falling back to a different key means
  the reviewer authenticated as something the operator did not choose.
- **Fail closed on every degenerate outcome.** An unknown backend value, a non-zero
  exit, and EMPTY output are each refused. Silence is never CLEAN.
- **No self-review.** The agent's declared name is compared against the change's git
  author — derived from the repo, not supplied by the operator. An author (human or
  agent) must not adjudicate its own work.
- **Read-only is the OPERATOR's responsibility.** The gate cannot revoke what the
  configured command allows, so the command must put the agent in its
  read-only/plan/sandbox mode. A reviewer that can write can edit until its own
  objections disappear.
- **Record which transport ran.** The stored review's reviewer field is `agent:<name>`
  for the agent transport and the model id for the llm transport, so a verdict stays
  re-derivable after the configuration changes.

## The optional triage layer

A fast typed judge ("System One") can CLASSIFY the reviewer's findings so ordinary code
applies policy: **MEDIUM+ blocks, LOW annotates.**

- **Enable with `ADVERSARIAL_TRIAGE_MODEL`; UNSET means disabled** — the gate then
  behaves exactly as it did before triage existed, with the reviewer's severities
  unchanged.
- **Annotation, never adjudication.** Triage may lower administrative noise; it may
  NEVER raise a severity, clear a finding, or pass a gate. Thresholds live in the
  caller, not the judge.
- **Entered only when the verdict is NOT CLEAN.** A CLEAN verdict produces no triage
  activity, so NO triage log line is the correct outcome — not a missing step.
- **Fail-safe by construction.** A missing client, a provider error, a non-`ok` status,
  or a reply the client rejects keeps the reviewer's severities. A judge outage can
  therefore never relax enforcement — nor tighten it.
- **Typed questions only**, one triple per finding, with the question ids binding each
  answer to its subject. See the `system-one-judgment` skill for the wire shapes — a
  `choice` question's `criteria` is a DICT, and a list is a failed request.
- **A protocol-compatible judge below the class's accuracy tier must stay INELIGIBLE.**
  Never lower the tier gate to make a local fallback "work": a skipped fallback that
  fails closed is safe, a fallback quietly serving above its measured accuracy is not.

## Verifying which engine actually ran

- **The stored review names it** (the reviewer field) — the authoritative answer for a
  verdict that already exists.
- **The gate logs its own decision** to `~/.hermes/logs/mcp-stderr.log`. Read the LAST
  matching lines: the log is append-only and long, so an unfiltered search returns the
  OLDEST matches and can make a recent review look as though it never ran.
- **"A pass is not evidence of a review."** Distinguish the outcomes — a
  below-threshold `skip`, a `CLEAN` verdict (reviewer ran, found nothing), triage
  lowering everything (`stored <verdict> but all LOW (n) — not blocking`), or findings
  with severities that blocked. Only a log line tells you which of these you got.
- **New transport or triage config is CODE**, so the long-lived MCP daemon must restart
  before it is live. A config VALUE does not need a restart once the gate resolves its
  own env per call — but until the code carrying that resolver is deployed, a value can
  sit correctly in the canonical env file and never arrive.

## When the reviewer is UNAVAILABLE (an auth fault, not a finding)

Symptom: `end_change` refuses with
`Cannot close: adversarial reviewer is UNAVAILABLE … (error: HTTP Error 401: …)`.
That refusal is the gate working — nothing ships unreviewed — and it is an
**environment fault, not a judgement about the change**. Do not start rewriting the
work to appease it; fix the credential path.

- **Probe with an AUTHENTICATED call, never a public endpoint.** Provider catalog
  endpoints (`/models` and friends) commonly answer **200 for a revoked key**, so they
  are a false green that costs a whole diagnosis cycle. The credential's verdict comes
  from a request that actually needs authorization — a small real completion, or a repo
  read as that identity.
- **Resolve the credential the way the COMPONENT does, then check every source in that
  order.** Env-var first, then the env files in the component's documented precedence
  (the cortex repo env outranks the deploy env, which outranks the Hermes env). A
  revoked value sitting in a HIGHER-priority source shadows the corrected one lower
down — so a fresh rotation can appear to "not work" while the component keeps reading
  the old secret. Compare candidate values by hash or length; never print a secret.
- **A long-lived process holds the environment it started with.** Env-first resolution
  means a stale env var outranks a corrected file forever, so a value can be right in
  the file and dead in the process. Unset/replace the variable and restart the consumer;
  a file fix alone is not live until then.
- **A rotation is a fleet-wide breaker until proven otherwise.** After rotating a
  leaked credential, treat EVERY consumer as a suspect and verify each with an authorized
  call — the reviewer refusing is just one symptom of a stale value shared by several
  components, and fixing only the reviewer leaves the others failing silently.
