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
               "instructions": "…", "criteria": ["…"]?}}}
-> {"answers": {"<id>": {"type": …, …value}}, "usage": {…}}
```

Answer shapes:

- **noul** → `{"type": "noul", "noul": 0.87}` — a probability.
- **choice** → `{"type": "choice", "choice": "administrative", "probabilities": {…}}`.
- **score** → a value on the question's scale.

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
