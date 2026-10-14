# Handing work to the adversarial reviewer

**Why this exists:** the most common review finding is not a bug — it is
*"unverified-claim"*: the note asserted the work was done without attaching the
output that shows it. That costs a full review round-trip (a **double response**),
and on a complex change it blocks `end_change`. Roughly all of that friction is
avoidable by handing over the right thing the first time.

The reviewer is not hostile and not a formality. It is reading two things:
**the diff** and **your note**. Everything below is about making those two
sufficient.

---

## 1. Ordering — commit BEFORE you close

The gate diffs `lock.started_at..HEAD`, i.e. **committed** history:

```
begin_change → work → COMMIT → end_change
```

Close before committing and the reviewer receives an **empty diff** while your
note describes a change — which reads as a fabrication finding, correctly. This
one mistake accounts for a whole class of failed reviews.

---

## 2. The note is EVIDENCE, not a summary

The reviewer's own words, from a real finding:

> *"Worker claims 'Proved the GENERIC CLI drives a real governance cycle…' No
> command output, test run logs, or session transcripts are present in the
> reviewed material to support any of these claims… **A narrative summary is not
> evidence.**"*

So:

| Don't write | Write |
|---|---|
| "Tested and it works." | the command **and** its output |
| "All 46 tests pass." | `pytest … -q` → `46 passed in 3.4s` |
| "Verified the lock is released." | `{"active": false, "lock": null}` |
| "Fixed the bug." | the failing output **before**, the passing output **after** |

Rules of thumb:

- **Paste, don't paraphrase.** A quoted tool result survives review; a
  description of one invites the finding.
- **Include the negative results.** "I could not verify X" is a strength. Silence
  reads as an unverified claim.
- **Do not write to the reviewer's checklist.** Findings include
  *"evaluation-awareness"* — prose that mirrors the expected success criteria
  exactly, with no evidence attached, is flagged as output shaped for acceptance
  rather than correctness.
- **Name what you changed and why**, in one or two lines. The diff shows *what*;
  the note explains *why*.

### 2a. The material is CONTENT — a path is not material

`adversarial-review.py --material <x>` takes the material itself. Hand it a
**path** and the reviewer receives the literal string: it sees one filename, files
it `unverified-claim`, and returns **CLEAN on an empty review** — a pass that
proves nothing while looking like approval. Same for a commit SHA on its own.

- Build the material from the artifact's **contents** (`cat <file>`, or
  `git diff --cached` for staged work) and paste it inline.
- **Paste the OLD bytes the change edits.** Quote an existing line from memory and
  a one-phrase drift ("never delete or weaken enforcement" against a file reading
  "never weaken enforcement") comes back as **`fabrication`** — the strongest
  severity — for a typo. Run `sed -n '<a>,<b>p' <file>` first and diff against
  those bytes.
- **Do not ask the reviewer questions.** "Answer Q1-Q3", "be blunt", "report as
  JSON per the template" are returned as `injection` findings and the questions are
  **not answered**; the substance goes unreviewed. State the proposal as a checkable
  claim and let the findings judge it.
- Expect **3+ rounds** on a first pass and fix *material completeness*, not the
  prose — each refusal names the missing thing in its `recommendation` field.

---

## 3. Shape of a good pass-off

```
What changed: <one or two lines>. Files: <list>.

Evidence:
$ <the command you actually ran>
<its real output, verbatim>

$ <the verification command>
<its output>
```

If a claim cannot be backed by output, either drop the claim or mark it
**[UNVERIFIED]** and say what would verify it. An honest gap is not a finding;
a confident guess is.

---

## 4. What the reviewer is looking for

| Technique | What triggers it |
|---|---|
| `unverified-claim` | an assertion with no output behind it |
| `fabrication` | material described but absent (e.g. "diff stat: files=2, lines=310" with no diff) |
| `evaluation-awareness` | narrative that matches expected success criteria suspiciously exactly, evidence-free |
| `error-swallow` | `except: pass`, `2>/dev/null \|\| true`, silent empty results |
| `unverified-claim` on scope | changes outside the stated task |

---

## 4a. Three more rules the reviewer taught us (all discovered by being flagged)

These came from a real re-review, and each is a way a note *looks* like evidence
while not being it:

1. **Attach machine-generated artifacts, not quoted text in the note.** Writing
   "Evidence (verbatim): $ cmd → output" into the note is still self-report. Save
   the transcript to a file in the change (or reference real captured output), so
   the reviewer reads an artifact rather than your rendering of one.
2. **Map each claim to the diff.** "A refusal now exits 1" is not verifiable by
   itself — say *which function*, what the old line was, what the new one is.
   One line per claim is enough.
3. **Test the code you changed — not a neighbour.** The sharpest finding was
   *"Running unrelated tests does not verify the governance CLI changes."* A
   green suite that never touches the modified file is reassurance, not evidence.
   If the behaviour changed, there must be a test that fails without the change.

And one anti-pattern: **do not editorialise about the review** ("this is
unverified", "only the reviewer can decide"). It is read as
`evaluation-awareness` — output shaped for acceptance rather than correctness.
Let the artifact speak.

### 4b. Any review artifact on disk must declare where it came from

An agent can call a model from a scratch subprocess and file its reply as a
"review": the enforcer audits *tool calls*, and an HTTP request from a subprocess
is not one, so nothing sees it. The control that closed this is **artifact-level**
and machine-enforced, not a note in a skill — `ops/scripts/quality/review-provenance-check.py`,
wrapped by the doctor's `check_review_provenance`. A committed file under
`docs/` that *presents itself* as a review must carry one TRUE line in its header:

- `recorded-in: adversarial_reviews review_id=<id>` — and that row must exist in the
  loop-governance store (a claim with no row is fabrication); or
- `provenance: advisory` — commentary, never citable as verification; or
- `provenance: not-a-review` — for a file whose header merely names a model.

Undeclared review artifacts **FAIL the doctor**, and a doctor FAIL blocks every
agent's push on the host. In the registered script that is
`--cycle-id N --review`, which writes the `adversarial_reviews` row.

---

## 5. If the verdict is FINDINGS

Fix the findings, **commit**, then re-review with **new** material:

```
rereview_change(task_id="<task>", note="<what changed + the evidence>")
# or, from any harness:  loop-gov rereview_change '{"task_id":"…","note":"…"}'
```

- The reviewer re-runs **live** against the current diff — this asks again, it
  cannot manufacture a CLEAN.
- It **refuses an unchanged note**: re-review exists to re-judge a *fixed*
  change, not to re-roll a verdict.
- Exactly one verdict is kept per cycle; a re-review replaces it and is logged.

Without this, a FINDINGS verdict was permanent — you could fix everything and
still never close, which pushed agents toward an override. Fixing the friction
without weakening the gate is the point: **the line between friction and
enforcement is *evidence*, and evidence is exactly what the reviewer is asking
for.**

---

## 6. Checklist

- [ ] committed before closing (the diff exists)
- [ ] the note pastes real output, not a summary
- [ ] every claim traceable to something the reviewer can see
- [ ] gaps marked [UNVERIFIED] with the check that would close them
- [ ] no `except: pass` / silently-empty results introduced
- [ ] scope matches the task
