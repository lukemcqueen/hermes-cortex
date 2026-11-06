# DeepSeek-Pro governed plan review — feeding, grounding, re-review (fleet)

When the operator says "review this decision/plan with pro" (Luke's standing
rule for any design/reorg/governance change: pro reviews the plan BEFORE
building), drive the governed reviewer, not a chat call. The recipe below is
the full loop; it has been run many times (PII-decisions, the mycortex
shared-brain plan, the repo-consolidation proposal — each through 2-4
FINDINGS rounds to CLEAN).

## The loop

1. **Open a governance cycle first** (`begin_change`) — the review needs a
   `cycle_id` and the terminal command is write-class without a lock.
2. **Write the decision/plan as a self-contained material file** (markdown):
   goal → current reality → the decided approach → and an **Evidence pointers**
   section (step 4). The file must be able to stand alone for a reviewer that
   sees ONLY its own text window.
3. **Run**: `python3 <repo>/ops/scripts/orch-bus/adversarial-review.py
   --cycle-id <N> --review --material-file <path> --reviewer-id
deepseek-v4-pro-0813`. rc=0, no stdout — the verdict goes to the store, not
   stdout.
4. **Read the verdict** from `~/.steadfaste-fleet/data/loop-governance.db`,
   table `adversarial_reviews`, latest row for `cycle_id` (parse `findings_json`
   for severity + technique + recommendation per finding).
5. **Expect `FINDINGS` dominated by `unverified-claim`** (and `fabrication` when
   a count is off). The reviewer cannot inspect the live tree — it verifies
   facts ONLY from the material window — so every factual claim must be PINNED
   to evidence, not reasserted in prose.
6. **Ground each finding**: add an Evidence-pointers section citing the EXACT
   commands whose output is the source (`git log --diff-filter=D -- 'src/*'`
   → hashes; `git ls-files | cut -d/ -f1 | sort | uniq -c` → counts; a grep
   output; the committed survey/decision doc + its commit; or the operator
   directive's record). Fix any count so its component list SUMS to the total.
7. **Fix genuine design gaps the reviewer catches** — it is not just a pin
   nag: it has caught real ones (a reserved-namespace leak, a migration owner
   backfill from the wrong source, a missing post-provisioning grant). Fix
   those BEFORE re-reviewing.
8. **Re-review with `--re-review`**, NOT a second `--review` — a second
   `--review` on the same cycle errors `already reviewed — UNIQUE constraint`;
   `--re-review` prints `superseded FINDINGS into history`. Repeat
   ground → re-review until `verdict: CLEAN`.

## The reviewer's nature (know what it is and isn't)

- It is an ADVERSARIAL defect-checker, not a design advisor: it finds
  fabrication / unverified-claim / logic holes in the material. To get pro's
  RECOMMENDATION on an open fork, put YOUR proposed answer inside the material
  and let it challenge the substance — a CLEAN verdict with no objection to the
  substance means pro does not contest that direction.
- Every restatement of a number must agree: assert "6 hits" in one bullet and
  the evidence-pointer says "3 hits" and that contradiction is itself a high
  finding. Reconcile every number everywhere it appears.
- `--reviewer-id deepseek-v4-pro-0813` is the pro model (Luke: pro for
  design/review, flash for implementation).
- Grounding is a dialog: the review is not clean until every factual claim it
  quotes has a pointer. A KEEP-fit rule: the material's every assertion (file
  count, commit hash, command, directive, observation) maps to a reproducible
  command or a committed record.

## Pitfalls

- A sub-list that is N short of the total reads as `fabrication`: an `ops/`
  row listing 6 of its 9 subtrees (sum 1045 vs 1053) was flagged high. List
  EVERY component so it sums to the stated total.
- Dated RECORDS (evidence/older/prd archives) stay byte-identical — a
  reviewer skips them as history, and rewriting them falsifies what was run at
  that revision. State that exclusion explicitly in the material.
- A design that introduces a reserved name must forbid escaping AND pin a
  no-leak migration test for a legacy occupant of that name — the reviewer
  flagged the reserved-`shared`-namespace profile collision before any code.