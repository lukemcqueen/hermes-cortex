# What bounds a close-time review

The close review is bounded in several independent places, and a range that exceeds any one of
them produces a refusal that looks like a broken gate. Know which bound you hit from the
message before changing anything.

| Bound | What it does | The knob |
|---|---|---|
| Material shown | how much of the diff the reviewer receives | not a knob — SPLIT the range |
| Output budget | one call's `max_tokens`, thinking + answer together | `REVIEWER_MAX_TOKENS` |
| Thinking effort | how much of that budget goes to reasoning | `REVIEWER_REASONING_EFFORT` |
| Wall clock | how long one call may take | the deadline constant |
| Units per pass | how many blobs one close judges | the per-pass blob cap |

`REVIEWER_MAX_TOKENS` and `REVIEWER_REASONING_EFFORT` are read at CALL time, not at import, so a
change takes effect on the next attempt with no restart. Values above the ceiling are clamped and
warned.

## The failure this actually produces

`NO usable content (finish_reason=length, max_tokens=N)` — a reasoning model exhausted the output
budget thinking and returned no content. Raising the cap is the intuitive fix and it does NOT
work: one blob measured the point exactly — empty at cap 16000 (16550 reasoning tokens), empty at
cap 32000 (35977), empty at 128000 (130836-143469), because the model thinks to whatever cap it is
handed. **The cap is never the lever.** The effort is: the same blob returned a verdict in seconds
at the lowest effort with a modest cap. Move the EFFORT to the bottom of its vocabulary before
touching the cap at all, and check the units per call second — not the cap.

Report the MEASUREMENT (`reasoning_tokens=N against max_tokens=M`), never the remedy that was
tried — a message naming the knob you already turned sends the next reader to turn it again.

### Where the value is actually resolved

A file edit that appears to do nothing is usually being beaten by something earlier in the chain,
not ignored. Resolution order is **the PROCESS ENVIRONMENT first**, then the env files (an
explicit `CORTEX_ENV_FILE`, then the repo `.env`, then the deploy root, then the Hermes-owned
one). So check the running process's own environment before concluding a file edit failed — a
value exported into a long-lived daemon outranks the file you just edited, while keys that daemon
does NOT carry still resolve from the file. That asymmetry is why one knob can appear to take
effect while its neighbour does not.

- **A CONFIG knob is live on the next call; a CODE change is not.** Knobs are read per call, so a
  config fix needs no restart and you can prove it with a live call immediately. Code needs the
  process to restart; until it does, the running daemon keeps answering from the revision it
  imported. Verify by comparing the deployed module's mtime against the daemon's start time, and
  treat the refusal's own wording as the tell for which revision answered you.
- **Edit a secret-bearing `.env` hermetically.** The read tools refuse such a file, and a shell
  rewrite risks the whole file. Assert the EXACT line you mean, replace one value, and print ONLY
  the changed line; keep a backup copy beside it. Then re-read just that key to confirm the value
  that will actually be resolved.

## Why a per-request timeout is not a wall-clock bound

An HTTP client `timeout=` bounds ONE socket operation, not the whole exchange: a server that
trickles bytes keeps every individual read inside the limit while the call runs for tens of
minutes. A real deadline has to be armed AROUND the call. A signal-based deadline fires only in
the thread that receives the signal, so a server that runs the call inline on its main thread is
fine and a worker thread needs another mechanism. Expect the deadline to fire as a REFUSAL naming
what it could not reach, never as a silent empty verdict.

## The unit that makes a wide range shippable: one blob

Judge the change in units the receipt already speaks, so a big range is a series of small
judgements instead of one impossible one.

- **Key the verdict to blob CONTENT.** A re-review of identical bytes is free, an edited file is
a new blob judged fresh, and a rebase stays cheap because content survives a sha rewrite.
- **Bound one pass and REPORT the remainder.** A cap per close plus a wall-clock budget, with the
unreached blobs named. Silently judging nothing is the failure shape a bounded pass exists to
avoid.
- **One call site, every exit.** Wire the pass where every close path converges (the point the
close is permitted), never at each individual exit: a pass wired per exit is skipped by the exit
nobody thought about, and the receipt then names fewer blobs than the range changed.
- **Required coverage must REFUSE when it cannot run.** If the whole-range review could not finish
and the per-blob pass is the fallback, a missing reviewer template or a dead reviewer is a refusal
with a named verdict — never a pass judged against empty instructions, which would read as
coverage of work no reviewer saw.
- **The receipt names only judged blobs.** Anything unjudged is omitted and the push gate names
it; that is what keeps a partial pass honest rather than hollow.
- **Pin the mechanism with a DYNAMIC test, not a source read.** Drive the pass's own decisions
  (required vs optional, always-review vs not, template present vs absent) with injected
  collaborators and observe whether coverage was asked for. A test that parses the file to prove
  every path calls the function verifies nothing about behaviour.

## Count the files before committing: one pass judges ONE blob

A range's close cost is set by its FILE COUNT, not by its size in lines: with the per-pass cap at
one blob, an N-file range needs about N closes. Measured on a 15-file change — every `end_change`
answered `N blob(s) of the push range still carry no review verdict`, judged one, and returned.

- **A remaining-count that drops by exactly ONE per call is healthy progress: keep calling.** The
  refusal names the count, so the decrement is the progress bar. Do not go hunting a bug in the
  close while it is behaving exactly as designed — that is where the wall-clock gets spent twice.
- **A count that does NOT move is the other failure**, and it needs the FILE fixed rather than
  another call (a blob whose verdict came back non-clean starves the pass — see below). Distinguish
  the two by the count, never by the wording of the refusal.
- **Budget the file count before you commit.** Files in one range trade linearly against close
  wall-clock: grouping a mechanical propagation into the smallest set of reviewed artefacts buys
  that time back, and a 15-file change is acceptable as long as you plan 15 passes up front instead
  of discovering it at the eighth refusal.
- **`… and N more` at the end of that list is TRUNCATION, not the total.** The refusal prints a
  prefix of the unreviewed paths; read the COUNT it leads with, never the length of the list it
  printed.

## A failed call must not end the pass — one slow blob is not an outage

A pass that stops on the FIRST failure deadlocks a range whose blobs each fit the wall clock
except the slowest one. Symptom to recognise from the refusal itself: it reports
`reviewed this pass : 0 blob(s)` round after round, together with a line naming ONE blob and a
deadline/timeout error. Nothing is cached, so the next attempt starts on the same blob and fails
the same way — the loop you built to make progress makes none.

- **Skip the blob whose call failed, and continue with the rest.** Name it as a reviewer
  FAILURE, distinct from "blobs not reached yet": collapsing the two hides whether you are
  waiting on latency or on work still queued.
- **Count only a REPLY that carries no verdict, or a real error — never a call that never
  ANSWERED.** A window-exhausted call is an ABSENT ANSWER, not a down reviewer: this class of blob
  answers in 180-220 s against a 240 s window, so the window runs out on a healthy call, and
  treating that as the outage signal ends a pass that would still have judged the rest of its wave
  (the flag defers everything the pass had not reached). Defer the blob — unjudged, never credited —
  and let the next pass retry it. The outage signal, two consecutive verdict-less REPLIES, stays as
  it was; a single failure followed by a success is latency either way.
- **An ANSWERED call must be read, whatever position it holds in the wave.** A wave awaited in
  submission order spends the whole window on its slowest member, so a LATER future that has
  already returned must be credited instead of being stamped "window exhausted" — discarding a
  verdict that was earned inside the window costs that blob a second review on the next pass.
- **Settle latency-versus-defect with a timed direct call, before blaming the reviewer.** Run the
  reviewer over the SAME blob's material directly and time it. Answering inside the window (a
  ~5 KB diff measured rc=0 in 191 s) means the governed path's slowness is scheduling rather than a
  sick reviewer, so the fix is units-per-call and the close is not re-rolled to "clear" it.
- **A failed call credits NOTHING.** The blob stays unjudged, the receipt omits it, the push gate
  names it — skipping is a scheduling decision, never a verdict.
- **Calibration.** A blob review of a real diff has measured 180-220s against a 240s ceiling, so
  with latency like that expect every close to reach only part of its blobs and the range to
  close over several rounds. The ceiling sits below the MCP client's own timeout, so it is not
  free to raise; the material per call is the lever you actually control (split the range).

## Tell reasoning time from a provider problem before blaming either

A slow reviewer and a sick provider look identical from the refusal. Separate them with a control
call through the component's OWN review function (the same `_call_reviewer` the pass uses, with a
tiny prompt): a small prompt answering in ~1-2s while a real blob takes minutes means the latency
is reasoning time on real material, not an outage — so retrying sooner changes nothing and the fix
is units-per-call, not patience.

**Resolve the TIER before you probe.** The pass picks its model from the change's tier, and a
light tier routes to a DIFFERENT (cheaper) model than the configured one. A probe against the
configured model therefore proves nothing about the governed path: measured, the configured model
answered the failing blob in ~15s while the light-tier model returned empty in ~36s on the same
material. Probe the model the tier actually selects, and say which model you probed — otherwise a
green probe sends you hunting a bug in a path the failure never came from.

Two rules for that probe:

- **It is a DIAGNOSTIC, not a review.** It writes no verdict and authorises nothing; say so when
  you report it. A committed review artefact must carry `provenance: advisory` unless its row
  exists in the recorded review store. Never let it stand in for the governed close pass.
- **Read its finding as a preview, then fix the material.** The probe returns the same findings the
  governed pass will, so acting on them before the next close is legitimate — but the fix lands as
  a new blob that the governed pass judges on its own.

## A blob already judged non-clean starves the rest of the range

Coverage asks for a CLEAN verdict per blob, so a blob whose review comes back FINDINGS is never
"covered" and is re-sent on the next pass. Verdicts are keyed to blob CONTENT, so re-reviewing
identical bytes cannot change the answer — the call is pure waste, and under a per-close cap of
ONE blob it also consumes the whole pass, leaving every blob sorted after it unjudged. Signature:
`reviewed this pass : 1 blob(s)` with the remaining count identical round after round, and a store
row for that blob from the previous round.

- **Skip a blob that already carries a verdict, but keep REPORTING it as uncovered.** Skipping is
  a scheduling decision, never a verdict: the blob stays in the refusal's count and stays out of
  the receipt, so nothing gains coverage and the close still refuses honestly. The only move that
  can turn it clean is fixing the FILE, which produces a NEW blob judged on its own.
- **Say so in the refusal.** A message naming "already judged, not clean" tells the operator the
  action (fix the file and commit) instead of inviting another identical round.
- **Test it with injected collaborators**, asserting three things together: the judged blob is not
  handed to the reviewer, it is still reported uncovered, and the pass spends its cap on a blob
  nobody has judged. A test that only asserts "reviewer not called" would also pass against a pass
  that silently dropped the blob from coverage — the hollow-receipt failure shape.
- **A re-review keeps returning the same verdict on identical content.** When the findings are
  non-blocking (info/low) and are about the range rather than the file, the fix for the BLOB is
  still an edit to that file or an explicit operator decision — never a loop of closes.

## Before the closure loop: score the cycle FIRST

The loop that retries a close must run AFTER the cycle is scored. Launching it in the same turn as
`feedback_accept` races the two: the loop's attempts run in the same second, each refusing
instantly with "this task's cycle is NOT scored", and the run ends having spent its attempts on a
row that was about to be scored anyway.

- Score, THEN start the loop (serialize the two — never concurrently).
- Do not try to time the score from the cycle row: the scoring update writes
  completeness/quality/progress/composite/decision, and leaves `timestamp` at the row's CREATION
  time, so the column cannot tell you when the score landed. If the ordering is in doubt, the
  proof is that the same close call now passes the scored-cycle check.
- A preflight in the loop is worth more than more attempts: check the cycle is scored (and the
  reviewer is answering at all) before spending an attempt on it.
