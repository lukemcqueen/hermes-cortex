# Satisfying the close-out review

How to close a governed change under the self-adversarial review with evidence,
without burning the session on a loose loop. The close refuses FINDINGS at medium+;
findings are usually about PROVENANCE (the reviewer can't see or re-run a claim), not
about the code being wrong.

## 1. Keep the range small — evidence starves the review window

The review's material is a per-file char budget shared across the changed files of the
range. Every committed evidence file in a COMPLEX / always-review range shrinks every
other file's share, so the MORE transcripts you append to prove a claim, the LESS the
reviewer can see of the code under review. Extreme symptom: the primary code file's diff
reports "N of N chars omitted" — the reviewer literally cannot judge what it exists to
judge.

- Land an evidence-heavy change as TWO cycles: code + tests first (a small range), then
a docs-only (`docs/evidence/**`) cycle for the transcripts. Splitting buys the big
window; a docs or evidence range also gets the larger material budget.
- Prefer ONE committed, reusable per-claim transcript over many ad-hoc captures.

### How the material is actually composed (know this before reasoning about it)

The reviewer's diff is **`git log -p` for your authored commits, plus any other author's
commits in the range** — not a flat `git diff`. Consequences that produce phantom findings:

- **A path appears once PER COMMIT that touches it.** Three commits touching one evidence
file means three sections, so any accounting that assumes one section per path is wrong;
an aggregate cap across "the file" may never fit while each section individually would.
Decide bounds PER SECTION.
- **Sections must break on commit boundaries as well as `diff --git`.** A splitter that
only breaks on `diff --git` lets a file's section run past its own patch and absorb the
NEXT commit's message, so a later section pairs one path with another commit's prose. The
reviewer then reports text appearing in the wrong file — correct about its material, wrong
about the repo. When material looks misassembled, check the splitter before rewriting the
content it complains about.
- **`docs/evidence/**` is shown whole and outside the budget, per section** (a section over
the cap is bounded like anything else). Artifacts prove the work; the budget belongs to the
code under review.
- **A checker or reproducer under `docs/evidence/` is an ARTIFACT, not production code.**
  Commit it there with its captured run beside it; do not write a `tests/` file to satisfy a
  test-first gate for something that runs itself. If a gate insists, that is a gate-class
  question (artifact vs production), not a reason to grow the change.

## 2. Commit evidence that is runnable, not asserted

A reviewer cannot verify a claim it cannot re-run; the fix is provenance, not argument.
An evidence artifact that survives a close review carries:

- the exact command it was produced by,
- the command's OWN exit status, captured bare — never a pipe's (`$?` after `cmd`
  alone, not after `cmd | tail`),
- the decisive line as the LAST line (review material always keeps a file's tail),
- a sha256 of the content.

`ops/scripts/make-evidence.sh` writes exactly this shape and `--verify` catches any edit.

### Self-referential hash pitfall

If a file records its own sha256, the recorded value is computed over the content BEFORE
the hash line is appended. `--verify` must therefore hash the file minus its final line,
not the whole file, or it always differs.

### The artifact has its own body cap — an unbounded section starves the ones after it

`make-evidence.sh` caps the captured body (`MAX_BODY`) and cuts the TAIL, recording the
omitted byte count at the cut. So ONE section that prints an unbounded report (a full
doctor run is ~300 lines) spends the entire budget and every LATER section disappears —
including the ones carrying the verdict. The file still looks finished, which is the
dangerous part: the omission note sits at the cut, i.e. exactly where a reader who was cut
off stops looking.

- **Order sections smallest-first and keep each one decisive**: the command, its own rc, the
decisive lines. A truncated artifact cannot be distinguished from a complete one by size.
- **Ask a tool for its own machine-readable summary instead of dumping its report.**
`cortex-doctor.py --json` prints `{"summary": {"pass": N, "warn": M, "fail": 0}}` — one
line that settles "warnings or failures?" — where the ~300-line human report settles
nothing and costs the whole budget.
- **Never summarize a report by counting a glyph.** `grep -c "❌"` counts non-failure lines
too (a fix hint, a footer), so it contradicts the tool's own exit code and reads as a
self-contradiction. Report the tool's OWN counts beside its documented exit convention
(e.g. `2` failures · `1` warnings · `0` clean, and a "healthy" flag that can be false with
zero failures); when your metric disagrees with the exit code, the metric is wrong.
- **Do not add proof-of-diligence.** Hashing files git already tracks, `wc -c` beside them,
or `ls`-ing a transient path outside the repo is filed as ceremony aimed at the grader and
costs a round. Evidence is the command, its own rc, and the decisive line — nothing that
exists to look thorough. (For which record to print instead, see rule 4.)

## 3. Prove claims at the level the reviewer asks

- **Tests**: commit a full run transcript that ENDS on the summary line (the tail is
  always kept in the material). For "this was RED before", commit a reproduction, not a
  memory. If you observed the RED run interactively under TDD but never committed it,
  reconstruct it: write the PRE-FIX module from git history (`git show <base>:path`) into
  a throwaway layout and run the CURRENT test file against it, asserting the expected
  failures. Mind module-path resolution — the test resolves its repo from `__file__`
  parents, so the module must sit at the path the test loads (`<repo>/mcp-servers/…`),
  and a test that references a constant added by the fix will surface as an
  AttributeError (still a RED, but name it as such rather than claiming a clean assert-
  fail it cannot produce).
- **Deploy**: a grep for a constant name proves the string exists, not that the running
  process uses it. Prove the RUNNING process loaded the deployed file by showing the
  process start time is AFTER the file mtime — or, if it is not, stop and restart the
  process, then capture that. Never claim a reload you did not perform.
- **Deployed line numbers**: the deployed copy of a file that the deploy banners has its
  lines shifted by the banner height (deployed == repo minus the leading banner lines);
  state that instead of implying a content difference.
- **A test that asserts a sibling file's SOURCE TEXT is not behaviour proof.**
  `assert "expected_call(" in other_file.read_text()` proves a string exists, and a reviewer
  files it as an unverified claim about behaviour. Run the real thing: invoke the CLI or
  script as a SUBPROCESS and assert on its stdout/stderr and its exit code. Keep at most a
  one-line source guard for the case a runtime test cannot observe (a call site that was
  DELETED fails silently rather than failing a test) and label it as exactly that.

## 4. Two mechanisms, one label — print the DISCRIMINATOR

When two different CAUSES produce the same visible value, an artifact that shows only the
value reads as self-contradictory and can be filed as **fabrication (severity critical)**:
the reviewer sees the same contents in two places and concludes the second cannot both prove
and disprove the first. The defect is in the ARTIFACT, not the work — the fix is to print the
field that separates the routes.

- **Find the discriminator and put it beside the shared value**: a path populated by one
  route and EMPTY by the other, an exit status, a timestamp, a provenance field. Then say the
  distinction in one line, so it cannot be misread as a paradox.
- **Prefer the RAW record to a summary of it.** `grep`-and-`head`ed output is not evidence of
  a claim: the reader cannot see what was filtered out, so the claim rests on inference and a
  finding says exactly that. Print the whole record (the JSON, the log section) and let the
  discriminator sit visibly beside the value.
- **When both routes are already in the artifact, cross-reference them** ("same label,
  opposite provenance; this field tells them apart") instead of assuming the reader infers it.

## 5. Measure the window before arguing about it

When a finding is about VISIBILITY ("this file is truncated", "cannot see the claim"), do
not answer with another artifact — that shrinks the window further. Measure first:

```bash
python3 ops/scripts/manage/review-material.py                    # per-file shown/of, your range
python3 ops/scripts/manage/review-material.py --gate deployed    # the copy that reviews
```

It prints the material's own accounting (budget in force, chars shown per file) and exits
non-zero when a file would be shown with almost no body. Rules that follow:

- A preview must build its input **the way the producer does**. A preview using `git diff`
while the review uses `git log -p` validates a different material and will contradict the
reviewer — trust neither until they agree.
- If the tool says the file IS shown whole while the reviewer says it is truncated, the
reviewer is reading a different material than you measured (a stale deployed gate, a
different base, or peers' commits in the range). Reproduce with `--gate deployed` and
report the numbers instead of restating the claim louder.
- One self-check beats a stack of transcripts: a single command whose output you quote as
the measurement ends the exchange; the sixth evidence file never does.

## 6. Don't chase evaluation-awareness phantoms

Late-round findings can be about the reviewer's OWN material limits or decisions about
your note's wording. If a claim is real, add the committed artifact and re-close; if the
finding misattributes the gate's own output (e.g. the MATERIAL LIMIT marker it appends)
back onto your note, say so once plainly and let the close assess the material. Keep
adding evidence actively makes it WORSE (rule 1) — recognize when the loop has stopped
finding real defects and stop feeding it.

## 7. A verifier is evidence — make it prove its own claims

The strongest answer to a provenance finding is ONE re-runnable command that re-checks the
whole change. It ends an argument that another transcript cannot, because a later reader
executes it instead of trusting a transcription. The trap is that the verifier is then
itself reviewed, and the same provenance standard applies to it:

- **A piped `tail` is not a result.** `cmd | tail -1` prints the last line whatever happened
  above it; a failure in the middle never reaches the artifact and the summary still reads
  green. Capture the output into a variable, print the decisive summary line, and print the
  command's OWN exit status next to it. Under `set -o pipefail` read `${PIPESTATUS[0]}` —
  never `$?` after a pipe, which is the last stage's status.
- **Print the script's own verdict.** Emit the failure count on the line before the exit so
  the capture states the outcome; "ALL CLAIMS VERIFIED" with no count beside it invites the
  finding that the count was never checked.
- **Make every check SKIP-able, and say so.** A verifier run on a fresh checkout (no
  deployed tree, no host tooling) must report SKIP with the reason rather than fail claims it
  cannot measure — and must never report a skipped check as a passing one.
- **Give "cannot check" its own exit code (3)** and keep it distinct from failure. A caller
  that reports an unverifiable run as a failed claim blames the payload for a host dependency
  it never measured; a caller that reports it as a pass is worse.
- **Name the artifact behind each check.** "The deployed copy" and "the repo copy" agree in
  every case except the one that matters (a wrong deploy-map entry still passes a repo-side
  run), so print which one was exercised, prefer the DEPLOYED path when the host has one, and
  let the fallback say it is a fallback.
- **`--help` is not a functional check.** It proves a file starts. If the claim is "the tool
  works on this host", run the real operation (write → read back → validate) against the copy
  that matters.
- **Read back what a helper wrote.** A config-writing helper is proven by re-reading the
  result and asserting the OTHER keys survived — the same call reports success when it
  silently wrote an empty value (two functions agreeing on a fragment's SHAPE is exactly
  where that happens: one returns it nested under its key, the other expects it bare).

## 8. Writing the finding response: the defect, not the reviewer

A response that argues the reviewer was right is filed as **evaluation-awareness** and can
block the close — a medium finding about the change's *framing*, not its content. The
reviewer is grading the change; diplomacy about its criticism is not a fix.

- State the functional defect and its mechanism, without the reviewer in the sentence:
  "a piped tail discards the failure lines and the exit status, so the artifact cannot tell a
  pass from a failure earlier in the run." Same fact, stated as the defect it is.
- The same applies to a commit message: describe what was broken and why the new shape is
  correct. "The reviewer caught that…" makes the change look aimed at the grader.
- When a finding is about the material's own limits (rule 6) or quotes a superseded claim,
  answer ONCE — a correction stated once reads as a correction; the same correction repeated
  in a second note reads as a new claim to review.

## 9. When the verdict is FINDINGS: re-review, do not re-close

A verdict is stored once per cycle, so a FINDINGS decision does not expire: the reviewer
keeps reading the SAME frozen note and refusing forever, however much the code improves.
Re-issuing `end_change` with rephrased prose is what that design actively prevents, and it
is how agents get pushed toward an override instead. The exit is a different call:

```
rereview_change(task_id="<task>", note="<what CHANGED + the evidence, pasted>")
```

- **Fix the finding first.** Re-review re-judges a FIXED change; it cannot manufacture a
  CLEAN, and the reviewer still runs live against the current diff.
- **The note must DIFFER and must carry command output pasted in, not summarised** — an
  unchanged note is refused outright. "What changed" means a fact the first note did not
  contain (the code that now exists, the before/after, the new task id), never a rephrasing
  of the same claim.
- **If the note that was reviewed quoted text, do not quote it back.** Replayed findings
  arrive with quoted fragments stripped precisely so a superseded claim cannot re-anchor the
  close; state the correction once in the newest note.
- **Never override a finding you have not fixed.** Overriding is for a scored DECISION you
  disagree with; it is not a way past the review gate, and it is especially wrong for a
  finding whose own evidence is sound.
- **A finding can refute itself.** Process findings sometimes arrive containing their own
  contradiction (a "fabrication" whose evidence concludes "no contradiction found"). Answer
  those once, plainly, with the artifact line that settles it, and spend no rework on them.

### Scope-drift findings: track the compelled work, don't argue about it

A review that measures your change against the task DESCRIPTION files anything it cannot
trace to that description as scope drift — including documentation the repository's own
audit forced you to write (an audit that refuses the commit until docs and index are updated,
so the work could not be landed under any other shape). Arguing that the audit compelled it
repeats the finding. The remedy the reviewer itself names is to make it a FIRST-CLASS
TRACKED TASK:

```
task_add(content="<the docs/debt work, the files, the commits that delivered it>",
         tags=["docs", "audit-compelled"], source="governance")
```

Then re-review, pasting the task id and the audit's own refusal line as the evidence. Two
consequences worth designing for up front: keep documentation that an audit demands inside
its own tracked task from the start, and expect the task description to be read narrowly —
when a change legitimately spills past it, split the delivery rather than defending it.

### A per-blob FINDINGS leaves NO cycle row — `rereview_change` cannot find it

Per-blob verdicts are stored in `blob_reviews`, keyed by the BLOB SHA, with no cycle id — and
`adversarial_reviews` is written ONLY by the whole-range path. So the exit prescribed above is
unreachable exactly when a per-blob pass produced the findings: `rereview_change` answers
`Cycle #<n> has no recorded review — nothing to re-review`, and the lock stays held.

Read the two stores before concluding a close is stuck (they disagree about what "recorded"
means, and the smaller one is the one `rereview_change` consults):

```python
import sqlite3, os   # the sqlite3 CLI is often absent; the module is always there
c = sqlite3.connect("file:%s?mode=ro" % os.path.expanduser(
    "~/.hermes-cortex/data/loop-governance.db"), uri=True)
```

For a per-blob verdict the working exits are narrower: change the blob's CONTENT (a fix produces a
new sha, judged on its own) or record the refutation and let the lock age out. Re-issuing
`end_change` cannot help — the verdict is keyed to content that has not moved, and each attempt
re-reads the same cached verdict.

### The capture must postdate the range's last commit

An artifact generated moments before the final commit of the range cannot have exercised
what that commit contains, and a reviewer comparing timestamps will say so (it did). Order:
finish every source edit, commit, confirm the tree is clean (`git status --short` empty),
THEN generate the capture, then commit the capture. Nothing is more annoying to defend than
a capture that was merely early.

## 10. Your own source can be too big to show

Rule 1 is about evidence crowding out code — the mirror case is a CHANGED FILE that does not
fit the window at all, so its middle is cut and the reviewer sees identifiers with no bodies.
That reads as "the implementation does not exist" and can be filed as fabrication. It is a
packaging defect, and it is on you to fix, not to argue:

- **Split a grown test or verifier file into topical files.** A suite that has accumulated to
  several times the per-file window is invisible in exactly the middle where its rules live;
  two files that each fit are fully reviewable, and the rationale can be trimmed rather than
  dropped.
- **Commit a raw transcript from the STANDARD tool** (e.g. `pytest -v`, whose own output is
  small) as the canonical small artifact. Evidence that comes only through your own wrapper
  is a claim about a claim.
- **Print the implementation and the before/after FROM THE FILE, into the artifact** when a
  diff window cuts a body: `grep -n -A8 "^def <name>" <file>` for the code, and
  `git show <commit>~1:<path> | grep -A4 <key>` beside `grep -A4 <key> <path>` for a change.
  The capture then carries the code, the change, and the commit that introduced them — which
  is the whole answer to "the diff does not show what you claim".

## 11. Publishing under a receipt: MERGE, never rebase

A CLEAN close writes a SHA-bound receipt for the reviewed range, and the push gate accepts a
LONE `git push` that the receipt covers. A peer pushing while you are closing therefore turns
the choice of integration into a publishing decision:

- **A rebase rewrites your commits, so the reviewed SHA stops existing** and the receipt
  matches nothing — you would be asking to publish content the review never saw.
- **A merge (`git pull --no-rebase`) keeps the reviewed SHA an ANCESTOR of the tip**, so the
  receipt still covers the range and a one-commit merge cycle authorises the push. Use the
  merge commit as the cycle's change; a merge commit is far cheaper than a fresh review.
- **Expect the peer to have edited the same shared docs** (an index, a changelog, a README).
  Keep BOTH additions rather than picking a side, then verify the merged tree before closing
  (`pytest` on the touched suites, the generator's `--check`), and say in the close note that
  a peer's commits are why the range grew.
- **Establish whose commits they are before concluding anything**: a peer's work looks exactly
  like your own in a diff. `git log --format="%h | %an | %ae | %s"` names the author, and
  `git merge-base --is-ancestor <sha> origin/main` says whether your range is already in the
  tip (exit 0) or genuinely diverged. Cycle ids far below your host's current range usually
  mean another host's database.

## 12. A wide range closes over SEVERAL attempts — drive it with a loop

When the range touches an always-review path, or the whole-range review cannot finish, the
close RE-ROUTES to a per-blob pass: one reviewer call per changed blob, verdicts cached by
blob CONTENT, and a receipt that may name only blobs carrying a CLEAN verdict. Unjudged blobs
are omitted and the push gate names them.

- **A partial pass is PROGRESS, not a blocker.** The refusal reports what it reached and what
  is left (`reviewed this pass: N blob(s)`); closing again continues from the cache and never
  re-buys a verdict it already has. Several rounds are normal when the reviewer is slow — do
  not read the first partial pass as a dead end, and do not re-slice your own history to make
  the range smaller.
- **Drive the rounds with a loop whose stop condition is a receipt for the CURRENT tip**
  (`ls ~/.hermes-cortex/state/.reviewed-*.json` naming that tip), in the background: a round
  is minutes long and its output is only readable afterwards.
- **SCORE THE CYCLE BEFORE STARTING THE LOOP.** Issuing `feedback_accept` in the same turn as
  the loop launch races: the attempts execute first, each instantly refusing with "this
  task's cycle is NOT scored", and the loop spends every round on that. Score, then launch.
  The record will not tell you afterwards — a cycle row's `timestamp` is its CREATION time
  (the scoring UPDATE does not touch it), so the ordering is unrecoverable from the DB.
- **A slow reviewer is not an outage.** One blob call runs 180-220s against a 240s wall-clock
  ceiling; a blob whose call times out is SKIPPED and reported, and only TWO CONSECUTIVE
  failures end the pass. Expect `reviewer timed out on: N blob(s)` beside `reviewed this
  pass: M blob(s)`, and close again rather than concluding the range cannot close.

### When a blob's verdict will not come: the two budget levers

- **`finish_reason=length` with `reasoning_tokens` ≈ `max_tokens`** means the OUTPUT budget
  paid for thinking and left nothing for the answer. Raise `REVIEWER_MAX_TOKENS` for that
  unit: the "raising the cap does not help" measurement was about a WIDE whole-range call,
  where reasoning runs away regardless, not about one blob.
- **Do NOT reach for the reasoning-effort knob to fix latency** — it does not move wall-clock
  time at all (measured on identical material: medium 187.9s vs low 187.1s). It changes how
  much the reviewer says, not how fast it says it, so lowering it trades review depth for
  nothing.

### The capture must postdate the DEPLOY, not just the last commit

A capture taken before the range's own code is deployed reports the deployment ORDER as a
failure: the doctor's checksum check compares the DEPLOYED copy against HEAD, so it prints
`❌ Checksum: <path>` and a non-zero failure count, and a close note quoting an earlier run's
clean numbers then contradicts the artifact beside it. Regenerate after the deploy. A commit
that afterwards touches only `docs/evidence/**` needs no second deploy (the deploy-sync check
is scoped to the deploy-map files the range changes), so this costs no extra deploy window.

### A heading is a claim — it must not assert what the body refutes

Making a section's body honest and leaving its TITLE asserting the old conclusion is filed as
**fabrication**: the transcript claims an outcome two lines above the output that disproves
it, and the heading is the reader's first impression. When a section is rewritten to report a
measured branch (say, "is the running process carrying this change?"), retitle it to name the
COMPARISON ("the comparison, measured") rather than an outcome, and let the branch print the
verdict.

## 13. A generated artifact that reports FAILURES must ATTRIBUTE them

A committed report that lists failing items is filed as **unverified-claim**: "3 failed" is a fact
about the run and says nothing about whether THIS range caused it, so the reviewer has to refuse it.
Explaining the failures in the close note does not fix it — the reviewer reads the DIFF. Fix the
GENERATOR so the artifact answers the question itself:

- **Re-run every failing item at the base revision and print the pair.** For each failure print
  `base rc=<n>` beside `this tree rc=<m>` and a verdict — `REPRODUCED at the base revision` /
  `*** DIFFERS — this range is implicated ***` / `COULD NOT VERIFY` — so a reproduced failure is
  visibly not yours and a differing one is visibly a regression.
- **Use the same classification on both sides.** A file run under pytest on one side and executed
  directly on the other compares two different runners and reports the difference as a code change.
  Reuse the generator's own "what the file IS" dispatch at the base.
- **A base that cannot be prepared yields `COULD NOT VERIFY`, never agreement.** A worktree that
  fails to create, or a file absent at the base, must not silently produce a matching exit code.
- **Keep the verdict a pure function and pin it both ways in the guard**: agreement must never
  render as a regression, and a difference must never render as agreement.

## 14. Pin the comparison base to the RANGE BASE, never `HEAD~1`

A relative base is right until you commit: once the change lands, `HEAD~1` is your OWN previous
commit, so the "before" side already contains half the fix and the comparison silently stops testing
what it claims — and regenerating the artifact then compares a revision with ITSELF. Resolve the base
the way the review does, and print the resolved sha so a reader can re-run the comparison:

```bash
base=$(git merge-base origin/main HEAD)     # the range base; does not move as you commit
```

Fall back to a relative revision only when git cannot answer, and say in the artifact which one you
used.

## 15. Your own task description is the requirements list

A finding can quote the `begin_change` description back as the deliverable you failed to ship ("the
task required an idempotent, age-gated bootstrap that CREATES it"). The reviewer grades the change
against the description you wrote, so **write the description as what you will actually ship**:
naming a mechanism, an exit-code contract, or a create/install step you do not implement is
self-inflicted scope drift that no amount of evidence answers. When a description has already
over-promised, deliver the missing piece rather than arguing the point — the corrected shape is
usually the better design anyway.

