# Adversarial gate — the review material contract

What the close-gate hands the reviewer, how the reviewed range is chosen, and how to
tell a real finding from an artefact of the material. Read this when a complex cycle
will not close and the findings look like they are about the wrong change.

## What the material contains

```
Cycle ID / Task / Description
Diff stat (files=N, lines=N, untracked=N, always-review=<paths>)
[numstat — TRACKED changes only]
Worker's note (explicitly labelled self-report)
Full diff
```

The verdict is pinned by a fingerprint of this material (note + diff), so any change
to the note or the diff invalidates a stored verdict and forces a fresh judgement.

## How the reviewed range is chosen

Oldest commit before the lock's `started_at` → `HEAD`. That window is NOT "this
session's change": a rebase pulls in other agents' commits and automated pipeline
commits. The range is therefore filtered by the repo's git author identity.

Three properties, and a change to any of them must preserve all three:

1. **Authored = audited.** Committed work is counted and diffed with
   `git log --numstat/--author=<identity>` and `git log -p --author=<identity>`.
2. **Fail OPEN when identity is unknown.** No resolvable identity, or nothing authored
   in the window → audit the WHOLE window exactly as before. Narrowing on a guess is
   how a worker escapes review by committing under another name. Fail-open must still
   LABEL authorship: emit every window commit as `<sha> <author> <email> <subject>`,
   taken from git rather than from the worker's note, and never state or imply that
   the range was narrowed when it was not. An UNLABELLED window is read as the
   worker's own change, so a peer's enforcement edits (enforcer, `loop-gov-mcp.py`,
   hooks, `cortex-update.sh`) pulled in by a rebase get charged to this worker — which
   then has its real evidence rejected as fabrication and cannot fix it from its own
   side. Share one formatter between the narrowed and unnarrowed paths so the two
   disclosures cannot drift apart.
3. **Fail SAFE against escape.** A window commit the session did NOT author but which
   touches an always-review path (enforcer, `loop-gov-mcp.py`, hooks, `cortex-update.sh`)
   still FORCES review. Non-authored commits also stay in the material, in full, as
   provenance — hidden context is where an escape attempt would live.

### Identity caveat

Author-scoping separates *agents*, not *sessions*. Two sessions of the same agent on one
host share one git identity, so a concurrent session's commits look authored. When the
repo is shared with another session, git cannot tell you whose work is whose — check for
uncommitted peer changes before pulling, pushing or deploying, and expect a peer's
`git add`/commit to be able to sweep your staged edits into its commit.

## What the reviewer accepts as evidence

- Raw output: the invocation, the stdout, the exit code. A curated PASS list is scored
  as self-report.
- A runnable test committed to the repo beats transcribed output, because the reviewer
  cannot re-run a terminal.
- A passing test is not enough on its own: include a CONTROL that asserts the pre-fix
  behaviour is present, or the test may pass against broken code. A guard is proved the
  same way: run it against a case it must FAIL before staging the fix, or its green run
  may mean it never inspected the right thing.
- The reviewer has no terminal. A true claim whose proof lived only on a screen is an
  evidence gap, not a fabrication — fabrication requires the material to CONTRADICT the
  claim (a file, line or result that does not exist, or output saying the opposite).
  The resolution is always committed proof: a later reviewer can re-execute a test and
  can never re-execute a transcript.

## Diagnostics — symptom → what it means

| Symptom | Meaning | Action |
|---|---|---|
| Finding quotes text you never wrote, or text a later commit removed | Daemon running pre-scoping code, or the change really is in the window | Check which code is live before editing; `grep` the phrase to prove it is absent at HEAD |
| Stat header count ≠ listing entries | Untracked files counted but not listed in numstat | Label both; do not let a labelling gap look like a fabricated number |
| "Injection" finding | Instructions to the reviewer were embedded in the material | Emit neutral metadata only |
| Injection/escape concern raised at all | Scoping may have narrowed coverage | Re-assert the fail-safe: foreign always-review paths still force review |
| Same finding returns after a correct fix | Material unchanged (fingerprint match) or the verdict was never stored | Change the material; check `rereview_change` first |
| "Fabrication" finding aimed at a result you really did produce | The reviewer cannot see a terminal; missing pasted output is an evidence gap, not deception | Commit a test that reproduces it, re-review with a new note |
| Findings say the implementation/tests are "not present in the material" | The diff bound truncated the material mid-line, so the reviewer judged a real change as unevidenced | Check the bound: keep head+tail and disclose the omission, then re-review |
| Finding charges you with changes to enforcement paths you never touched | The window holds commits a pull/rebase brought in and the material did not label authorship | `git log --format='%h %an <%ae>'` to confirm, name your own shas, re-review once authorship is disclosed |

## The material is BOUNDED — a truncation is the GATE's limit, not missing evidence

The full diff is cut to fit the reviewer's context. That bound is a property of the
GATE, and it shapes findings: a reviewer reported a large implementation and its tests
as ABSENT from the material because the diff had been cut mid-line, and the worker's
closing note then read as a claim about evidence that was not there. Before answering
"the implementation/tests are not in the material" with more justification, check
whether the material was truncated — and fix the bound if it was.

- **Keep a HEAD and a TAIL.** A head-only cut drops the end of the change, and a diff's
  later hunks are often the fix under review. Reserve part of the budget for the tail.
- **Never cut silently.** The omission notice carries true numbers (N of M chars
  omitted), says plainly that this is the GATE's budget rather than absent evidence, and
  names the files partly hidden in the cut, pointing at the committed content the
  reviewer can read with a file tool. A silent marker turns a tool limit into a wrong
  finding about the worker.
- **Where the bound lives, its comment is not the guard.** The comment claimed head+tail
  while the code kept the head only, so the disclosure described behaviour the code did
  not have. Extract the bound into a function and test it directly: the tail survives,
  the numbers in the notice equal what was actually dropped, files in the cut are named,
  and a source-level check asserts the gate calls it and that no bare head-only slice
  returns.
- **When the finding is abstract ("the diff is truncated", "contents absent"), re-review
  rather than rewriting the change.** The fault is in the material, so fix the material
  and submit a new note saying what it now carries.
- **A truncated diff cannot confirm WHICH revision was tested — pin the artifacts by hash.**
  When the evidence is a generated artifact plus the source file it was produced from, the
  reviewer may see the artifact while the source sits in the cut, so "the file this ran
  against is the file that is committed" is unverifiable from the material — and a count
  or a version in the artifact cannot be checked. Record a `sha256sum` of each tested
  artifact INSIDE the generated evidence, so a reviewer with a partial diff verifies by
  hash instead of by reading. Cheap, and it retires a whole class of "cannot verify this
  from the visible evidence" findings as a one-line check.

## Testing the gate itself

Driving `_adversarial_review_gate` with a stubbed reviewer is the only way to prove a
refusal path without waiting for a real verdict. Four things that cost a run each:

- **The reply is parsed as a JSON OBJECT** by `_extract_verdict`. Stub
  `{"verdict": "FINDINGS"|"CLEAN", "findings": […]}`. A bare findings ARRAY parses
  as *no verdict*, which is FINDINGS with an empty list — so "it did not block" fails
  for the wrong reason.
- **Layer 1 refutation DROPS a finding whose quoted `evidence` does not appear in the
  material.** A fixture that blocks on nothing is usually the refutation layer working,
  not the gate failing: quote real material text (the note, a diff line) in the fixture.
- **Layer 2 triage calls the LIVE judge when one is configured in the env**, so a
  synthetic finding can be legitimately lowered mid-test. Neutralise `_refute_findings`
  and `_triage_findings` only when the test isolates WIRING; those layers have their
  own suites, and a fixture that neutralises them proves nothing about classification.
- **The reviewer prompt template is read from the repo path**, so a temp repo without
  it refuses with TEMPLATE_MISSING before any reviewer call — itself a refusal path
  worth asserting, but not the one under test.

Point the fixture repo at a temp HOME (`repo_slug` resolves relative to it), keep the
complex change UNCOMMITTED on an always-review path so complexity measurement counts
it, and assert the refusal MESSAGE so a failure names which path refused.
