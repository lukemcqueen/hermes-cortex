# The two-window class, and how to fix the reviewer's constitution

## The class

A per-blob review window shows ONE file. Its siblings in the range are not in that window, the
reviewer has no file access, and no edit by the worker can put a sibling's content inside it. So two
demands are unsatisfiable BY CONSTRUCTION:

- "commit the test bodies in this window" — asked of a source file whose proof is a sibling test;
- "commit the implementation in this window" — asked of a test file whose subject is a sibling.

Symptom that identifies it: **the refusal count RISES as the worker answers it** (measured 2 → 2 → 4
→ 9 across four rounds), because answering one side of the pair produces the demand from the other.
Adding a pointer to the sibling makes it worse, not better. Escalation shape: the reviewer turns the
BOUND into a contradiction and files `fabrication` — and fabrication is never downgraded, so no
gate-side rule can absorb it. Do not keep editing the judged files; the class is not reachable that
way.

## Fix the constitution, not the judged files

1. Edit the reviewer's prompt template — the file the gate actually reads (orchestrator-only path) —
   and state WHY the demand cannot be met, not merely that it is discouraged. A rule that reads as a
   preference is dropped by the next edit.
2. Name the forbidden demand VERBATIM, and name what IS accepted instead: a
   `COVERED BY <path>::<test_id>` pointer to a test that exists at the tip. Whether it PASSES is not
   checkable from one window — that run belongs to the committed evidence artifact.
3. State that the sibling block is BOUNDED: absence from it is never evidence of absence and never a
   contradiction. A `fabrication` finding must quote what the material DISPROVES; a bound shows LESS,
   not the opposite.
4. Keep the checkable case blocking: a reference, path or symbol THIS range invalidates is a real
   finding, at the severity the break actually costs. Scoping a demand is not relaxing it.
5. Pin it in a test that reads the SHIPPED template — assert the rule's own wording AND that the
   strict case survives. A rule without a test disappears on the next rewrite of the prompt.

## A rule in the constitution is not a control

The reviewer is a sampling model reading its own constitution, and the prompt ALREADY forbade
"demand the evidence be duplicated into the file under review" while the reviewer filed it anyway at
HIGH for several rounds. So pair every prompt rule with a STRUCTURAL FACT the window can show: carry
sibling test ids with their first assertion line, or the sibling's symbol names, into the material.
A prompt-only fix buys one round; a fact in the window removes the inference. Same principle when the
fact is on the other side — a test file whose subject is a sibling should bind its dependency
EXECUTABLY (assert the function is defined in the module under test, exported, and still takes the
arguments the test passes), rather than asserting in prose that it exists.

## A template change is also the unblock for a stuck range

Verdicts are keyed on blob CONTENT plus the rules revision (a hash of the prompt text). Editing the
template changes that revision, which makes stored verdicts inadmissible and RE-SENDS the blobs the
old rules refused. That is the mechanism that re-opens a range whose blobs carry blocking verdicts:
fix the constitution, deploy, then close again. Do not re-roll the note and do not reach for `force`.

## Terminal exits when the class will not clear

- Record the measurement as an issue first (`record_issue`), then release deliberately:
  `advance_task_state(task_id=…, new_state='cancelled', reason=…)` — "a terminal task holds nothing".
  A cycle that was already scored leaves no PENDING-cycle leak, and the refusal advisory itself names
  this as a legitimate exit.
- Landed commits stay LOCAL and unpushed. A range on an always-review path cannot be pushed without a
  receipt, and a refused close mints none. An unpushed commit is the honest resting state — never a
  reason to force, and never a reason to edit another file to appease a finding.
- Every fix commit changes a blob, which buys a FRESH judgment rather than clearing the old finding.
  Budget one round per blob, and answer the CLASS in one edit instead of one finding at a time.

## Measure a candidate refusal rule against the store BEFORE building it

Before adding a rule that REFUSES submissions (a length cap, a banned-token lint), run the candidate
predicate over the stored corpus it would have judged and count how many ACCEPTED (CLEAN-verdict)
cases it would have refused. A rule that fails a large share of what the reviewer accepted is a churn
generator, not a control. Measured: a close-note length cap plus a banned-token list would have
refused 84 of the 113 CLEAN-verdict cycles, because this fleet's work is largely ABOUT the gate, so
tokens like "reviewer" and "the gate" appear in factual registers. Commit the measurement as a
re-runnable generator plus its transcript; it is the justification for NOT building the rule.

## Reading a per-blob close

The pass judges a bounded number of blobs per close inside a wall-clock window, so a wide range
closes over several passes and each pass REPORTS what it did not reach. Read "N blob(s) still carry
no review verdict" as PROGRESS and call `end_change` again — only a findings list is a refusal.
