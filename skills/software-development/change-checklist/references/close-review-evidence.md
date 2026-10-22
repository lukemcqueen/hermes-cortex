# Packaging evidence for the close reviewer

Depth for the close-time evidence rules in SKILL.md Phase 5. The close reviewer is an automated
reader with a **bounded view of the range diff** — write evidence for that window, not for an
archive.

## The window constraint

The reviewer renders a truncated window of the whole `base..HEAD` diff, with the budget shared across
ALL changed files. Consequences that decide how you package:

- **A large evidence file is mostly invisible.** A complete 8KB transcript can be 88% omitted; its
  claims then read as unverified, which is indistinguishable from fabrication to the reader.
- **More changed files means less of each.** A range with 15 files shows less per file than a range
  with 3 — so keep the diff tight and the evidence files small.
- **Truncation is not a defect in the artifact, but it IS a defect in the evidence package.** You
  cannot widen the window; you can only make the load-bearing lines survive it. Do not spend turns
  arguing the point — that itself draws an evaluation-awareness finding.

## Shape

- One topic per file, a few hundred bytes to ~2KB: before-state, after-state, per-file decisions,
  test run, deploy+doctor transcript. Named by topic, not by date.
- Put the command and its output near the **head** of each file so truncation of the middle cannot
  hide the invocation.
- Every transcript carries `rc=$?` beside the command and the **warning count**. A bare `✅ PASSED`
  with N warnings and an unresolved sub-check reads as a clean system to the reviewer; report the
  numbers that are NOT clean too.
- **Count statuses from the tool's OWN summary line, never from a grep for its symbols.** A grep for
  `⚠️`/`❌` also matches the legend the tool prints UNDER its findings ("resolve each ⚠️ or ❌
  above"), so a 0-fail run reports one fail and the artifact contradicts the summary line printed
  two lines above it. Quote the summary verbatim (`Overall: WARNING (469 pass · 4 warn · 0 fail · 3
  info)`) and, when you also enumerate the non-pass lines, scope the pattern to status lines
  (leading whitespace + the symbol) so a legend can never be counted as a finding.
- State the honest limit inline ("doctor rc=1, WARNING, 448 pass / 3 warn / 0 fail") instead of
  claiming cleanliness the output contradicts.

## Capture discipline: label it, paste it whole, regenerate it

An evidence artifact is judged on whether its LABELS match its CONTENT. These four mistakes all read
as fabrication to a reviewer, and all four are avoidable before the first close attempt:

- **Name each capture for its ROLE and never reuse one filename across runs.** A capture written to
  `pytest_targeted.txt` on the failing run and re-written there by a later passing run leaves the
  block labelled RED holding `29 passed` — a fabricated BEFORE state, because the file was overwritten
  rather than the label being wrong. Write `pytest_RED_genuine.txt` and `pytest_GREEN_final.txt`, and
  regenerate the artifact FROM those files in one pass so no block can drift from its capture.
- **Paste the WHOLE capture for anything load-bearing.** Truncating to `tail -14` cut exactly the two
  rows a section claimed to show, so the prose described evidence the material did not contain. If you
  must truncate, say what was dropped and why it is not load-bearing.
- **Never print a placeholder in a command that has output beneath it.** `--file <changed file>`
  followed by a result reads as output from no real invocation; name every real path, one command per
  file, and let the captured block follow it.
- **Label partial blocks and never make a blanket completeness claim.** "Every block below is complete"
  beside two blocks marked `(selected lines from a 567-line run)` is a contradiction inside one file.
  Write the honest rule at the top ("two blocks are marked SELECTED LINES; every other block is
  complete") — a narrower true claim survives review, an overstated one does not.
- **A recorded command line must be exactly re-runnable.** `bash -c "cmd-a && cmd-b"` renders in the
  transcript as `bash -c bash cmd-a …`, which no reader can execute — a reviewer is right to read a
  green rc under it as a fabricated run. Give each command its OWN captured step (`run "$OUT/06-x.txt"
  … bash "$DEPLOY/scripts/x.sh" --check`) and echo the argv verbatim, so copy-pasting the line
  reproduces the block.
- **The generator must RUN on the host, which rules out naming a large file it merely reads.** When
  a shell executes a script, the host's guard scans the script's referenced paths first and REFUSES
  the run if one is too large to scan — so a capture that opened the governance store by path could
  not execute at all, while every line of it was correct. Resolve stores and big artifacts through the
  COMPONENT'S OWN ACCESSOR instead: import its module and reuse the constant/helper that builds the
  path (an import is inert when its work sits behind `if __name__ == "__main__"` — check the file's
  tail before importing), and open read-only where the store supports it (`sqlite3.connect('file:%s?mode=ro'
  % path, uri=True)`). Two wins: the artifact never hardcodes a host path, and the accessor is the
  route the component itself sanctions. Prove a capture by RUNNING it, not by reading it — an
  unrunnable generator produces no artifact and no error the reviewer can see.
- **Probe the store's schema before a query goes into an artifact.** Column names are not guessable
  (`blob_sha`/`ts`/`decision` rather than the `blob_path`/`created_at` a writer would assume), and a
  wrong guess in a committed transcript publishes a traceback where proof was claimed. Query once
  interactively, confirm it returns rows, then put it in the generator.
- **A regenerated artifact varies; say what is stable.** Re-running a capture that contains
  model-generated prose (an agent turn, a summariser) produces different wording every time, and a
  reviewer reading only the diff files the change as unexplained scope drift. Emit a provenance header
  INTO the artifact — `# the PROVIDER named and the URLs returned are the stable facts; the surrounding
  prose is model-generated and differs between runs` — and repeat the same sentence in the commit
  message. Determinism is what makes a transcript evidence; variance is fine as long as it is declared.

## The generator's own silence must fail loudly

An evidence generator that extracts its work list, times a run out, or parses a summary has three
ways to end up holding no data — and each, rendered as ordinary output, reads as a CLEAN run:

- **An empty extracted list.** A list pulled from a committed artifact by a section range yields
  nothing when that artifact's shape changes, and the script then prints `files to run: 0` and exits
  0 — indistinguishable from "nothing is failing". Refuse it: name the source, name the section you
  expected, exit non-zero.
- **A killed run.** `timeout` returns its OWN exit code (124), and a timed-out run's output is
  truncated or empty, so grepping it reports whatever fragment survived as the "reason". Branch on
  the timeout code BEFORE parsing anything and name the timeout as the cause.
- **A count-less run.** A runner that crashes before printing counts leaves the summary field blank,
  so the line reads `rc=1   ` with nothing after it. State the gap explicitly.

Prove each guard by driving the REAL script's branches — a byte copy with one literal changed per
case — and assert each fires. The probe needs its own non-vacuity check beside every behavioural
assertion, or a case that never reached its branch reports a pass; the mechanic is under the
false-green pitfall in `adversarial-verifier`.

## The note is read against the DIFF

A claim in the cycle note is checked against what the diff ADDS, so an enumeration can read as
unbacked when it is merely unchanged:

- **Every item the note enumerates must appear as an ADDED line.** Naming three per-file gate runs
  when the third command line was already present as context reads as "no added invocation for X
  appears in the material" — the claim is true and still unfalsifiable in the window. Add a summary
  line that names all of them (which is itself an added line) above the captured block.
- **Put the command directly above each block.** The material is a diff: the trailing context a hunk
  header carries is prose from the file, and a reviewer can quote `@@ -90,23 +89,11 @@ <that prose>`
  back as "a line in the file". Short sections with a command adjacent to their output give that
  reading nothing to attach to.

## Reproducible BEFORE states

A BEFORE state labelled "captured before the change, not re-runnable" cannot be verified and is a
legitimate finding. Reproduce it:

```bash
git worktree add /tmp/pre <commit-before-the-change>
python3 /tmp/pre/<path-to-the-detector>.py   # a tool that resolves its root from its own path
                                             # measures THAT tree, not your working copy
git worktree remove --force /tmp/pre
```

Commit the output with its rc. Authenticity then rests on the commit being measured rather than on a
claim in the prose — and any later reader can re-run it. Copy the NEW test files into that worktree
when the before/after is "these tests against the old sources", and name both revisions in the
artifact so the comparison stays re-runnable after your own commit lands.

**Attribute a failing item by NODE ID, not by the printed line.** A runner reports paths relative to
its own rootdir, so the same failure reads differently from a worktree and from the repo
(`base-wt/tests/x.py::test_y` vs `../hermes-cortex/tests/x.py::test_y`). Diffing the whole `FAILED`
line therefore answers DIFFERS for two identical failures and throws away the pre-existence verdict
you just earned. Normalise both sides to the test's own ID (the `::test_name` suffix) before
diffing, print the shared IDs in the artifact, and pair that with an outcome classification
(PASS / FAIL-naming-a-test / NOT RUN) — two runs that measured nothing share an exit status and a
code-only comparison reads them as agreement.

## Identity, not labels

- Bind a claim to the artifact that produces it: the commit SHA, the file path, the range
  (`origin/main...HEAD`), the exit code. "Verified" is not evidence; the command beside its output is.
- Say explicitly when a range includes work that is NOT yours — a peer's commit, a prior session's
  landing — and name it, so a reviewer does not file it as your scope drift.
- Evidence must be self-consistent: a summary may never cite a file, path or count that the artifact
  beside it does not show.
- **A crash class you fixed inside your own fix is not a pre-fix defect.** State its provenance
  ("found by the boundary probe on its first run, before the guard existed") rather than presenting
  it as behaviour the old revision had; if the old revision cannot even exercise the code path (the
  parameter did not exist yet), say so and pin the guard with a committed test instead.

## When a close is refused

0. **An INCOMPLETE close is not a refusal — do not change the work.** `end_change` can return
   `Cannot close yet: N blob(s) of the push range still carry no review verdict`: a per-close budget
   (a blob cap and a wall-clock limit) ran out, not a judgement. Verdicts are cached by blob CONTENT,
   so calling `end_change` AGAIN continues from where it stopped rather than re-judging the blobs it
   already cleared — repeat until it returns a receipt. Re-working the range, or reporting a blocker,
   in response to that message wastes the passes it already paid for.
1. Read each finding as a work item; implement the remedy, do not restate the claim more forcefully.
2. **The verdict is FROZEN per cycle — `end_change` alone cannot clear a FINDINGS refusal.** It
   re-reads the same frozen note and refuses identically, however much you changed since. The remedy
   is `rereview_change`, which re-judges an OPEN cycle and REFUSES an unchanged note — supply the NEW
   evidence with the output pasted in. Never use it to re-roll a verdict. It resolves the cycle by
   TASK, so the lock must belong to that task: re-acquire with `begin_change` under the original task
   id when you fixed findings in a later cycle. The order that works: fix the blob →
   `rereview_change` with a note naming what changed and the command output that shows it →
   `end_change` once it returns CLEAN. Per-blob verdicts are keyed by CONTENT, so the fix itself is
   what creates the new blob to be judged; a file whose bytes are unchanged keeps its refusal.
3. **Do not keep committing while that refusal stands.** The lock is still held, so each commit
   STACKS under the refused cycle and the reviewer later reads a description that no longer matches
   the diff. Land the fix and re-judge first — and note that a commit already made under the refused
   cycle is not wasted: it IS the new blob the re-judge reads.
4. **A task with nothing left holds nothing — release it yourself.** When the work is finished or
   abandoned and the cycle is already scored,
   `advance_task_state(task_id=<task>, new_state='cancelled', reason='<why>')` releases the lock with
   no PENDING-cycle leak. That is the correct exit for a terminal task; it is not an override and
   needs no operator approval.
5. A finding whose remedy is impossible or contradicts an explicit operator instruction gets stated
   once, with the evidence, and then recorded (`record_issue`) — not re-litigated each round.
6. Never `force`, never an override: that is the operator's call, and asking is cheap.

## Deliverables belong in the repo

A host-local script, a cron job, a state-dir artifact or a chat transcript is not a deliverable: the
next agent and the reviewer cannot read or re-run it. Reusable logic goes in a registered script with
a hermetic case in a `tests/` runner that actually executes it; only host-specific values stay in a
thin `local-`-prefixed wrapper; measured transcripts go under `docs/evidence/`.

## What the reviewer refuses as an "unverified claim"

Every one of these is the same finding with a different costume, and the remedy is always to change
the ARTIFACT, never to restate the claim harder:

- **A proof that lives outside the repo — or in a SIBLING blob.** A probe harness in a scratch dir,
  a session transcript, an operator's chat: the reviewer cannot re-run any of it, so the claim reads
  as unverified. But moving the proof INTO the repo is not sufficient on its own, and this is the
  trap: verdicts are stored per blob CONTENT and the reviewer judges ONE FILE AT A TIME, so a claim
  made in `scripts/x.sh` and demonstrated only by a test in `tests/test_x.py` is invisible FROM
  `scripts/x.sh` and returns as unverified-claim on every round — however good that test is. **Put
  the proof in the blob that MAKES the claim**: a runnable `--self-test` mode on the component
  itself, printing PASS/FAIL per assertion and exiting non-zero, is the shape that travels with the
  code. Keep the `tests/` case as well and have it assert the self-test passes, so the two proofs
  cannot drift apart. A finding of this shape is usually a request for the proof you placed one file
  away.
- **A count asserted under an ellipsis.** "… the doctor: 449 pass / 11 warn / 0 fail" with the run
  elided is a number the reader cannot check. Quote the LOAD-BEARING LINE VERBATIM, name the command
  that prints it, and explain a count that differs from another file's ("an earlier run of the same
  command, before the deploy moved one check") instead of leaving the contradiction for the reader.
- **A mechanism you did not observe.** "No restart happened", "the deploy reloaded it", "the cache was
  warm": state the OBSERVATION ("with no lock held, the push completed and the hook named the
  receipt"), put the inference under its own clearly-labelled heading, and state what it does not
  prove. The inference from a completed action is usually strong enough on its own — the unobserved
  mechanism adds only attack surface.
- **A finding whose premise is factually wrong.** Verify the premise before complying: "an existing
  utility gained a drive-by guard" is false when the function is added by THIS diff. Rebut it in the
  rereview note with the evidence (the differential probe's own "added in repo: [...]" line, a
  `git log -S` showing the definition never existed before), and implement the rest normally. The same
  check applies when a reviewer quotes a line it says the FILE contains — grep the committed file
  first; if the quoted line is the diff's own hunk header or metadata, the file is unchanged in that
  respect and there is nothing to remove, so say so with the grep and fix what the finding usefully
  points at.
- **Refute it with a check that DISCRIMINATES, not with prose.** A reviewer that misreads an assertion
  ("this substitution always yields empty, so the check passes trivially") is answered by pinning the
  pattern both ways in the committed test — drive it against a fixture that must match and one that
  must not, and show the two opposite outcomes. That converts your rebuttal from an argument into
  evidence, and it is the same discipline the finding itself is asking for. Keep the argument to one
  sentence naming the mechanism (`$(grep -q … && echo 1 || echo 0)` prints 1 or 0 — the substitution
  captures the echo).
- **A RED-then-GREEN claim needs the RED state to survive.** A test committed in the same commit as its
  fix makes the failing run unverifiable — nothing in the range shows the check ever failed. Commit the
  failing test first where you can; where the two must land together, pin the discrimination inside the
  artifact instead (a stub launcher/fixture that drives each branch, an assertion self-test), so the
  grader can see the check would notice a regression without needing your terminal.

## Sanitising a transcript before it enters the repo

The shared-surface PII guard rejects material that is not PII — a full 40-char SHA and a remote URL
both trip it. Write evidence with the SHORT sha (`081c7fd6`), `<origin>` (or the same placeholder the
runbook uses) for remotes, and no long digit runs. Sanitise the command line you paste too: a
transcript that quotes `$HOME` is more portable than one quoting a real home path.

## When the close call itself times out

An MCP close/re-review can exceed the client's call timeout while the SERVER finishes the work. Do
not conclude failure and do not re-run the review: check the cycle's stored note and the receipt file
(`~/.hermes-cortex/state/.reviewed-<slug>-<tip>.json`). If the note and receipt are there, call
`end_change` again — it reports the frozen verdict if the re-review did not land, and closes
cleanly if it did. Re-running the re-review instead re-rolls a verdict the guard exists to protect.

**A close that ERRORS (no verdict at all) and reproduces on one retry is not transient — stop.**
An identical exception on the second attempt is a defect in the gate, and each further attempt costs
a reviewer run and teaches nothing. After the second identical failure: `record_issue` with the
exact message, the cycle id and range, and what you RULED OUT (each hypothesis with the observation
that killed it — a running process that started after the deploy already has the new code, a guard
you verified exists, a parse you verified is guarded), then report it with the reproduction and say
plainly that the lock stays held. Do not present the diagnosis as proven when it is a hypothesis,
and do not start a second change while the lock is stuck — a new cycle's close will hit the same
wall and leave another stuck cycle behind.
