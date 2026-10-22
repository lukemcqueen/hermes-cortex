# Changing what the reviewer demands

A reviewer's demands are part of a worker's critical path, so an unsatisfiable one is a recurring
cost paid by every session on the host. This is how to change that safely — scoping the demand
WITHOUT relaxing the gate.

## Where the demand lives

The per-blob (and whole-range) reviewer is driven by a fixed prompt template under
`docs/templates/`, and the material it is shown is assembled by the gate module. Both are
the reviewer's constitution:

- the PROMPT states what it must demand and how to grade what it cannot see;
- the MATERIAL decides what it can see at all (one file's diff, bounded, plus the range it sits in).

An operator-owned file with a marker line (`=== REVIEWED MATERIAL ===`) is the contract: the script
reads it verbatim and appends material below the marker. Edits to it are orchestrator-only by design.

## Diagnose before you change it

A finding you cannot resolve by any edit is the signal, not the prompt text. Read the stored
findings and sort them by what they DEMAND:

- **a committed test or script** → satisfiable; a worker problem, not a policy one;
- **a fixture for a past measurement, or for something a person said** → unsatisfiable by
  construction; the behaviour measured is already replaced, and a quote is a fact;
- **content the window cannot show** → satisfiable only by restating the contract IN the file, or by
  reporting it as a window property rather than a defect.

When one file yields findings that are all of the second and third kinds, the friction is the
standard, and no amount of re-wording the file will clear it.

## The three rules that stop the churn

1. **Proof is scoped by claim type.** Behaviour the file controls keeps the strict requirement — a
   committed, re-runnable test in the range, still filed as an unverified claim without one. A past
   measurement or an external instruction needs a POINTER to its record instead, because neither can
   be a test fixture. State the strict case explicitly in the same rule, "not relaxed", so the
   scoping cannot be read as a general softening.
2. **A cited sibling is judged on its own blob.** The window shows one file, but the range is
   judged in a SERIES, so a file leaning on a sibling is not a contradiction — it is that sibling's
   own review. Say plainly that it is a property of the window, forbid the strongest severities for
   it, and stop it carrying a FINDINGS verdict on its own.
3. **A repo-internal REFERENCE is a pointer, not a claim.** A doc naming a repo path (`see
   CURRENT_STATE.md`, a cross-reference between docs) is DISCLOSURE: its evidence is that the target
   exists at the reviewed tip, which the window cannot show. Forbid `unverified-claim` at a blocking
   severity and `fabrication` outright, and — the half that actually stops the loop — NAME the demand
   being forbidden: "add the referenced file to the range" is RECURSIVE, because that file names
   further files, so satisfying it means editing all of them and then all of theirs. Keep the
   checkable case as a real finding: a reference THIS range invalidates (the diff renames, moves or
   deletes the target, or changes the referenced path) is filed at the severity the break costs.
   Without that second half the rule reads as a blanket exemption for docs, which is the thing the
   operator's condition forbids.
   **A reference is not the only window-boundary demand — the SHAPE recurs, so look for it before
   negotiating with the reviewer.** Any demand whose only resolution requires material the worker
   cannot put in the range (a file outside it, a re-run of a measurement that is gone, an
   instruction nobody wrote down) is a property of the WINDOW and belongs at `info`. When you meet a
   new one, the fix is the same three lines: state the rule, name the forbidden demand AND why it is
   unsatisfiable, and keep the checkable case blocking — then pin it with a test that fails if the
   strict case is dropped.

### What COUNTS as a pointer

The scoped rule says a past measurement or an external instruction needs "a pointer to its record",
and that phrase is worth spelling out, because two shapes that LOOK like pointers are not:

- **A finding id is not a pointer — it is the claim.** Citing the reviewer's own identifier
  (`(adversarial finding ADV-<cycle>-N)`) as the reason a line exists gets refused for exactly the
  reason the rule was written: the reader cannot resolve an id from this material, and the id does
  not say where the fact is recorded.
- **A date is not a pointer — it is the claim's timestamp.** "(operator directive, <date>)" states
  when, not where.

What resolves is a locator a reader can act on: the **cycle id and task whose description or stored
review carries it**, the **recorded issue/event number**, or the **evidence path** in the range. In
code, name the record rather than the identifier; in a commit or a note, name the artifact. The same
shape applies to your own provenance lines: state the revision and the command that produced them,
not the fact that they were produced.

## Make the rule ACTIONABLE, not aspirational

A rule the reviewer cannot apply changes nothing. The sibling rule only works if the reviewer is
told which files the range contains — so the per-blob material must NAME the range's other paths,
and be silent about siblings when the file is the only one. Check the rule has teeth by reading the
material a real pass would send, not by reading the prompt alone.

**An instruction the reviewer ignores is not a rule — answer the complaint with DATA.** Measured:
with the sibling rule stated in the prompt AND the range's paths named in the material, a reviewer
still filed the sibling dependence as a BLOCKING finding — six times against one file, each saying the
sibling "is not shown". What cleared it was stating, per sibling, its OWN recorded verdict and whether
that verdict is covered, which is the question the finding is actually asking. So when a window
complaint recurs after the rule is in place, stop re-wording the rule and put the fact it wants into
the material: resolve it from the same store the gate trusts, and label a sibling that still has
blocking findings outstanding honestly rather than waving it through.

## Ship it with a guard on the STRICT case

When an operator authorizes a change to the reviewer's standard, the condition is normally some form
of "this must not weaken enforcement". Make that condition checkable rather than promised: commit a
test that asserts the new scoping rules ARE present AND that the strict requirement and its finding
classification are still stated verbatim. Without that second half, a later edit can cite the
scoping policy while quietly dropping behavioural proof — the exact failure the condition exists to
prevent.

Templates for both halves (the assertions to make, and what each one protects) are in
`templates/reviewer-policy-guard.py`.

## Deploy is not live

Two separate lifetimes bite here:

- the running gate daemon is a LONG-LIVED process, so a prompt or module change reaches it only
after it reloads;
- a STORED verdict is evaluated by the RUNNING predicate, so an already-refused item keeps refusing
  until that process is replaced. The fix is live for the NEXT session, never retroactively.

So verify the change against the DEPLOYED prompt/material (the copy the close actually loads), and
expect to hand the operator the single reload command when the lifecycle guard refuses a restart
from inside a session.

## What good looks like afterwards

The same material that produced nine blocking findings should come back with observations you can
act on — a pointer to add, a file to open — and the strongest severities reserved for things a
worker can actually fix. If the findings after a policy change are still unsatisfiable, the rule was
not scoped, only narrowed.
