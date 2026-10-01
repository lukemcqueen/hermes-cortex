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
