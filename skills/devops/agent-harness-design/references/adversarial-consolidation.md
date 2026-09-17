# Consolidating a grown design: adversarial party + gap ledger

When a design has accumulated many later-added principles and needs to be
consolidated into one coherent vision — then adversarially torn apart for gaps
before it can be called settled — run a delegator party with a **consolidator**
and an **adversarial reviewer**. This is the "did we really think of everything?"
step; never go from a nice consolidated doc straight to "done".

## The two-role party

Pin the delegated model (this fleet: `delegation.model: deepseek/deepseek-v4-pro`,
provider openrouter — confirm in ~/.hermes/config.yaml before dispatch). Dispatch
TWO parallel subagents via delegate_task, each with the full source list + the
list of LATER-added principles to fold in:

1. **Consolidator** — reads all sources, writes ONE complete redesigned hub
   (ASCII diagrams) folding in every later principle. Instruct: full markdown,
   bounded by start/end sentinel lines (e.g. `=====NEWDESIGN===== / =====END=====`).
2. **Adversarial reviewer** — attacks the consolidated/current design for gaps,
   contradictions, and edge cases. Instruct severity tiers S1 showstopper /
   S2 important / S3 notable, each = (a) the gap, (b) a concrete failure
   scenario, (c) a mitigation. Bound with its own sentinels.

## Integrate honestly — do NOT polish the warts away

- Replace the consolidation target with the consolidator's output (strip the
  sentinels; `sed '1d;$d'` works when each sentinel is its own line). Dedupe the
  header — merging often duplicates the original intro paragraph.
- Land the adversarial output as a **tracked open design ledger** (e.g.
  `docs/design/design-gaps.md`), NOT a throwaway review — with a header saying
  it is unresolved and that the spec's Acceptance must close it.
- Wire it into the spec's Acceptance/"It is DESIGN until" section so it keeps
  the covenant honest: the honest standing is **"settled in intent, open in
  mechanism"** — never "done." Closing a gap moves its rule INTO the spec (it
  becomes a settled design rule), then the item is removed from the ledger.

## Close a showstopper (S1): the gap-closure loop

After the ledger exists, each S1 showstopper is closed by turning it from a
*flagged risk* into a *settled mechanism* — one concrete procedure, repeated per
gap:

1. **State the mechanism as a one-paragraph contract first**, then write a
   dedicated design-spec doc under the design docs (e.g. `docs/design/<topic>.md`)
   with: the problem, the threat model (what it does AND does not stop), and a
   concrete "what gets built" (incl. a conformance test that proves the mechanism).
2. **Fold the mechanism INTO the governing spec** as both a short governing-truth
   entry AND a table/paragraph in the relevant numbered section — not just a
   one-off design doc sitting beside it. The spec is the source of truth; the
   design doc is depth.
3. **Mark the gap RESOLVED in the ledger** with a strikethrough note giving
   where the rule now lives (`core-spec.md` §…) and a pointer to the spec doc.
   Say which showstopper it was and how many remain.
4. **Commit** — spec + design doc + ledger update in one change.
5. Start the next cycle and repeat; give the user the next remaining gap with
   (a) the risk, (b) a concrete failure scenario, (c) the planned mechanical fix.

This is the pattern that turns "settled in intent, open in mechanism" into
closures one at a time, and it composes — each closure reuses the same
primitive (hash/integrity discipline) so later gaps (collusion, stop
enforcement) build on earlier ones.

## Pitfalls

- **Close every pending governance cycle before opening the next gap** — the
  enforcer rejects a new `begin_change` while an earlier cycle is unscored
  ("Close out your previous task before starting a new one"). Score
  (`feedback_accept`) + `end_change` the prior cycle first. When mid-gap you
  receive a substantial new steer, `end_change` the current cycle once scored,
  then start the new one.

- **Don't let one subagent consolidate AND review** — same model peering at its
  own output converges; they are separate, adversarially-oriented roles.
- **Feed the reviewer the same full principle list** as the consolidator — a
  reviewer that only sees the old doc misses exactly the new additions.
- **Keep the S1/S2/S3 (gap + concrete failure scenario + mitigation) format.**
  Bare "consider X" items are not actionable design debt.
- **Strip only the sentinel lines, never the content**, when merging subagent
  output.
- **ASCII diagrams must be machine-clean** (aligned borders, no mangled box
  characters) — a garbled diagram reads as sloppy regardless of content.
  Sanity-check borders by eye before committing.
- The reviewer will surface honest gaps IN the design that contradict the happy
  consolidated doc (e.g. Ledger tamper-evidence unspecified, agentic Operator
  hiding its own breaches, dry-run payload integrity loop, emergency stop not
  OS-enforceable, cross-Agent collusion undetectable). Record them verbatim as
  the ledger — these are the first things to design-and-prove next.
- **Folding a new governing truth into a numbered list can mis-nest it inside the
  prior entry.** The numbered governing-truths in the spec are long blockquotes
  with 4-space continuation indents. When your `patch` anchors on the tail of one
  truth to append the next, the fuzzy matcher can collapse the continuation
  indent and land the new `N.` *inside* the previous entry's paragraph — which
  then reads as one giant corrupted rule. Concretely this also leaks first-try
  typos ("traveable", stray tokens) into the new prose. Guard: after every
  patch to the numbered-truth list, re-read the block and confirm (a) the new
  number sits at column 0 flush with its siblings, (b) the prior truth's
  continuation lines are unbroken, (c) no stray tokens remain in the new text;
  fix indentation immediately rather than layering a second patch over the torn
  one.
