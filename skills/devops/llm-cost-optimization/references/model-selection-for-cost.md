# Choosing models and effort for cost without losing quality

Two model-selection episodes share one lesson: cost wins only when it does NOT
trade away the quality the selection gate exists to protect. Both need a
MEASUREMENT whose protocol is written down before the first call.

## Capability map before you turn on a per-model knob

Turning on per-turn `reasoning_effort` (or any per-model request knob) must be
driven by a measured capability map, never a guess: an unsupported value 400s
the request or is silently ignored, and the point is cost, so measure what each
value actually costs.

1. Probe EVERY pool model at EVERY candidate value with ONE controlled prompt.
   Record acceptance + output/reasoning tokens from the reply `usage` block.
   One variable per row: the value.
2. Include a CONTROL: the same request with NO knob field. It splits the two
   non-acceptance shapes that feel identical in the error text but need
different handling:
   - **level REFUSED while the bare request works** → the model just cannot be
     sent that value (e.g. a mandatory-reasoning model refuses `none`). Declare
     the model with the other accepted values only.
   - **bare request fails too** (a data-policy/guardrail 404 on every value AND
     the control) → a route/key problem, NOT a knob problem. EXCLUDE the model
     from the map, carrying `reason` + `evidence`, and declare NO value — an
     excluded model's request is left untouched, which is fail-safe.
3. Commit the probe (script + transcript + raw JSON) so the "unreachable vs
   refused" split is re-runnable and provable later; the probe's own output is
   the evidence the ladder sits on.
4. Capability-map keys are EXACT `provider:model` (the router normalizes the
   provider). An absent/wrong entry is fail-safe (request untouched). Record in
   the map WHY a model is excluded; a bare exclusion with no reason is a datum
   nobody can audit.

## `none` is OFF, not a baseline

On a reasoning model, `reasoning_effort: none` turns thinking completely off (0
reasoning tokens) while `low`/`medium`/`high` buy comparable thinking on
mechanical work — so the real decision is none-vs-any, and `none` on a task that
needs tools carries a measured regression (a tool-needing turn answered without
calling a single tool). Default mechanical turns to `low`; reserve `none` for
truly trivial/no-tool turns, and only where routing's tier-floor guarantees the
turn is not real work. One config value flips the ladder; prefer the safe rung.

## Replacing a gate/reasoner model: measure recall AND precision, not price

"Is there a cheaper pro model for reviews?" — price alone must never pick a gate
model, because a gate that rejects GOOD work costs the operator a revert of
every legitimate close. Run a head-to-head on the REAL prompt template with two
controlled inputs:

- **material with PLANTED defects** it must catch (recall of the failure modes
  the gate exists for: fabrication, forward-looking unverified claim,
  embedded injection);
- **material that must pass clean** (precision: any blocking finding here is a
  false positive).

Grade each candidate on BOTH. A cheaper challenger that manufactures false
positives on the clean material is worse than the per-call saving (often
$0.01–0.03); sampled top-3 cheapest reasoning candidates all previously
fabricated findings on clean work while the reasoner did not. Confirm a
promising switch on a replay over several REAL closes before changing a gate —
small-N (two materials) is directional, not definitive.

## Grating-headache: stating the grader so prose verdicts count

A grader that parses only a strict full-document JSON undercounts every verdict
a reviewer wraps in prose (measured: planted_caught=0 for all four candidates
while all four in fact REJECTED the planted material). Extract verdicts with the
same tolerant parser the real consumer uses — find first `{`, last `}`, `json.loads`
that window, else fall back to scanning for the verdict word (`CLEAN` /
`FINDINGS` / `REJECT`). Never discard the raw reply when the parse fails: keep
the full content so a human (or a re-grade) can reach the verdict the parser
missed.
