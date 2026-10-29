# Risk-triggered close-review depth — plan (lever E)

**Status: PLAN ONLY.** Nothing in this document is implemented. Next lever after
`docs/design/adversarial-review-cost-reduction.md` (whose A1 + A2 are shipped; its B and D remain
plan-only).

**Operator request (Luke, 2026-10-29):** *"we are overusing reviews. we should be using them for the
complex/risky tasks."* Advisory input recorded verbatim in
`docs/research/review-cost-advisory-chatgpt-2026-10-29.md`.

**Baseline it responds to:** `docs/evidence/review-cost-baseline-2026-10-29.txt` (the measurement
transcript; every number below is that artifact's own output).

---

## 1. The problem, measured

The close-gate is **size-triggered, not risk-triggered**, and its depth tiers no longer change who
judges. Three facts, all from the shipped code:

1. **A size threshold decides whether any review runs at all.**
   `mcp-servers/loop-gov-mcp.py` — `_complexity()` (l. 5123) sets
   `is_complex = bool(always) or (len(non_noise) >= COMPLEXITY_FILE_THRESHOLD or
   non_noise_lines >= COMPLEXITY_LINE_THRESHOLD)` (l. 5224), against
   `COMPLEXITY_LINE_THRESHOLD = 50` / `COMPLEXITY_FILE_THRESHOLD = 3` (l. 4456–4457).
   `end_change` then does `if not cx["is_complex"]: <skip review>` (l. 7080–7083).
   So a 50-line prose edit buys a review, and a 45-line rewrite of a security check does not —
   the gate is counting, not classifying.

2. **The two "tiers" no longer differ in spend.** `_tier()` (l. 5447–5465) returns `heavy` for an
   always-review path or ≥10 files / ≥200 lines, else `light`. But
   `_light_reviewer_model()` (l. 5424–5444) returns `REVIEWER_MODEL_DEFAULT`
   (`deepseek/deepseek-v4-pro`, l. 4472) unless an operator sets `ADVERSARIAL_REVIEW_LIGHT_MODEL`
   explicitly, and `_call_reviewer` (l. 5534–5545) routes the light tier to that same resolver.
   That is the 2026-10-18 operator reversal ("FLASH SHOULD NOT BE THE REVIEWER DEFAULT") applied as
   written — the light tier is now a settled decision about *who judges*, and its practical effect
   is that **every non-trivial close pays pro prices**. The tier still decides transport and wait
   budget only.

3. **The volume is pro-sized.** `blob_reviews` in the live store
   (`~/.hermes-cortex/data/loop-governance.db`) holds **940 `deepseek/deepseek-v4-pro` verdicts
   between 2026-10-18 and 2026-10-29**, peaking at 322 on 2026-10-22, against 60–115 cycles/day in
   the same window. And **199 of the 547 commits since 2026-10-15 (36%) touch documentation only** —
   no code, no config, no executable artifact.

For contrast, the push gate is *not* what forces this: a CLEAN receipt is required only when the
pushed range touches an always-review path (`docs/git-enforcement.md` l. 26, `README.md` l. 82;
implementation `ops/scripts/lib/review-receipt-check.py`). Ordinary ranges are exempt at push time —
so the review cost lands on the **close**, on every complex-by-size cycle.

**Honest limits of these numbers** (stated so nobody reads them as more than they are): `blob_reviews`
has no path column, so review spend cannot be joined to the docs-only commit share; cycles are not
commits and a single close can issue several blob reviews; and the day range is chosen, not sampled.
They establish the *order of magnitude* and where the gate decides — not a projected saving.

## 2. Lever E — the judge and the depth follow RISK, computed from the diff

One new pure function, `_review_class(repo, cx, own_paths) -> "A0" | "B" | "C"`, called from the
existing `end_change` review block (l. 7080) **before** the skip decision. It never replaces the
complexity measurement — it consumes it. Classification is **computed from git**, never read from the
worker's note (the existing docs-only rule at l. 4552–4585 already works this way and is the model to
follow).

| Class | Predicate (ALL must hold) | Judge | Rationale |
|---|---|---|---|
| **A0 — deterministic-only** | every changed path is documentation (`docs/**`, or a `.md`/`.txt`/`.rst` suffix) **and** no always-review path **and** no uncommitted code path **and** the range has ≥1 changed path | **no model call** | prose has no executable behaviour for a reviewer to falsify; the deterministic checks (syntax, `adversarial-verify.py` static gate, doctor) are the whole gate. Measured: 36% of commits. |
| **B — cheap judge** | code changed, **and** no always-review path, **and** not the protected surface of §3, **and** the range carries a test delta | cheap judge (explicit class rule, JSON contract, capped output) | ordinary code with executable evidence; a slower judge adds latency, not recall |
| **C — deep judge** | everything else, including every §3 case | pro (today's behaviour, unchanged) | enforcement, security, schema, config, unproven code |

**Class A0 is not a new idea in this repo** — it generalises the docs-only material budget
(l. 4584, `DIFF_CHAR_BUDGET_DOCS = 60000`) and the existing trivial-skip from a size threshold to a
risk class. What changes is which side of the line prose falls on: today a 3-file/50-line docs range
is "complex" and pays pro; under E it is classified by what it *is*.

## 3. Fail-closed rules (each is a test, not a promise)

1. **Unknown is C.** An unresolvable path, an unresolvable git state, an unresolved session identity,
   or an empty own-path set ⇒ **C**. Never A0.
2. **A0 requires the STRICT predicate.** One non-documentation path ⇒ not A0. A path whose
   documentation-ness cannot be determined ⇒ not A0. Any always-review path ⇒ **C**, checked FIRST
   (the l. 4423–4430 list, file-wins rule at l. 4437).
3. **Never self-declared.** A note claiming "docs only" changes nothing; a diff where every path is
   documentation is the only thing that qualifies (same rule the l. 4562–4566 comment already states).
4. **Uncommitted code ⇒ C** — the anti-dodge property of `_complexity` (l. 5127–5130) is preserved.
5. **The protected surface is C regardless of size**: `ALWAYS_REVIEW_PATHS`, schema/migration files,
   auth/credential handling, gateway/config, hooks, and any range that changes a file the deploy map
   owns.
6. **Every skip is recorded as a decision, not an absence.** The cycle row carries the class and the
   predicate's own inputs (paths, counts), so a later reader can recompute why no judge ran. A class
   with no recorded reason is treated as C.
7. **No bypass, no force, no raised timeout.** Union coverage at push is untouched; the 240s/600s
   ceilings (l. 4643–4651) are untouched.

## 4. What this lever deliberately does NOT do

- **It does not shrink `REVIEWER_MAX_TOKENS` (16000, l. 4508).** A small cap is a measured false
  negative: 900 and 3000 returned EMPTY content on a reasoning model (l. 4501–4507), which the gate
  reads as "reviewer unavailable" and uses to refuse a valid close. ChatGPT's "low max_output_tokens"
  is not adoptable here without re-measuring that failure; it is the one advisory item with a
  recorded counter-measurement against it.
- **It does not re-enable flash as a DEFAULT judge.** Class B names a judge for a *classified* risk
  band with an explicit rule; the default resolver keeps returning the canonical reviewer, so the
  2026-10-18 operator decision stands.
- **It does not make Pro reviews cheaper by trimming material.** Delta-bounding already exists
  (`DIFF_CHAR_BUDGET`, per-file floor + always-review priority, l. 4549–4636) and the runs at
  `REVIEWER_REASONING_EFFORT_DEFAULT = "none"` already answered in single-digit seconds (l. 4522–4531).
- **It adds no second review path.** `change-checklist` forbids one; every class routes through the
  same `_call_reviewer` seam, and A0's verdict is written by the same receipt writer (or explicitly
  not written, with the reason recorded).

## 5. Slices (one cycle each; RED first, then wire)

0. **E0 — the classifier alone.** `_review_class()` as a pure function with its own tests: docs-only ⇒
   A0; docs+one code path ⇒ C; always-review path ⇒ C; uncommitted code ⇒ C; unresolvable ⇒ C; each
   probed BOTH ways. **No wiring** — nothing changes behaviour yet.
1. **E1 — wire it.** The class gates the judge in `end_change`/`_call_reviewer` and is recorded on the
   cycle. Existing tests (`tests/test_review_attribution.py`, `test_reviewer_tier_wiring.py`,
   `test_gov_friction_fixes.py`) must not regress; the class must be visible in the stored row.
2. **E2 — the A0 evidence exchange.** A0's close must still carry runnable evidence (the deterministic
   gate's output, committed under `docs/evidence/`), and the close note must point at it — the same
   bargain the existing empty-diff class proposes (`adversarial-review-cost-reduction.md` §4 B2).
3. **E3 — measure the escape rate.** Sample A0 and B closes and run the deep judge on them anyway,
   recording verdicts; tune the class boundaries from the observed defect-escape rate, never from
   confidence. This is the advisory's stage 3 and the only basis on which the thresholds may widen.

**Sequencing note:** E0 is inert and cheap, so it can land while other work is in flight. E1 changes
the enforcement surface and must land as its own cycle with the `enforcement-change-safety` path.

## 6. Risks

- **A0 removes the independent reviewer from prose.** The counterweight is §5's E3 sample plus the
  deterministic pipeline; until E3 has data, A0's boundary stays at the strictest reading (pure
  documentation, nothing else). If the escape rate is non-zero, the class narrows — the same trade-off
  `adversarial-review-cost-reduction.md` §9 records for lever A.
- **A class predicate is a bypass surface.** Whoever edits the predicate controls what is reviewed, so
  `_review_class` lives on the same always-review surface as `_complexity` and is reviewed deep
  forever by construction.
- **The 36% figure is a commit share, not a review-share.** It motivates the class; it does not
  predict the saving. E3 is what replaces the estimate with evidence.
