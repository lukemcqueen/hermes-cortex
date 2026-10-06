# Review Triage — the System One judge in the adversarial close-gate

**Status:** built, deployed, **OFF by default (fail-safe)**. 2026-10-02.

## What this is

The adversarial close-gate gets its findings from an LLM reviewer. That reviewer
is good at judgement and bad at bookkeeping: it restates what it has already been
told, and it inflates presentation problems to blocking severity, so cycles churn
on the same class of finding. The triage layer classifies the findings the
reviewer produced, and the gate then blocks only on the ones that are real.

**Triage is a classifier, never a judge.** It cannot raise a severity, cannot
clear a finding, and cannot pass a gate — a triage verdict is evidence that moves
the gate *toward caution*, never authority. Adjudication stays with the reviewer
and the orchestrator.

## The wire contract — and why a chat model cannot serve it

Jev is a **System One** model: typed questions in, typed answers out. The client
is `ops/scripts/judgment.py`:

```
POST {base_url}/v1/systemone
  {"model": …, "state": …, "questions": {
      "<id>": {"type": "noul" | "choice" | "score",
               "instructions": "…", "criteria": {"<option>": "<definition>"}?}}}
-> {"answers": {"<id>": {"type": …, …value}}, "usage": {…}}
```

Answer shapes:

- **noul** → `{"type": "noul", "noul": 0.87}` — a probability.
- **choice** → `{"type": "choice", "choice": "administrative", "confidence": 0.94,
  "probabilities": {"administrative": 0.03, "judgement": 0.97}}`.
- **score** → a value on the question's scale.

**`criteria` is a DICT, not a list.** Each option maps to what that option means
(`{"administrative": "Formatting or evidence attachment only.", "judgement": "A claim
about the behaviour of the change."}`). This was learned against the live API: a list
returns **HTTP 422** —

```
loc:  ["body","questions","<id>","choice","criteria"]
msg:  "Input should be a valid dictionary"   input: ["administrative","judgement"]
```

A list is therefore not documentation shorthand, it is a failed request. The client
now refuses it **locally** (`_validate_question_shapes`) so the mistake fails in
milliseconds with a real message instead of costing a round trip and being reported
as "the judge is unavailable" when the judge is fine.

`model` is **required** by the API — omitting it is also a 422 (`loc: ["body","model"]`).

`decide(decision_class, state, questions, config=None, primary_fn=…)` returns
`{status, provider, answers}`. The client validates that **the answer keys match
the question ids exactly** and that the **types match**; anything else is a
rejection (`status != "ok"`) and the gate keeps the reviewer's severities.

**Consequence:** a chat-completions model — local (Ollama) or remote — cannot
serve this endpoint. A plain LLM is **not** a drop-in backup for triage. A
protocol-compatible judge is required.

## The question triples

One triple per finding (capped at `TRIAGE_MAX_FINDINGS = 12`), with the question
id carrying the finding id so the client's exact-match validation binds each
answer to its finding:

| Question id | Type | Consumed as |
|---|---|---|
| `<fid>.cites_artifact` | `noul` | TRUE at `noul >= NOUL_TRUE` (**0.7**) — threshold composed **in the caller**, because thresholds belong to the gate, not the client |
| `<fid>.class` | `choice` (`administrative` \| `judgement`) | administrative **and** no artifact ⇒ lowered to LOW |
| `<fid>.severity` | `choice` (`low` \| `medium` \| `high`) | advisory; **never raises** |

## Severity policy

**MEDIUM+ blocks; LOW annotates.** A finding lowered to LOW is preserved with
`severity_reviewer` so the original severity stays auditable, and the triage
decisions are recorded. Layer 1 (deterministic refutation) is separate: a finding
that *quotes* text is refuted only if the quote is present in the material the
reviewer saw — a paraphrase is never refuted, and refuted findings stay in the
stored summary.

## Enabling it on a host

Triage is inert until a model is named. All three steps are required:

1. **Credential (by name only, value in the gitignored env file):**
   `TYPESAFE_API_KEY` — the Jev judge credential. Without it, `review-triage`
   cannot run and triage stays off.
2. **Name the model:** set `ADVERSARIAL_TRIAGE_MODEL` in the host's env
   (`~/hermes-cortex/.env`).
3. **Confirm the class exists:** `review-triage` in `judgment-providers.yaml`
   (deployed beside `judgment.py` by `cortex-update.sh` — the client resolves it
   as `Path(__file__).parent/"judgment-providers.yaml"`, or `JUDGMENT_CONFIG_PATH`).

Verify with the host env applied:

```bash
python3 - <<'PY'
import importlib.util, os
spec = importlib.util.spec_from_file_location("j", os.path.expanduser("~/.hermes-cortex/scripts/judgment.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m.decide("review-triage", {"material": "", "findings": []}, {})["status"])
PY
```

`unavailable` means triage is off (or the judge is unreachable) — and the gate
behaves exactly as it did before triage existed.

## Provider routing and the tier gate

`judgment-providers.yaml` → `review-triage`: `primary: jev`, `min_tier: T2`,
`fallback: [von]`.

- **von** speaks the same protocol and runs locally, but is **T3 < T2**, so the
  tier gate makes it **INELIGIBLE** for this class. An ineligible fallback is
  skipped and the call **fails closed** — safe, because triage failing never
  changes a verdict.
- **Do NOT lower `min_tier` to make the fallback "work".** That trades a
  validated judge for an unvalidated one purely to silence an alert.
- **nomic** (`nomic-embed-text`) is an **embedder** — it returns vectors, not
  verdicts. It cannot judge. Its place is the semantic arm of Layer 1, where it
  may only ever *escalate* ("possible paraphrase — do not auto-refute").

## Choosing the reviewer — LLM or coding agent

The verifier's transport is pluggable; its **contract is not**. A backend gets the
review prompt and must return text containing the findings JSON. Every backend
stays fail-closed: raising refuses the close, and **never** passes it, so a
misconfigured or unreachable reviewer can only make closing harder.

`ADVERSARIAL_REVIEW_BACKEND=llm` (default) — a chat-completions call. The model is
`ADVERSARIAL_REVIEWER_MODEL` (keep it different from the worker's model), and the
endpoint is `ADVERSARIAL_REVIEW_BASE_URL` (default OpenRouter, so a local or
self-hosted endpoint can review). Name the credential with
`ADVERSARIAL_REVIEW_API_KEY_ENV`; when you set it, it is honoured **strictly** —
the reviewer never silently runs with a different credential than the one you
named.

`ADVERSARIAL_REVIEW_BACKEND=agent` — shells out to a **coding agent**, prompt on
stdin, via `ADVERSARIAL_REVIEW_AGENT_CMD`. The command is configured rather than
inferred from a built-in table of CLI flags: each agent CLI has its own arguments
and a guessed one produces a wiring that exists and does nothing. This is also
what makes the backend genuinely open — any agent works, including one this repo
has never heard of.

**Reviewer tiering by measured complexity (2026-10-06).** The close-gate used to
run the configured backend on EVERY complex change. On a host whose backend is
`agent`, that meant a coding agent (e.g. pi) spawning for even a small diff —
~100s for a trivial prompt and often >300s on real material, which blew the MCP
client's 300s tool-call window and read as a fatal timeout when the review had
only just started. The gate now tiers reviewer depth on the same `_complexity()`
measurement it already uses to decide *whether* to review:

- **light-but-complex** — crosses the gate, but NOT an always-review surface and
  under the heavy bar (`<10` files and `<200` added+removed lines): reviewed by
  the **fast `llm` model** (`ADVERSARIAL_REVIEW_LIGHT_MODEL`, default
  `deepseek/deepseek-v4-flash-0731`, ~1s) even when `ADVERSARIAL_REVIEW_BACKEND=agent`.
- **heavy** — an always-review surface (enforcement/governance paths, incl.
  `loop-gov-mcp.py` and `cortex-update.sh`) or ≥10 files / ≥200 lines: the deep
  configured backend runs unchanged.

**Enforcement is unchanged.** Every complex change still needs an independent
CLEAN verdict before the lock releases; only the reviewer's *depth* is tiered,
and the light reviewer can still report FINDINGS that block the close. For a
heavy change the deep reviewer still takes minutes — the tiering accelerates
ordinary light changes, it does not decouple heavy ones from the MCP call.

Why an agent at all: an agent can open the repo, run the tests and check the
claims, which a single completion cannot — and the recurring review finding here
is *"a self-report is not execution evidence"*. A committed dogfood harness,
`ops/scripts/manage/dogfood-reviewer-tiering.py`, runs the REAL module and prints
PASS for the decision matrix and light/heavy/always-review routing; it is wired
into `tests/test_reviewer_backends.py::test_tiering_dogfood_script`.

Two rules that are not negotiable, both enforced in code:

- **Read-only.** The configured command must put the agent in its
  read-only/plan/sandbox mode. That is the operator's responsibility, because the
  gate cannot revoke what the command itself allows. A reviewer that can write can
  edit until its own objections disappear.
- **No self-review.** `ADVERSARIAL_REVIEW_AGENT_NAME` is compared against the
  change's **git author** (derived, not operator-supplied). An author — human or
  agent — must not adjudicate its own work.
- Silence is not CLEAN: a reviewer that exits non-zero, or prints nothing, refuses
  the close.

## Where the gate reads its config (decoupled from Hermes)

The gate is a cortex component, so it resolves its own configuration itself — it
does **not** depend on Hermes, and it does not need Hermes to pass the values in:

1. the **process** environment (wins, so an explicit export always overrides);
2. `$CORTEX_ENV_FILE`, else `$CORTEX_REPO/.env` (default `~/hermes-cortex/.env`);
3. the deploy root (`$CORTEX_DEPLOY_HOME/.env`);
4. `~/.hermes/.env` — **last resort only**, kept so a host whose credential happens
   to live there keeps working. It is not the source of truth for cortex config.

Two properties that matter operationally:

- **Only the named key is extracted.** The file is never loaded wholesale into the
  process environment — that would import every other secret and change behaviour
  for code that does not expect it.
- **Files are re-read on every call.** A long-lived MCP server therefore picks up
  an operator's change *without a restart*. (The one thing a restart is still
  needed for is deploying this code in the first place: a running server keeps the
  module it imported.)

Practical consequence: setting `ADVERSARIAL_TRIAGE_MODEL` in `~/hermes-cortex/.env`
is enough for the gate to see it — no `config.yaml` change and no Hermes env block.

## Failure is fail-safe — by construction

Disabled (no model named), client missing, provider error, non-`ok` status, or a
reply the client rejects ⇒ the classifier returns `None` and **the reviewer's
severities stand unchanged**. Triage can therefore never silently relax *or*
tighten the gate; a triage outage is invisible to correctness and visible in the
log.

## Do not

- Do not route triage through a chat-completions model or a shim that parses
  prose into "probabilities" — that adds the unreliable layer this design removes.
- Do not let a triage answer pass a gate or raise a severity.
- Do not hand-edit `judgment-providers.yaml` on a host to work around a tier
  gate; validate the tier or accept fail-closed.
