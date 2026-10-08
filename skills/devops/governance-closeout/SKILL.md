---
name: governance-closeout
version: 1.0.0
category: devops
description: "Use when a governed change will not close."
author: Hermes Cortex curator
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [governance, loop-governance, adversarial-review, lock, close-out]
    related_skills: [loop-governance, governance-lock-lifecycle, two-hard-rules]
---

# Governance Close-out

**Class of task:** closing a governed change — `feedback_accept` then `end_change` —
and everything that can refuse it: an unscored cycle, an unclosable cycle, an
adversarial review returning FINDINGS, or a fix to the close-out path that is not live
yet.

> The normative governance rules live in the repo (AGENTS.md, the loop-governance
> skill). This skill is the CLOSE-OUT procedure and the traps that cost time.

## The procedure

```text
cycle_query(status="pending")                  # every cycle for this session
feedback_accept(cycle_id=…, completeness=…, quality=…, progress=…, note="…")
end_change(task_id=…)                          # refuses while the cycle is unscored
```

A bare note is refused: pass scores, or an explicit `unscored_reason`. Decisions are
compared by CLASS, so a `LOOP` result still closes.

## The adversarial review gate

A COMPLEX change cannot close without a CLEAN verdict. Complexity is MEASURED from the
diff (≥50 lines, ≥3 files, or any always-review path such as `plugins/`,
`mcp-servers/`, `ops/scripts/cortex-update.sh`, `pre-commit-score`) — never
self-reported, and uncommitted work counts.

**Independence is CONTEXT ISOLATION, not a different model.** The design
(`docs/design/independent-adversarial-verifier.md`) defines it as: its own
process seeing only the output, a fixed orchestrator-owned prompt the worker
cannot edit, and an orchestrator-owned trigger the worker cannot invoke. (The
gate's reviewer also happens to use a different model, but that is not what makes
it independent — so never argue independence from the model name.)

That design point also names the trap: a review the WORKER invokes, in the
worker's own session, is a self-report — so the two mechanisms are distinct and
they are named accordingly, in the artifacts rather than only in the design doc:

| Name | Path | Independent? |
|---|---|---|
| `self-adversarial review` | loop-gov-mcp.py `end_change`, complexity-gated | **No** — worker-invoked, in-session |
| `adversarial review` | `ops/scripts/orch-bus/adversarial-review.py` sweep (fixed prompt, own process) | **Yes** — the evaluator |

Name a mechanism by the property that DISTINGUISHES it from its lookalike, and
propagate that name into everything it emits (log lines, verdict text, doctor
result names) — not just the design doc. Two mechanisms sharing one name is how a
later session merges the wrong one: sharing the CODE is fine (share the policy,
keep one implementation), but process, prompt and trigger are what carry
independence, and a name that hides the difference invites breaking it.
**Resolve the reviewer's MODEL in one place, and let a tier change the TRANSPORT,
never the model.** A tier that routes a small change over a faster path is a transport
decision; if it also silently substitutes a different model, the fleet's documented
reviewer is not the one that judged — and the stored row faithfully records a model
nobody chose, so the record cannot be used to notice the drift. Keep ONE resolution
used by both the caller and the recorder, so what runs and what is written down cannot
diverge, and make a different model an explicit, auditable opt-in.

**The verdict is durable, and the reviewer is a SAMPLING model** — re-running it on
byte-identical material can return the OPPOSITE verdict, so the verdict is stored
once per cycle and pinned by a fingerprint of the exact
material it judged (note + diff):

- `end_change` honours a stored verdict whose fingerprint matches the current
  material — CLEAN proceeds, FINDINGS blocks with the recorded findings.
- Material that moved after a review is judged again, so a CLEAN cannot be carried
  over a later, unreviewed change.
- A stored verdict with NO fingerprint is not reused.

### Working the findings

- **Keep the closing note FACTUAL and minimal — no self-assessment.** State what
  changed, the commits, the files, and the raw output. Do NOT narrate your own
  corrections, add an "honest limits" section, or pre-empt the reviewer's concerns in
  prose: a reviewer reads that as evaluation-shaped framing (`evaluation-awareness`)
  and it looks like shaping the verdict rather than informing it. The diff and the
  committed tests are the argument; the note is a caption. Honesty is not the issue —
  presentation is, and a factual note is also simply shorter. The ONE exception is a
  finding that demands a retraction: retract the claim in one line and state what IS
  verified in its place. Do not re-argue a claim the material cannot support.
  **Never explain the gate's OWN mechanics in the note — its character budget, a finding
  id, or what a previous round said.** Describing how the material is assembled or judged,
  instead of the change and its evidence, is graded `injection`/evaluation-awareness even
  when every word of it is true, and it blocks the close at MEDIUM. State the change, the
  commit count, the evidence path and the raw output; nothing about the review process.
  **Never write a sentence addressed TO the reviewer** — "if the reviewer judges this a
  process finding, I will split future ones" is graded as an injection attempt however
 transparent it is. A conditional promise, or your own classification of your own
 finding, belongs in neither the note nor the artifact.
 **Do not write the note in the REVIEWER's format.** Labelling your own paragraphs
 `ADV-<cycle>-N (severity) — …`, i.e. assigning yourself finding ids and severities, is
 graded `evaluation-awareness`: you are role-playing the reviewer on your own work
 instead of describing it. Write plainly — what changed, why, and the evidence path —
 and let the reviewer produce findings.
- **A refusal whose findings are ALL `unverified-claim` is an evidence gap, not a code
  defect — commit the artifacts and CLOSE AGAIN.** Every such finding is a true claim
  whose output lived only on a screen (a test count, a live-run result, a proof about a
  scratch resource, a fix for a defect the diff does not demonstrate). The remedy is to
  commit, in the SAME range, the verbatim run output and a re-runnable capture — not to
  edit code nothing found fault with, and not to rewrite the note. A refusal keeps the
  lock, so the retry is `end_change` on the SAME cycle: the material changed, so it is
  judged afresh. Do NOT open a fresh cycle for it — a new cycle's window is empty, its
  review is skipped as `simple`, and it authorises a range nothing reviewed.
- **Evidence about an EPHEMERAL resource is captured while it exists, or re-created.**
  A scratch unit or temporary process is deleted once the proof is taken, and a reading
  captured as it went away prints `MainPID=0 / NRestarts=0` — a contradiction sitting
  inside your own artifact. Re-run the proof and capture the reading live, and inline the
  resource definition and its probe IN the artifact so any host can reproduce it. The
  unit's JOURNAL survives the cleanup (`journalctl -u <unit>`), which is what makes the
  capture durable rather than a claim.
- **A pasted transcript is NOT accepted evidence, however true it is.** When the
  load-bearing claim is a measurement (the suite is green, the doctor is clean), the
  finding will be that nobody can re-run a transcript. Commit a RUNNABLE generator — a
  script that reproduces the measurement, writes an artifact, and exits non-zero on
  failure — and commit its ARTIFACT too, not just the script. One command must reproduce
  the claim.
- **Lead the artifact with its ASSERTIONS, not with its transcript.** The material bound
  cuts the artifact too, so a transcript whose proof lines sit in the omitted middle is
  unreviewable: the reviewer reports the claims as unevidenced while the output proving
  them sits on disk. Emit `RESULT: <n>/<n> assertions PASS, exit <code>` first, then the
  assertion lines verbatim, then the load-state evidence, and only then the verbose
  transcript. Same discipline for the note — it shares the character budget with the diff,
  so a long note crowds out the very material it points at: name the artifact, the
  revision and the assertion count, and stop.
- **The artifact must name the revision it ran against, and be run against the FINAL
  revision of the change.** A green artifact produced at an intermediate commit is
  exactly the finding it was meant to answer: the reviewer reads the revision field and
  asks for the run at the head of the change's commits. Generate it after the last code
  commit — the artifact's own commit may follow, since it is documentation. **Deploy LAST
  when the claim is deploy-sync.** A doctor capture taken between the commit and the
  deploy reads `Deploy sync — HEAD ahead of last deploy` and lands as a FAILING artifact
  beside a note claiming the tree matches: deploy first, capture, and remember the
  artifact's own commit moves the tree again — the push gate runs the mandatory dogfood,
  so deploy is the last step before the push rather than a step before the commit. **The named
  revision must also CONTAIN the generator that produced the artifact**: an artifact whose
  revision field predates the script it claims to come from is `fabrication` on its face,
  and the reviewer is right to file it. And never claim the run happened at the commit
  CARRYING the artifact — the file is generated and then committed, so by construction it
  can never name its own carrying commit. Say which revision it ran at, and that the
  generator is committed, so any reviewer can re-run it at HEAD.
- **The audited range is every commit since the lock, it is TRUNCATED, and it shows
  SUPERSEDED hunks.** The gate budgets roughly 12k characters of diff for a normal
  range, and a docs-only range gets several times that (see
  `references/adversarial-gate-material.md`, "Two budgets") — either way a large range
  reaches the reviewer with its middle omitted — and a range holding SEVERAL commits
  contains the earlier commits' hunks as well as the final ones. The reviewer then reads
  an intermediate state and files `fabrication` against a claim that is true of the
  final state ("the test still ages mtimes" — when the second commit deleted exactly
  that). Two things prevent it: **keep the audited range to ONE commit** wherever the
  work allows, and when it cannot be, **say the commit count out loud, name HEAD, and
  quote `git show HEAD:<path>` for the files under dispute** — the note is the material,
  so the final state has to be readable from it. Do not paste or commit the whole diff
  in response: a 100 KB range is what truncated in the first place, and committing it as
  an artifact duplicates git history and lands in the next range.
  - **When the reviewer's own reasoning is "the last commit does not touch <file>, so the
    earlier hunk stands", give it a commit that DOES touch the file.** A note quoting
    `git show HEAD:<path>` is not enough while the visible diff still ends on the
    superseded hunk. Fold a REAL improvement to that file into one more commit (a
    stronger assertion, a persistence check) so the final state is the last hunk the
    material shows — then the finding's premise is gone rather than argued with.
  - **Read the range's BASE off the material and claim nothing at or before it.** The
    range arrives named `<base>..<head>`, and `<base>` — normally the tip already on the
    remote — is a boundary, not a detail: a file you fixed and pushed in a PREVIOUS cycle
    is at the base, outside the window, so claiming it reads as `fabrication` even though
    the claim is true of history. Scope the claim with `git diff --stat <base>..HEAD`,
    and describe genuinely-earlier work as out of range in one clause rather than as
    evidence. A clean tree, a green suite or a dogfood pass is context the reviewer
    cannot check — omit it or mark it, never paste it beside a narrow diff as proof.
  - **When the range is more than one commit, make the NEWEST one the evidence commit.**
    The window keeps the HEAD and TAIL of the diff text and omits the middle, and
    `git log -p` emits newest-first — so the newest commit's diff is the part that is
    always readable, while an older large commit falls into the omitted middle.
    Evidence folded into the big EARLIER commit is unreviewable by construction; a
    small commit made LAST is visible. Point at the committed artifact for the full
    run rather than pasting it.
  - **Collapse UNPUSHED documentation commits before you close.** The artifact's own
    commit may follow the code commit, but a range of three or more commits is what
    truncates: fold the docs commit back with `git reset --soft <last-code-commit>` and
    re-commit once. Do this ONLY for commits you have not pushed — do not rewrite
    published history on a shared repo, and never force-push to make a range smaller.
  - **Same finding, same superseded hunk, two retries = stop re-writing the note.** It
    means the range is too long for the budget, not that your note lacked evidence.
    Shorten the range (one commit per close where the work allows) instead of
    re-rolling the reviewer — it samples, so a lucky CLEAN on unreadable material is
    not a fix.
- **A per-run artifact is OVERWRITTEN by the next run, so a FAILING run's evidence
  disappears the moment a later run passes.** Keep an append-only ledger beside it: one
  line per run carrying timestamp, revision, measured summary and failure count, so a
  failure cannot be erased by time. If you already overwrote one, commit the captured
  output as a file with a provenance header stating it is NOT regenerable and why — do
  not silently lose it, and do not re-run to reconstruct it.
- **Scrub the artifact at the SOURCE, not in the committed copy.** An evidence artifact
  carries host paths — the interpreter's bin dir, the checkout path, whatever the tests
  printed — and the leak detector flags `/home/<user>/…` in anything committed to a
  shared repo. Put the scrub INSIDE the generator (one function replacing the home dir,
  the checkout path and the python bin dir with placeholders, applied to every emitted
  line): a hand-sanitised copy is republished the moment anyone re-runs the generator,
  which is exactly what the artifact invites. The same guard reads a long digit run as a
  phone number and will refuse a repo write carrying raw PIDs — describe a process by its
  ROLE ("the reviewer child", "the cron worker's server") rather than its pid.
- **The committed artifact's SCOPE must equal the claim's scope — the SUMMARY
  included, not just the files.** A capture that ran ONE test file cannot
  substantiate "41 tests pass" across two — the reviewer checks the arithmetic
  and the gap is the finding. Regenerate the artifact to cover exactly what the
  note asserts: the run, not a slice of it. The same rule bites the per-test
  OUTPUT: a generator that keeps only the last N lines of each test's output
  truncates the `PASS (N):` block, so a 13-test harness reaches the reviewer
  showing 4 names while the note claims 13 — and it files `fabrication` against a
  claim that is completely true. The finding is then WRONG about the code and
  RIGHT about the evidence, which is the expensive shape: fix the generator, not
  the note. Size the tail to hold the whole summary (these harnesses print it
  last, so a generous tail suffices), and have it re-emitted in full.
- **When the load-bearing value is a personal identifier, commit the SHAPE and
  claim the shape.** An evidence artifact is a committed file, so a real chat id,
  hostname or key has to be redacted to its pattern (`hc-<agent>-<chat>`) — but a
  redacted artifact sitting beside a note that asserts the exact value is its own
  finding. Assert the property the reader CAN check from committed material (the
  key is per-chat, distinct, stable) and drop the value they cannot.
- **A guard that passes on the broken revision is not a guard.** Prove it
  discriminates before citing it: run it against the PRE-FIX revision
  (`git show <pre-fix-sha>:<path>` into a temp tree) and assert it FAILS there,
  then record both directions in the evidence. A guard only ever run against the
  fixed revision is a happy path with a name.
- **When a finding says "you claim X but the diff doesn't show it", add the CHECK.**
  The fix is not a paragraph of justification: make the tool verify X, then commit a
  test that drives it in BOTH directions — a healthy input passes, and one thing broken
  fails with the right remediation. That converts an argued claim into a checkable one
  (and is reusable by every host, unlike a pasted transcript).
- **FINDINGS → fix, then `rereview_change` with a NEW note.** An unchanged note is
  refused: re-review exists to re-judge a FIXED change, not to re-roll a verdict.
  Re-calling `end_change` on UNCHANGED material replays the stored verdict word-for-word
  and says so ("already recorded for exactly this material") — that message means the
  MATERIAL has to change, not the note: commit the artifact the finding asked for FIRST,
  then call `rereview_change`. Re-submitting the same material a third time is not a
  re-roll, it is a wasted cycle.
  **If `rereview_change` is not in the running daemon** (it answers `Unknown tool:`
  because the MCP server predates the deploy — see Pitfalls), the recovery is the
  same end state by the ordinary path: re-issue `feedback_accept` with the evidence
  note (the verdict is fingerprinted on the material, so a NEW note is judged
  afresh) and call `end_change` again. Do not re-explain in prose; add the output.
  That fallback holds only while the cycle is still PENDING. Once the cycle has been
  ACCEPTED — `feedback_accept` already returned MOVE_ON — a second `feedback_accept` is
  refused with `No PENDING cycle found for task '<task>' in this session`, which reads like
  a lost lock and is neither: the cycle is scored, and `rereview_change` is the ONLY path
  back, whatever the note. Do not score twice; re-review once with the new note.
- **Put the evidence where the reviewer can SEE it — the note IS the material.**
  The reviewer reads the note and the diff and cannot re-run a terminal, so a
  load-bearing claim with no output behind it in the material is graded
  `fabrication` no matter how true it is. Preferred: commit the proof as a runnable
  test. When the fact cannot be committed — a doctor summary, a queue drain, a
  delivery receipt, a process listing — PASTE the real output into the note (a short
  transcript of the actual lines, not a restatement of them), and say plainly which
  claims remain unverifiable and why. Saying "no receipt is available for a bot's own
  sent messages" beats both silence and an inference dressed as an observation.
- **"Unverifiable" is not "fabricated".** The reviewer cannot see a worker's terminal
  by construction, so a true claim whose output existed only on a screen is an
  evidence GAP; a fabrication finding has to name a contradiction the material
  actually shows. Answer it with a committed test that reproduces the behaviour,
  never with a re-explanation in prose.
- **When a finding charges you with another agent's change,** check authorship before
  editing anything: `git log --format='%h %an <%ae>' <base>..HEAD`. A lock window
  spans whatever a pull or rebase brought in, so a peer's commits can sit in your
  diff. Name YOUR OWN shas in the re-review note (the material states authorship, so
  the reviewer can check them against git) and re-review — do not "fix" a peer's
  change to appease a finding aimed at the wrong worker.
- **A fix that was merely REQUIRED to keep the tree green reads as `scope-drift` if it
  rides in the same range.** When the change forced a side-fix (a generated file had to be
  regenerated, a red suite had to go green), keep it in its OWN commit and state in one
  line why the change required it. An unexplained unrelated commit in the audited range is
  graded `scope-drift` at MEDIUM and blocks the close.
- **A `fabrication` finding can be about the MATERIAL, not about you.** The gate
  builds the material's "Diff stat" from the complexity MEASUREMENT while it builds the
  diff BODY from the cycle's COMMITS, and the measurement deliberately also counts your
  own uncommitted work. When the checkout is dirty — a peer's files, or an earlier
  task's WIP sitting in a shared tree — the stat names paths whose diff the material
  never shows, and the reviewer reads N files beside an unchanged HEAD as a
  contradiction. It IS one; nothing you wrote is false, and no rewrite of the note
  fixes it. Diagnose before reworking the change: compare
  `git diff --name-only <base>..HEAD` (what the stat should count) with
  `git status --porcelain` (what it did). The durable fix lives in the gate — build
  the stat from the same range as the diff body, and DISCLOSE a counted working-tree
  path the material cannot show as out of scope rather than naming it; failing that,
  COMMIT the work so the two agree.
- **A quoted PASS line without its warning count reads as a clean system — record the
  exit code and the COUNTS.** A borderless artifact can say genuinely true things and still
  mislead by omission: a dogfood/doctor transcript showing `DOGFOOD PASSED` while omitting
  `11 warn` and the unresolved drift block beside it, or a section tail with no `rc=`, is
  judged (correctly) as a swallowed error — the reader cannot tell a clean run from a
  noisy one. Every captured run carries its `rc=` AND its summary counts
  (pass/warn/fail). **When the run is genuinely NOT clean, say so with the numbers** and
  state the decision — "doctor rc=2, 14 warnings, the drift is pre-existing and recorded
  as issue N; this cycle's claim is the narrower one verify-landed proves" — because a
  narrowed, measured claim survives review where an implied clean bill does not. Record
  the re-run commands with their EXPECTED non-clean results so a later reader measures
  instead of trusting a PASS line.
- **Answer a false finding with a measurement, not with prose.** Findings can be
  wrong. State the measurement that refutes one and leave the code alone rather than
  "fixing" a non-defect.
  **The corrective commit is the worst case: the diff SHOWS the text it removed.** A
  commit that deletes a mistake (a traceback pasted into an artifact, a wrong claim)
  reaches the reviewer as `- <that text>`, and a finding can then assert the artifact
  "still shows" it — the removed lines are the evidence it cites. The same shape hides
  the GOOD news: a commit that leaves a section untouched contributes no lines, so a
  capture sitting in an unchanged section reads as absent ("contains the re-run command
  but not the captured output"). Before rewriting anything, measure at HEAD:
  `grep -c '<flagged string>' <artifact>` (0 matches refutes the finding) and
  `grep -n '<expected evidence>' <artifact>` (line numbers prove what IS there). Put
  those two numbers in the re-review note — a count and a line number, not an argument —
  and change the code only if the grep agrees with the reviewer.
  **Two such findings in a row, both refuted by grep at HEAD, means stop rewriting**: the
  range is being read through its hunks rather than its content (see the superseded-hunk
  rule above). Record the refutation, record the issue, and let the lock reach TTL —
  re-rolling the note cannot fix a material-assembly problem, and the precedent for an
  ops-only cycle trapped this way is an explicit recorded issue, never `force=True`.

## Verifying the gate actually RAN — a pass is not evidence of a review

A close that succeeds may mean the review passed, or that the review never ran.
Only the gate's own log separates those, and the gate writes **two** places:

- **`~/.hermes-cortex/logs/loop-governance.log`** — the cortex-owned record
  (bounded: rotates at 5 MB, 3 backups). **Read this one first**: it is ours, it
  sits with the other cortex logs, and it does not depend on Hermes's rotation.
- `~/.hermes/logs/mcp-stderr.log` — stderr, captured by the harness. Useful for
  live debugging, and it interleaves every gateway-spawned server, so prefer the
  cortex log when asking "what did the gate decide".

| Line | What actually happened |
|---|---|
| `self-adversarial review: cycle N simple (L lines, F files) — skip` | The change was BELOW the complexity threshold. No reviewer, no triage, no findings. A clean close here says **nothing** about review quality. |
| `self-adversarial review: cycle N stored <verdict> but all LOW (n) — not blocking` | A review ran and every finding was classified administrative and lowered, so it annotated instead of blocking. |
| `adversarial review: cycle N CLEAN` | The review RAN and PASSED. Note the wording: the pass line can arrive **without** the `self-` prefix, so a grep for `self-adversarial review:` alone returns zero hits on a review that ran. |
| findings listed with severities | MEDIUM+ findings blocked the close. |

**A refusal naming the reviewer UNAVAILABLE is an ENVIRONMENT fault, not a finding** —
usually the reviewer's own credential (auth error). It is the gate correctly refusing to
ship unreviewed, so fix the credential path instead of reworking the change:
`references/reviewer-transport.md` has the probe that discriminates (an authenticated
call — a public catalog endpoint returns 200 for a revoked key and wastes the cycle) and
the resolution order to check.

Cheap check before claiming "the gate passed": search **both** logs (the cortex log AND
`~/.hermes/logs/mcp-stderr.log`) for the CYCLE ID and for **both** wordings —
`adversarial review: cycle` (the verdict/pass line) and `self-adversarial review: cycle`
(the skip/annotate lines) — plus `triage:`. A zero-hit grep on ONE wording is not
evidence the review never ran: the emitted names differ by path and by the daemon's
code version, so search the ID, not the phrase you expect. The triage layer also logs
`triage: judgement status=…` and `reviewer severities stand` when the judge is
unreachable — silence there means triage never ran, not that it approved.

**A skipped review is silent by design**, so the log is the only evidence. Never
report a gate as "passed adversarial review" without it.

**A clean close is not evidence that the evidence SHIPPED.** The gate closes on the
cycle and does not push for you, and a push can fail transiently while another session
lands a commit in the same window (`failed to push some refs` after a fetch/rebase). So a
close whose note cites a commit that never reached the remote is a self-report with extra
steps — the whole point of committing the proof was that someone else can inspect it.
After closing, read the remote back:

```bash
git log --oneline origin/main..HEAD | wc -l      # must be 0 when you are done
```

Verify against `origin` (after a `git fetch`), never against the branch you think you
pushed. A push that failed is cheap to fix — fetch, confirm the local commit is a
fast-forward over `origin/main`, push — but only if you check, and the failure is silent
because the commit itself succeeded locally and the tree looks clean.

### Push order: PUSH BEFORE `end_change`, because the push gate needs the lock

The pre-push hook requires an ACTIVE lock — it refuses with *"the lock file must exist at
`~/.hermes-cortex/state/.governance-*.json`"*. `end_change` RELEASES that lock, so closing
first strands the push and you need a fresh cycle just to publish work that is already
reviewed. The operator's standing preference — **review precedes push** — lands the same
order from the other side:

```text
work → commit → review CLEAN → push (lock still held) → end_change
```

Do not treat "push then close" as the natural sequence. It is the shape that produces the
push-then-review complaint, because the review is the CLOSE step and therefore lands after
the push by construction. Review first, push second, close last; if you have already
closed, take a fresh lock naming the original cycle rather than leaving the commit
unpublished.

### Verify an artifact is TRACKED before claiming it is committed

`git add -A` does NOT mean the file was added: an ignore rule silently skips it, the commit
succeeds with a clean-looking message, and the reviewer — who sees only the diff —
correctly files `fabrication` against a claim naming an artifact that IS on disk but is NOT
in the commit. Confirmed the expensive way: an evidence log named `*.log` was skipped by
`.gitignore`, so the note asserting it had been committed was simply false.

```bash
git diff --cached --name-only                  # before committing
git ls-tree --name-only HEAD <artifact-dir>    # what the reviewer can actually see
```

Then let the repo's EXISTING convention choose the extension: artifacts already committed
as `.txt` mean the ignored `.log` was the wrong filename, not a missing ignore rule.

## Pitfalls

- **A fix to the close-out path is not live until the MCP daemon restarts.** The
  loop-governance MCP server is a LONG-LIVED process that loads
  `~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py` once — the same
  "deploy ≠ load" trap as the gateway holding the old enforcer. The CLI
  (`ops/scripts/loop-gov.py`) imports the server module fresh on every call, so it
  runs the repo code right now: use it to verify a close-out fix without waiting.
  The decisive symptom: calling a tool that IS in the deployed file returns
  `Unknown tool: <name>` from the running process. That means the daemon predates
  the deploy — not that the tool is missing — so a restart is the whole fix, and
  until then every newly deployed tool (e.g. `rereview_change`) is unavailable even
  though it is present in the deployed path. Restarting the GATEWAY from inside a
  session is blocked by design, but you rarely need to: kill the SERVER's own child
  (`ps -eo pid,ppid,args --no-headers | grep '<server>.py'`, then `kill <pid>`) and the
  gateway respawns it on the next call. Confirm a NEW pid appeared before trusting the
  reload, and expect the first call after the kill to answer *"lost its stdio subprocess
  … the operation may have completed"* — that is the restart, not a failure. Re-issue a
  read-only call (e.g. `check_lock`) to confirm the fresh process serves, then continue.
- **The CLI is a subprocess with no harness session.** Run from a plain shell it finds
  no session and answers `No active governance lock`. Pass `session_id` explicitly in
  the payload — the documented priority-0 override.
- **One session's close can wedge the SHARED loop-gov server for every other session.**
  ONE server process serves every session of its parent, and handlers used to run
  inline on the event loop, so a single `end_change` blocked the server from answering
  ANYONE while its adversarial reviewer ran for minutes — peer sessions then hit the
  300 s MCP client ceiling on *every* call, so a session could not close its own cycle
  because somebody else's close held the process (2026-10-06: the daemon was found
  wedged in `poll_schedule_timeout` with the reviewer child still running). Symptoms
  are exactly "governance is broken": every tool times out at ~300–420 s, `check_lock`
  lies, and closing your OWN cycle is impossible. Distinguish it from a refused close
  (findings) and from a lost lock (TTL): if *unrelated* calls also hang, the server is
  wedged, not your cycle. The fix is `asyncio.to_thread(handler, args)` plus an
  `RLock` around the shared-state primitives — deployed, but not LIVE until the daemon
  restarts (see the daemon pitfall above), so a wedge can persist after the fix lands.
- **A reviewer timeout at or above the client ceiling is a hang, not a wait.** The MCP
  client gives up at 300 s, so `ADVERSARIAL_REVIEW_TIMEOUT=420` never returns a
  verdict — the caller observes nothing and the close is neither confirmed nor refused,
  and the lock stays held. Reviewer budgets must be clamped BELOW the client ceiling
  (`REVIEWER_TIMEOUT_CEILING = 240`); prefer a short fail-closed refusal over an
  unobservable hang.
- **One lock per logical change.** `begin_change`'s description is fixed for the life
  of the cycle and must NEVER be hand-edited (that is fabricated governance state).
  The reviewer diffs the window from the lock's `started_at`, so stacking a second
  unrelated change under one lock leaves the description not matching the diff: the
  reviewer flags it, `rereview_change` cannot resolve it, and the cycle is unclosable.
  Only the orchestrator can clear such a cycle.

  The way this happens in practice is a NEW concern arriving mid-cycle — a peer
  reporting a bug in the code you just shipped, a fleet breakage, a follow-up you
  notice while verifying. Fixing it immediately is exactly the trap: the description
  was frozen when the lock was taken and the reviewer diffs from `started_at`, so the
  the added change reads as the description not matching the diff. Score and `end_change`
    the current cycle FIRST, then `begin_change` the new one — your own bug is not an
    exception.

    The lock is SESSION-SCOPED (one `.governance-<session>.json` per session), so
    `begin_change` hard-REFUSES while any lock is held — *"A governance session is
    already active … Call end_change first, or use force=True"* — and a refused close
    keeps that lock for its full TTL. That leaves exactly three exits: fix and
    re-review, ask an orchestrator to clear the cycle, or let the TTL reap it.
    `force=True` releases the held cycle to make room, so it is an override, not a
    convenience — never take it to get past your own refusal.

- **A timed-out `end_change` may have SUCCEEDED — do not report it as a failure.** The
    call can hit the MCP client's ~300 s ceiling while the reviewer is still working.
    Retrying then answers `No governance session active. Nothing to release.` — the same
    wording as an expired TTL, which reads like a lost close. Confirm from the gate's own
    record before saying either way: `grep '<cycle id>' ~/.hermes-cortex/logs/loop-governance.log`
    showing `<…> review: cycle N CLEAN` plus the cycle's stored decision means the close
    landed and the lock was released.

    **A close can also fail because the LOCK EXPIRED, not because it was refused.** The
    session TTL (one hour) is shorter than a long verification tail — deploying, waiting
    on a suite, re-running it after a finding. `end_change` then answers `No governance
    session active. Nothing to release.` while the cycle itself is already scored, so
    nothing is blocked and no doctor FAIL appears: only the lock is gone, and the
    remaining commit or push still needs one. Take a fresh lock for the leftover work
    (`begin_change` with a description saying it finishes that commit), close it, and
    name the original cycle in the note so the history stays legible. Score the cycle
    BEFORE any long verification step and this never happens.

    **A refusal blocks the LOCK RELEASE, not the work.** The cycle is already scored, so
    there is no unscored-cycle gate, no doctor FAIL and no blocked push — the entire
    cost is the held lock plus the findings on record, and the lock expires on its TTL.
    Say that plainly instead of reaching for `force=True` to "unblock" work that was
    never blocked.

    A refusal is RECORDED ON THE LOCK (`close_refused`: cycle, verdict, blocking count,
    finding ids, time) and a pre-commit advisory
    (`governance-refused-close-advisory.sh`) prints it at the moment new work is
    committed under it. Advisory only, always exit 0 — a blocking version could deadlock
    an agent whose close is legitimately stuck, which is a worse failure than the one it
    prevents. EVERY refusal path marks the lock: a MEDIUM+ verdict, a stored FINDINGS
    verdict, an UNREACHABLE reviewer, and a missing reviewer prompt template. If a
    refusal shows no marker, the daemon is running code that predates the marker —
    restart and re-check; do not conclude the refusal was harmless.
- **A close that hangs may be a WEDGED SERVER, not your cycle.** MCP servers are
  spawned per PARENT process (one gateway owns one `loop-gov-mcp.py`), so a session
  blocked inside `end_change`'s reviewer freezes the server for every session that
  parent serves — including yours, which then cannot close its OWN already-scored
  cycle. Do not rework the cycle and do not reach for `force=True`: prove the block
  first (`ps -eo pid,wchan:22,args | grep loop-gov-mcp`; `poll_schedule_timeout`
  means blocked in a `subprocess.run` on a reviewer child, `do_epoll_wait` means the
  server is healthy and the cause is elsewhere). Full probe and the off-loop rule:
  `concurrent-session-isolation` → "A wedged shared MCP server". The governance
  STATE is already per-session; only the transport is shared.
- **A cycle that will not close no matter what you change may be reviewing the WRONG
  REPO.** A lock carries BOTH `repo_slug` (a NAME) and `repo_path` (an absolute path),
  and `_adversarial_review_gate` resolves the tree it diffs from the lock's **`repo_path`**
  (falling back to `HOME/<repo_slug>` only for locks predating that field). When the two
  describe DIFFERENT repos, the gate diffs a tree that cannot contain your work: the
  reviewer returns FINDINGS every time, the close is refused forever, and each
  `end_change` retry spawns another full review.

  **The mixing is the defect, and it is diagnosable.** `_derive_repo_path` accepts the
  enforcer's observed absolute path, but a slug resolver that validates the injected slug
  only as `HOME/<slug>` — which fails for any checkout nested deeper than a HOME child —
  SKIPS it and falls back to the host-canonical repo. The lock then lands with a canonical
  slug beside an observed path (observed: `repo_slug: "hermes-cortex"` + `repo_path:
  "~/.hermes/hermes-agent"`). The fix, when you own the resolver, is to derive the slug
  FROM the same accepted path — one resolution, one repo — never a canonical slug beside an
  observed path. A session repo-hint that merely DRIFTED (it records whichever repo the
  session last touched a path in, so it can name one you are no longer working in) is the
  is the same symptom from a different cause.

    **A harness with NO identity injector at all is the third cause, and it hits EVERY
    non-Hermes caller** (pi, Claude Code, Codex CLI): Hermes injects the session's repo through
    the enforcer plugin, but a harness that merely spawns the MCP server injects nothing — so a
    resolver that falls through to the host-canonical repo tags a PROJECT-repo session as the
    shared cortex checkout. The close gate then refuses with *"the lock's repo cannot contain
    this session's work"*, there is no injector to repair it, and every `end_change` retry
    re-runs the whole review; in practice the OPERATOR deletes
    `~/.hermes-cortex/state/.governance-<session>.json` by hand. The rule: resolve the repo from
    the CALLER's own evidence — an explicit env hint (`CORTEX_SESSION_REPO`) first, else the MCP
    child's cwd — and keep the Hermes path excluded from that fallback so an injected identity
    still wins. Test the matrix both ways: a project-repo caller resolves its OWN tree, and a
    Hermes caller is never re-tagged from the shared daemon's cwd.

  **The tell is a finding that says the diff does not show your change while your own
  `git log` plainly shows it** — including the extreme form where the material's
  `Full diff:` is EMPTY or its file/line count matches a PEER's commit rather than yours.
  Check the lock BEFORE reworking anything:

  ```bash
  python3 -c "import glob,json;print([(json.load(open(p)).get('repo_slug'),json.load(open(p)).get('repo_path')) for p in glob.glob('$HOME/.hermes-cortex/state/.governance-*.json')])"
  ```

  Disagreeing values, or a `repo_path` that is not the tree you edited (`git rev-parse
  --show-toplevel`), mean no rewrite of the note can fix it. Also available as a
  guard read: the review refuses when the lock's repo holds none of YOUR commits in the
  window — but a guard keyed on "the lock's repo shows nothing" is DEFEATED by a single
  unrelated commit there (a peer's, a pipeline's), which is exactly how a wrong-repo
  close gets as far as permanent findings. Key such a guard on AUTHORSHIP (does the
  lock's repo hold any commit this session authored), never on an empty change count.
- **The wrong-repo refusal is the MCP guard; the CORRECT tagging is the enforcer plugin — separate lifetimes, so seeing the NEW refusal text does NOT mean the injection is loaded.** The refusal you get on a wrong-repo close comes from `loop-gov-mcp.py`, which is spawned FRESH per call and therefore always runs current code. The thing that tags the lock with the session's real repo (`_inject_session_context` / `_note_session_repo` in `plugins/governance-enforcer/__init__.py`) is a PLUGIN loaded ONCE into the long-lived gateway process (`PluginManager.discover_and_load` at process start). So a host with current code on disk and current guard text can STILL produce an old `hermes-cortex`-tagged lock — the running gateway holds the pre-injection enforcer. The guard even says it: "once that is deployed AND the gateway has reloaded it". The fix for the affected host (dev macOS = Titus) is NOT another deploy; it is reloading the gateway so the enforcer rebuilds: `hermes gateway restart` (macOS launchctl; Linux systemd `hermes gateway restart`). There is also a hot control-socket verb `reload-plugins` (gateway/run_plugin_rewire.py) that rebuilds plugins WITHOUT a process restart — prefer it for a minimal blast radius. Do not keep re-deploying files; reload the loaded plugin.
- **A wrong-repo lock could leave DEBRIS in the other repo, and that debris blocked the
  push.** A mis-tagged lock wrote its secondary marker to
  `<repo_path>/.hermes-cortex/.governance-lock`, dropping governance state into a repo it
  did not govern — including the upstream Hermes checkout, which the pre-push dogfood gate
  then fails on (`Cortex must not edit ~/.hermes/hermes-agent`), blocking a push for a
  change that is otherwise fine.

  **The durable fix is that the marker is GONE: locks are runtime-only. Removing the
  resolver bug alone was the wrong fix — a marker that can authorise against a repo the
  session never touched is a liability, not a safety net.** `_secondary_lock_path` now
  returns `None` on BOTH sides (the MCP server and the enforcer plugin), so nothing may
  write governance state inside a repository; `plugins/governance-enforcer/README.md`
  documents the phase as removed. Both git hooks were unaffected either way — they scan
  `~/.hermes-cortex/state/.governance-*.json` directly — so dropping it cost no
  enforcement. If you DO find stray debris, it predates the drop or the daemon still
  holds pre-drop code (see the daemon pitfall: the reload is the fix, and until it
  restarts a fresh `begin_change` can re-create the marker). Clearing it is DESTRUCTIVE
  and needs operator consent, and you may not be able to clear it yourself — the enforcer
  scopes your lock to the LOCK's repo, not the one holding the debris — so back it up,
  report the exact path and command, and stop rather than routing around enforcement.

  **Report it and take a fresh lock; do not fight it.** Re-pointing lock identity is a
  fleet-wide change, not a local workaround. Note a long verification tail can outlive the
  1-hour session TTL, so the lock may be GONE by the time you get here (see the expired-lock
  pitfall) — take a new one for the leftover work and name the original cycle in its note.

- **`rereview_change` requires an ACTIVE lock, so a mid-task deploy can strand the
  documented FINDINGS → fix → rereview path.** It answers `Cannot re-review: No active
  governance lock` once the lock FILE is gone — and re-taking a lock is itself refused
  while the session is still live ("a governance session is already active … call
  end_change first"). That three-way state (no lock file, live session, refused rereview)
  has exactly one exit: `end_change(<task_id>)` on the live session, which judges the
  CURRENT material. Commit the artifact the finding asked for FIRST — that is the only
  thing that makes the next verdict differ — then close; do not hunt for a way to re-take
  the lock.
- **Score before you investigate.** A cycle left PENDING with no live lock is a doctor
  FAIL that blocks every push, so scoring an orphaned cycle is the first move, not the
  last.
- **A cycle you opened and then did NOT work in still has to be closed.** When an
  approval times out, the operator redirects, or you stand down mid-task, the cycle is
  left PENDING and blocks the next push. Close it with `unscored_reason` stating that
  nothing happened and why ("cycle opened to restart the daemon; approval timed out,
  no change made") — an explicit unscored close is an accurate record, while walking
  away from the cycle is a leak. Do not leave it for the reaper, and do not let the
  abandoned cycle stop you from reporting which half of the work is still pending.
- **`check_lock` can say `active: false` while `begin_change` refuses with "a governance
  session is already active".** They read different things — the session/lock registry vs
  the lock file — so a lock the reaper has already reaped, or a session whose TTL has not
  expired, makes them disagree. Trust the REFUSAL: it names the held `task_id`, its
  `started_at` and the session id. The exits are `end_change(<that task_id>)` or the TTL;
  it is never a reason to reach for `force=True`, which releases someone else's cycle to
  make room for yours.
- **Probe the schema before you commit a query as evidence.** The governance DB's tables
  are NOT named after their contents: cycles live in `loop_cycles`, and recorded issues
  are rows in `task_events` (`id, timestamp, task_id, agent, event_type, from_state,
  to_state, detail`) — there is no `events` table, and guessing one both fails and, when
  the guess is committed into an artifact, publishes a traceback where proof was claimed.
  One `SELECT name FROM sqlite_master WHERE type='table'` first; a query you intend to
  quote belongs in an artifact only after it has returned a row.
- **Test a verdict-recording helper BOTH ways.** One exercised only by re-recording an
  existing row never runs its insert path — assert the first record into an EMPTY
  cycle too, or the insert half can be silently broken while the suite is green.
- **A test that models the lock WINDOW must open the window BEFORE creating the work.**
  The gate measures the commits since `lock.started_at`, so a self-test that commits
  first and computes the timestamp afterwards places its own fixture OUTSIDE the window
  and fails for a reason that has nothing to do with the code under test. Capture the
  window start, THEN create the work. Also point sandbox repos at an empty
  `core.hooksPath`: otherwise the host's global git hooks fire on every fixture commit
  and add seconds of latency between the two, which can push the work out of a narrow
  window by itself. (Compare the window as EPOCH seconds, never `git log --since=` —
  see `concurrent-session-isolation`.)
