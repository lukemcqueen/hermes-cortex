# Detection-gate design (checks that decide "is this artefact class X?")

Use when adding a rule that classifies artefacts or state — a provenance requirement, a drift
detector, a policy linter — especially when the operator has asked for ENFORCEMENT rather than advice.

## Where the enforcement belongs

- The control is the ARTEFACT plus a BLOCKING check (a doctor FAIL, a pre-commit hook, a gate exit
  code). A rule that lives in prose — a skill, a runbook, a comment — is not a control; never offer
  it as one, and never let it substitute for the check after the operator has rejected that trade
  ("notes instead of controls").
- Wire the rule into a registered script with hermetic tests, and call the SAME implementation from
  the standalone path and from the blocking path. One rule, two callers.

## Choose the discriminator by measurement, once

- Enumerate candidate signals, then count what each would flag across the LIVE corpus in a single
  pass. Decide from that output. Do not iterate the rule in front of the operator: each round trip
  costs a full cycle and reads as churn, and the end state is no more correct.
- Record the refuted candidates in the source with the reason each failed, so the next reader does
  not spend the same budget re-trying them.
- Measured outcomes worth expecting:
  - **Name/path rules** evade by rename or move (a one-word change defeats the gate) and
    false-positive on unrelated files that merely share the word. Use content, not location.
  - **Prose phrase rules** fire on documents that DISCUSS the subject instead of being it.
  - **A marker searched anywhere in the file** hits unrelated deep text; scope it to a HEADER
    window, because a declaration belongs at the top.
- Prefer the signal carrying a FACT the artefact cannot have by accident (a named producer, a
  claimed record id) over one carrying style or vocabulary.

## Prefer claim-verification over pattern-matching

- Strongest cheap rule: if the artefact CLAIMS a relationship to a record
  (`recorded-in: <table> id=<x>`), assert the record EXISTS. A claim with no row is fabrication, and
  that is a finding the reviewer can check mechanically.
- Verify claims wherever they appear — any directory, any extension. A scope limited to one folder
  or `.md` is a one-move evasion, and the tree you scan is the tree that must be covered.
- Print the supporting record's own fields (who produced it, what model, when) beside the OK, so a
  reader judges the evidence rather than a bare tick. A row proves a record exists; it does not prove
  the producer was independent.

## False-positive cost is the failure mode

- A gate that fires on the healthy majority teaches its readers to scroll past it, and an alarm on a
  clean run is worse than no alarm — the reader stops believing the next one.
- Where a legitimate artefact can trip a signal, give it a TRUTHFUL declaration ("not-a-review",
  "not-managed-here") instead of forcing a false statement or maintaining an exemption list.
- Pin every measured false-positive class as a FIXTURE in the tests, so the rule cannot silently
  re-widen back onto it when someone next edits the pattern.

## Exit codes and honest limits

- `0` clean, `1` violation (named, with the remedy), `3` could-not-verify. "Cannot check" is a third
  outcome with its own message — never a pass, and never a negative verdict about the artefact.
- State in the source what the rule CANNOT promise: a self-declared exemption can be a lie; a
  deliverable that arrives as a URL or as chat text is not a file; a fact asserted in a note is not
  covered. An overstated claim sitting beside a narrow implementation is filed as fabrication, so
  including the limits costs nothing and protects the rest.
- **Decide the could-not-verify case FIRST, before any comparison runs.** Resolve the thing that
  determines whether a decision is possible AT ALL, and return the third outcome immediately. A
  comparison reached before its precondition still has to return something, and the PERMISSIVE
  branch is the one that runs — so the gate fails OPEN on exactly the input it cannot judge, which
  is the one input it must never pass. Ordering here is not style: a guard whose repo-resolution sat
  after the index comparison answered "permit" for an unresolvable repo, and would have allowed the
  very commit it exists to refuse. Pin the ordering with a case that supplies the precondition's
  ABSENCE together with every other input present, so a later refactor that reorders the branches
  fails loudly instead of quietly widening the gate.
- Probe the gate both ways before shipping it: a planted violation must be caught (rc=1, named), and
  the legitimate case must stay silent. A gate verified only in the reporting direction may be
  unfirable; verified only in the silent direction, it may already be disarmed.
- **Prove DISCRIMINATION, not just the two outcomes.** Take a COPY, reintroduce the exact defect the
  check exists to catch (invert the call, move the precondition back after the comparison), and
  assert the check FAILS there. A gate whose assertions pass on both the correct and the broken
  revision is measuring something other than the rule, and the copy keeps the real file clean while
  making the proof re-runnable by the next reader.
- **A gate is only as good as the DIRECTION of the call that acts on it.** Testing the decision
  function proves the decision; it cannot see how the caller consumes it. A guard documented as
  "returns 0 to refuse" wired as `if ! <guard>; then <refuse>` permits everything the guard refuses
  AND refuses everything it permits — with every decision test green, because none of them is
  looking at the call site. Assert the call site's shape too, and ANCHOR that pattern to the start
  of a line: an unanchored search for the inverted form also matches the assertion's own source
  text, so it reports the defect in a file that does not have it (measured, on the first attempt).
  Ship the guard with a runnable self-test mode on the component itself — see
  `references/close-review-evidence.md` for why the proof has to live in that file.
