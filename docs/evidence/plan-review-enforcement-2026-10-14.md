> `recorded-in: adversarial_reviews review_id=9e5fb9af-1455-43f7-9bb6-1417c022933a`

# Plan review — the review-provenance enforcement (operator standing directive)

Why this file exists: the operator's standing rule is "have deepseek pro ALWAYS review your plan
before building" (2026-10-14, after losing trust in my judgment). This is that review, and it went
through the GOVERNED path — `ops/scripts/orch-bus/adversarial-review.py --cycle-id 12589 --review` —
so the row it claims above is real and the gate that verifies such claims passes on this very file.

The plan I submitted: finish the enforcement (deploy+push; land the rule in change-checklist; a
code-bearing second review round; state residual limits), with the gate's actual source, its tests
and the measured live output attached — because the FIRST round returned 6 `unverified-claim`
findings precisely because I had sent prose with no code.

## What the reviewer found (verbatim findings are in the store row; dispositions here)

**ADV-0-1 (high) — remove the change-checklist edit.** "The operator explicitly rejected 'notes
instead of controls'. The gate is the control. The skill edit is, at best, advisory prose and, at
worst, a distraction." **ACCEPTED — step 2 is CUT.** I had planned to land a documentation rule and
had already argued to myself that a skill is "where agents read it". The reviewer is right that this
is the exact substitution the operator rejected, and my own memory carries the same lesson
("enforcement>verbal"). No skill edit was made.

**ADV-0-2 (high) — the doctor wiring was claimed, not shown.** Correct: the material quoted the
checker and its tests but not the doctor's own output. **ACCEPTED — committed**: step 4 of
`docs/evidence/review-provenance-2026-10-14.txt` runs the doctor and shows the `Review provenance`
line; the wiring itself (`check_review_provenance` in `cortex_doctor/checks.py`, registered in
`cli.py`) is committed in the same range.

**ADV-0-3 (medium) — the `model:` trigger is a weak signal** (a doc ABOUT a model trips it).
**ACCEPTED with a change**: the trigger stays (it is what closes the innocent-filename evasion) but
the declaration a file may make is no longer only "advisory" — a design document can now declare
`provenance: not-a-review`, which is TRUE rather than a false statement, and a test pins that case.

**ADV-0-4 (medium) — a row proves a review exists, not that it was independent** (the same agent can
run `--review` on its own cycle). **ACCEPTED — the OK line now prints the row's `reviewer_id` and
`model`**, so the reader judges the recorder instead of reading a bare "OK"; the residual is stated
in the source rather than implied away.

**ADV-0-5 (medium) — gameable paths**: a declaration can be a lie; a review delivered as a URL is
not covered at all. **ACCEPTED as stated limits**, written into the checker's source: the gate
guarantees nothing can CLAIM a recorded review without a row, not that a declared-advisory file is
honest. What it cannot honestly promise is not pretended.

**ADV-0-6 (medium) — resolve the first round's findings before re-submitting.** Correct: the first
round's findings were all "no code/diff/test output in the material"; this submission included the
source, the tests and the live output, and the reviewer was then able to attack the mechanism itself
(finding 3/4/5 are mechanism findings, not missing-artifact findings) — which is the resolution.

**ADV-0-7 (low) — cut scope.** ACCEPTED: the skill edit is cut, and the remaining work is this
artifact plus the deploy/verify of work already committed.

**ADV-0-8 (info) — "WHAT I WANT ATTACKED" pre-channels criticism.** Noted and accepted as a fair
criticism of my framing; the reviewer's own list went beyond my questions (its findings 1, 2, 6 and
7 are about my steps, none of which I had flagged as weak).
