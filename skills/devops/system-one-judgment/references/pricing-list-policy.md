# Jev router pricing-list policy

How the model-routing pricing list (`config/jev-router-models.json`) stays honest. The list
is the single reviewable artifact that decides which model a turn gets (first fit wins), so
its invariants are ENFORCED by the tool's `--selftest` and by repo tests — never documented
only.

## The baseline is the model the host actually runs — and it is an anchor, not a label

Every "x cheaper" claim and every tier ceiling is a multiple of the `baseline`. When the
agent's default model changes (see `hermes-model-config`), the baseline MUST be re-anchored
in the same change, or the multipliers compare against a model nobody runs: pool heads stop
meaning what the notes claim, the medium pools' in-pool fallback ("the model we trust") is
the old model, and the deployed doctor's cost guard (it compares pool heads against the
host's actual current model) starts flagging heads that were fine. The fallback belongs to
the pool only while it is within the tier's ceiling — a cheaper baseline can leave the old
fallback stranded ABOVE the ceiling (measured: $0.560 base -> $0.357 base made the $0.560
fallback 1.57x, over the 1x medium ceiling, and the selftest — not the tests — caught it
because the selftest checks EVERY model in a pool, tests only the heads).

## Budget caps are ABSOLUTE $/M, never "Nx the baseline"

A multiple-of-baseline cap silently changes meaning when the baseline moves: re-anchoring
5x-of-$0.560 ($2.80) to 5x-of-$0.357 ($1.79) evicts the very model the budget was built to
afford. "Keep it affordable" is an absolute number — store it as one
(`policy.hard.max_price_usd_per_m`), and let the selftest fail if anything dearer than the
cap is PRESENT in the list at all (not merely not-first). Exempt the `rejected` record: it
exists to record WHY a dear model is not routed, price and all — but then make the rejected
reason COMPUTED from the list's own prices, never a second hand-written copy (a stale copy
of a ratio was measured saying 5.4x while the file's own prices gave 6.54x). One fact, one
place; the map carries numbers plus a `reason_ref`.

## The pool gives way, never the stated ceiling

A tier note saying "ceiling 0.5x" while a pool carries a 0.62x model is a promise nobody
can trust — it is contradiction-in-file, and a reviewer will (correctly) call it
fabrication rather than a nit. When contents and claim disagree, drop the models from the
tier (they belong one tier up), and pin the ceiling with a test that checks EVERY model in
every pool against the tier's ceiling, plus a test that a rejected model is never also a
promotion candidate.

## The whitelist is the control, not the head

"Only models on the whitelist may be routed" must be enforced, not annotated: selftest
FAILs if any hard-pool model is off the whitelist, if the whitelist is empty, if a model is
both whitelisted and rejected, or if any priced model is neither routed nor whitelisted nor
rejected. Whitelist criteria in this fleet: open weights, reasoning + tool_call, ctx >= 200k,
within the hard $/M cap — measured from the catalog, and the criteria themselves recorded in
the evidence extract next to the prices.

## Probe pitfalls (the installed plugin, driven without a gateway)

- A scratch `HERMES_HOME` has NO `routing.json`, so every decision reads
  `no tiers configured; run \`jev models suggest --write\`` and keeps the model — copy the
  live `~/.hermes/jev/routing.json` into the probe home and say why in the probe.
- The `notice` gate is state.json-driven and read PER CALL (`_state()` re-reads the file), so
  flipping `notice` needs no gateway restart; the plugin's owned probe proves it.
- Assert the STABLE prefix of a live judgement, never the exact value: confidence moved
  0.81 -> 0.79 between two runs of the same prompt and broke a pinned assertion. Stop the
  expected string at `confidence 0.` and note why.
- A stale `TYPESAFE_BASE_URL` export (pointing at a killed stub or dead port) makes `jev route`
  report a spurious network error and keeps the model — run probes with
  `env -u TYPESAFE_BASE_URL -u JEV_PROXY_API_KEY` and check the decision log row for
  contamination before trusting the result.
- The rendered notice string is `[Jev] {tier} . {specialty} -> {model} . confidence {c:.2f}`,
  switch-only (a kept decision renders nothing); `notice: on` + `routing: on` in state.json
  is the exact flip for "visible but still auditable" mode. The full per-turn audit stays in
  `logs/jev-decisions.jsonl` regardless.
