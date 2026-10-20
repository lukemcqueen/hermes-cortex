---
name: change-checklist
version: 2.3.0
category: software-development
description: "Mandatory pre-ship verification before calling end_change(). Covers survey, test, adversarial verify, multi-OS, multi-role, docs, final verification, and reflexion. Every governance cycle must run this before closing."
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [governance, testing, documentation, multi-os, multi-role, quality]
    related_skills: [loop-governance, change-test-loop, two-hard-rules, cron-job-management, survey-before-action, agent-contract]
---

# Change Checklist — Pre-Ship Validation

The easy path (one file, one test) is never the complete path. Ask: what else does this touch? Did the SYMPTOM resolve? Did I check sibling locations? Did I run the doctor? Did I push so the fleet benefits?

Load this before end_change() on any script, deploy-config, cron, shared-doc, or updater change.

## Writing Quality (prompts, docs, skills)

1. **Concrete examples, never abstract placeholders** — show real-looking values (`43 cycles scored`, `$0.006/run`, `2026-07-15 10:01 KST`), not templates (`[N] cycles`, `<cost>`, `<datetime>`). LLMs mimic concrete structure faithfully; they interpret placeholders loosely.
2. **Be concise — every sentence must earn its place.** After writing, review: "Would the agent do anything differently if I deleted this?" If no, delete it.

## Phase 0: Survey the Change Surface (BEFORE begin_change)

- [ ] Pushback Check (3 questions, BEFORE begin_change) — Is this idea wrong (harm, data loss, wrong scope, better mechanism)? Is there a clearly better alternative? If you raised an objection, do NOT begin_change until the user acknowledges (override is final). Silence is not consent (SOUL P5).
- [ ] **Plan review before building (operator standing rule).** For any non-trivial build, get the
      PLAN independently reviewed BEFORE writing the code — the operator's words: *"have deepseek pro
      ALWAYS review your plan before building"*. Submit it through the GOVERNED path
      (`ops/scripts/orch-bus/adversarial-review.py --cycle-id <new-cycle> --material <plan>
      --review --reviewer-id <id>`), which records a row, then act on its findings before coding.
      **`--material` is the material TEXT, not a path — pass the CONTENT (`--material
      "$(cat <plan>)"`).** Hand it a filename and the reviewer receives that filename and
      nothing else: it reports that there is nothing to evaluate, records `CLEAN` with a single
      `info` finding quoting the path back, and the script still exits 0. That row is a review
      that judged NOTHING, and it is indistinguishable from a pass until you read the stored
      `summary` — the exact shape of a "reviewed CLEAN" claim built on no review. Before
      treated as a review, read the row back and confirm its summary describes
      judging content (`governance-closeout` has the vacuity check and the store path).
      **It is a FINDINGS gate, not a design service — expect no prose proposal even when you
      asked for one.** What comes back IS the spec: name the seam that owns the decision, the exact
      result shape, the threshold — so put the CODE MAP (`file:function:line`), the hard
      constraints and the options you already rejected INTO the material, and its findings arrive
      as actionable requirements instead of `unverified-claim`. A request that states the problem
      and asks for a design without that context gets told its own claims are unsupported.
      Include the material it must judge — the source, the tests, the measured output — because a
      plan submitted as prose comes back as nothing but `unverified-claim` findings; that is the
      reviewer working correctly, not a reason to re-run it. Expect it to CUT scope: obey the cut
      instead of defending the step (a planned documentation edit was refused as "notes instead of
      controls" — the operator's own standing objection).
      **Never phrase the material as a REQUEST — an imperative addressed to the reviewer is filed
      as a HIGH `injection` finding.** "Judge the CODE below", "Identify the gaps and the smallest
      changes": the reviewer's input is DATA, so any ask reads as an attempt to redirect it, and the
      whole submission is refused without engagement. The identical material with no ask comes back
      CLEAN while saying nothing, because there is nothing to falsify. Read that pair as the gate's
      actual contract: it answers *"are these claims sound?"*, never *"what should I build?"*. For a
      genuine design or architecture question, hand `subagent-architecture-party` the measured facts
      and a `file:function:line` map and let its roles attack the design — do not invent a third
      review channel, and do not keep re-phrasing the same ask at the governed gate.
- [ ] **Name the cycle for the diff it will CONTAIN, not the instruction that started it.** A task id that under-describes the work fails the close on scope drift no matter how good the evidence is: the reviewer sees the real range and refuses a cycle whose name does not cover it. An instructed next step ("pull latest and update", then a follow-on reconciliation the update itself demanded) belongs in its OWN correctly-named cycle — do not fold a derived deliverable into the parent's cycle.      Check before begin_change: does `<task_id>` describe every path the range will touch? If not, split it. (Cost of getting this wrong: cycle 12012 was refused four times and held a 60-minute TTL wait; the identical work closed CLEAN on the first attempt under a correctly-named cycle.) Recovery for an already mis-framed cycle: retire it through the state machine (`advance_task_state` → `cancelled`, reason logged, no override) and open a correctly-named one — never `force`/override.
- [ ] **Size the range so the CLOSE review can read it, and decide that before the last commit.** A wide range (measured: 8 files / 381 lines) exhausts a reasoning reviewer's output budget — it returns no usable content at `max_tokens=48000` and again at `96000` — and raising the cap does not help, because that budget pays for thinking and answer together. Narrow ranges close normally, so plan the work as reviewable slices up front; once every commit exists, no new cycle can cover them and re-slicing means rewriting your own history. **A wide range is no longer a dead end**: an unfinished whole-range review RE-ROUTES to a per-blob pass (verdicts cached by blob CONTENT, bounded per close by a blob cap and a wall-clock budget), so the range closes over SEVERAL attempts with each attempt continuing from the cache. Drive that with a loop whose stop condition is a receipt for the CURRENT tip instead of treating the first partial pass as a blocker — and expect the partial pass to REPORT the coverage it did not reach rather than judge nothing. Sizing remains the cheap lever: the fallback costs several close rounds on a slow reviewer.
- [ ] Foreign working-tree check — `git status --short` says WHAT is staged (column 1) vs unstaged (column 2), **never WHO staged it**. Do not infer a concurrent peer from that shape: establish authorship first (`git log --oneline -3 -- <path>`, `git log -1 --format='%an %ae'`, `git reflog`). When you are the only writer on the host — the normal single-agent case — staged-but-uncommitted work is YOUR stranded work from an earlier session: land it in its own correctly-named cycle, or discard it deliberately, but never route around it and never write "another session" into a commit message on that assumption. For genuinely concurrent writers: coordinate, and never stash/clean/commit a peer's files (SOUL P9).
- [ ] search_files() for the old name/term across the whole repo.
- [ ] Live cron prompts — grep ~/.hermes/cron/jobs.json for the old term; source edits don't rewrite existing jobs — update each hit via cronjob action='update'.
- [ ] Cron manifest — install-crons.sh AND install-orch-crons.sh: uninstall arrays, create_cron blocks, guards.
- [ ] Updater — cortex-update.sh register() calls.
- [ ] Doctor — cortex-doctor.py parse_expected_crons() / parse_orch_crons() read the uninstall arrays.
- [ ] Deployed path — verify ~/.hermes-cortex/scripts/<script> exists at runtime, not just the repo.
- [ ] Category — orchestrator-only (orch-* in install-orch-crons.sh) vs all-agents (agent-* in install-crons.sh). Update the fleet-reference.md cron table.
- [ ] Install array sync — create_cron block name must match the uninstall array entry EXACTLY. Run python3 ~/hermes-cortex/ops/scripts/manage/fix-cron-duplicates.py (zero issues = in sync).
- [ ] Old cron cleanup — crons don't self-destruct; confirm the old name was removed.
- [ ] Governance lock — after begin_change(), confirm with check_lock. **Pass the session context:** a bare `check_lock()` with no args cannot resolve the session and reads a FALSE "inactive" while your lock is live — the enforcer then blocks the very next write. Trust the lock FILE (`ls ~/.hermes-cortex/state/.governance-*.json`) over a no-arg reading, and when the two disagree, the file is right and your close is still permitted. (Observed 2026-10-10: a no-arg `check_lock` reported inactive, the operator-visible file was active, and the close then succeeded — the false reading had nearly cost a needless re-acquire and a second cycle.)
- [ ] PII scan — bash ~/hermes-cortex/ops/scripts/secret-leak-detector.sh before pushing.

## Phase 1: Test the Change (no simulated output)

- [ ] Scripts — run with real inputs, verify real output. ⚠️ DOGFOOD (enforced): the deployed copy must run its real scheduler invocation — cortex-update.sh then cronjob action='run' job_id=<id>. Manual python3 script.py does NOT update the scheduler's last_status (the doctor reads scheduler status). Run the full command, not an imported function.
- [ ] Config — diff generated vs deployed; only intended changes.
- [ ] Syntax — .sh bash -n; .py py_compile; .yaml yaml.safe_load (hook catches staged files; verify unstaged too). **A patch tool that reported a NON-EXACT match has verified nothing by definition** — a fuzzy match can drop a keyword or the quoting around a block (each `echo "…"` line collapsing to bare text, which then parses as a command) while still reporting success, so re-read the returned diff and run the syntax check for that file in the same step rather than at the end of the task.
- [ ] **A scripted bulk edit must ASSERT its match count, then be scanned for artefacts.** Replacing
      one string across many files (a `python3 -` heredoc walking `rglob`) reports success whatever it
      did: a silent 0 leaves a file unfixed while a silent 2 corrupts the second site. Assert the count
      per file before writing (`assert text.count(old) == 1`, or the number you expect) and fail loudly
      on a mismatch, then grep the tree for what a blind replacement leaves behind — unbalanced
      backticks in inline code, escape residue such as `[0m`, a truncated path — and re-read the
      returned diff. Splicing a parenthetical INTO a line that already delimits inline code is the
      reliable way to break the delimiters: rewrite the whole sentence, or check the rendered line,
      before committing. A file of prose has no compiler to catch this; the scan IS its syntax check.
- [ ] nginx — sudo nginx -t.
- [ ] **Run the sibling tests that exercise the seams you CHANGED — a green regression harness does
      not cover them.** A curated harness runs its own file list, so an older test that drives a
      helper whose signature, verdict writer or contract you moved can be left RED while the harness
      everyone trusts stays green. Grep the test tree for the symbols you touched
      (`rg -l "<function>" tests/`) and run those files in the same step as the syntax check. Then,
      before blaming your change, prove pre-existence: run the failing file at the RANGE BASE in a
      worktree (`git worktree add <dir> $(git merge-base origin/main HEAD)`) and compare the OUTCOME
      — a named failing test on both sides — not the bare exit code, which two runs that measured
      nothing share (`references/close-review-evidence.md`). An identical failure predates you, and a red test nobody runs is a finding to RECORD, not a
      regression to absorb or quietly fix inside someone else's cycle.
      **A DIFFERS verdict is not automatically yours, and the worktree is why.** A `git worktree`
      materialises TRACKED files only, so any UNTRACKED directory in the main checkout — a leftover
      venv (`.venv-brief/`, `site-packages/`), a build output, a scratch tree — exists on one side of
      the comparison and not the other. A runner that walks the repo with a glob (`REPO.glob(...)`,
      `rglob`) then reports a DIFFERENT verdict for reasons that have nothing to do with the range:
      expansion wanders into vendored site-packages, and the set it accumulates (that library's
      dependencies, not your code's) is junk. Before attributing a differing failure to yourself,
      check which side owns the extra directory (`git ls-files <dir>` empty = untracked; `git
      status --short` for `??`), and treat a repo-wide GLOB sweep as a probe whose verdict depends on
      local untracked state — pin it with a fixture, and exclude dot-dirs and `site-packages` rather
      than trusting the run.

## Phase 1.5: Adversarial Verification (MANDATORY — no bypass)

Enforced at 3 layers: pre-commit hook (static gate), enforcer (blocks commit until adversarial-verifier loaded), and this checklist.
- [ ] Static gate on every changed script: python3 ~/.hermes-cortex/scripts/adversarial-verify.py --file <file> --level A2 --gate. A4 for plugins/, hooks/, mcp-servers/, ops/scripts/manage/, cortex_doctor/, quality/, tests/, and enforcement scripts. Critical/high → block. No --no-verify.
- [ ] **Pin a before/after comparison to an immutable revision, and name both revisions in the
      artifact.** A baseline recorded as "HEAD", "the working tree", or a stash is unrepeatable the
      moment your own commit lands — HEAD then IS the change, so the comparison can never be
      re-run and the reviewer correctly refuses it. Record the baseline SHA and the tip SHA in the
      evidence and the cycle note; re-running the tool against those two revisions must reproduce the
      counts exactly. **Resolve the baseline as the RANGE BASE — `git merge-base origin/main HEAD` —
      never a relative `HEAD~1`.** A relative base is right only until the next commit of your own
      lands; after that the "before" side already contains half the fix and the comparison silently
      stops testing what it claims (regenerating the artifact then compares a revision with ITSELF).
      Print the resolved sha in the artifact so a reader can re-run it. **And a committed artifact
      that reports FAILING items must ATTRIBUTE them**: re-run each failing item at the range base
      with the SAME runner and print both exit codes beside a verdict (`REPRODUCED` / `DIFFERS` /
      `COULD NOT VERIFY`), because a bare failure list says nothing about whether the range caused
      it and is filed as unverified-claim. **Quote only numbers a COMMITTED artifact prints** — a count read off a live
      tool run and never committed is itself an unverified claim, and it is filed as one at HIGH even
      though the run really happened: the reviewer reads the diff and cannot see your terminal. Before
      writing a before/after into a note, commit the capture that shows BOTH sides. When a committed
      artifact's numbers turn out to disagree with a figure you already stated, WITHDRAW the figure
      explicitly and once ("the earlier count came from a live report, is not artifact-backed, and is
      withdrawn — the artifact's own numbers are these") — re-explaining it appends a second copy of a
      claim the artifact beside it contradicts.
      **ONE note, ONE run.** Every number in a close note must come from the SAME run as the committed
      artefact beside it. A deploy log and a pre-deploy transcript are two different runs: quoting the
      deploy's `N pass / 0 fail` while the committed transcript reads `FAILING (N-1 pass, 1 fail)` is
      filed as FABRICATION at critical, and rightly — the reviewer reads the diff, sees both, and
      cannot tell which run you meant. When the run you want to quote is not the committed one,
      RE-GENERATE the artefact after the deploy rather than quoting the other run's numbers. And when
      a claim is about a FILE, name the commit that actually carries it (`git log --oneline -- <path>`):
      "committed in this range" about a file that landed in an earlier, already-pushed commit is the
      same finding.
      **The baseline belongs INSIDE the check's DEFAULT, not only in how you invoked it.** A
      discrimination check whose default baseline is a branch ref (`origin/main`) stops
      discriminating the moment the change is pushed: the ref then IS the change, the check
      reports "the pre-fix revision already carries it", and a tautology wears a PASS. Pin the
      exact revision in the script's own default with a comment naming which revision it is and
      why — a baseline you must remember to override on every run is a check that will silently
      stop testing what it claims. Re-run it after pinning and show the discriminating line.
      **And ASSERT the baseline reproduces the defect, or the comparison proves nothing.** Pinning
      a revision is only half the rule: a baseline that already passes is a tautology wearing a
      PASS, and it is filed as fabrication even when every command really ran. Make the failing
      side an assertion inside the check — the pre-change revision must flag the OLD behaviour,
      and detail that asserted state in the artifact so a future reader can see the baseline was
      exercised, not merely named. An artifact that EXTRACTS its baseline from git needs the same
      proof one level down: grep the extracted copy for a symbol the fix INTRODUCED (absent ⇒ the
      extraction really is the pre-change revision). That assertion is what catches the drift this
      bullet warns about — without it, a baseline that silently starts resolving to the fixed code
      keeps printing success, and the reader has no way to tell.
- [ ] "0 findings" is NOT a pass — execute the changed path with boundary inputs (-1, 0, None, empty, inf/nan, non-ASCII); attack the premise (list implicit assumptions, violate each with a 30s test); verify deployed == loaded (restart/daemon check for guards/hooks/enforcers).
- [ ] A green check is not evidence until you have seen the assertion RUN. A test
      file with no executable entry point (a pytest-style file with no
      `if __name__ == "__main__":` when pytest is absent) imports, runs NOTHING,
      and exits 0 — so any harness that records `rc=0` scores it PASS. Prove a test
      executed by its OUTPUT, not its exit code, and make the harness REJECT any
      entry it cannot actually run. **A duplicated definition is a silent disarm**: Python
      keeps the LAST `def main()`, so a file carrying two of them runs the second and leaves
      the first — and every check only it contained — dead, with the suite still green.
      Assert the definition is unique (or assert the property directly) so the duplicate
      cannot come back. **Grep the module for the symbol BEFORE you add a helper to it.** In a
      shared module a re-used name is the same disarm one level up: a new local `_candidate_repos`
      beside an existing one leaves the LATER definition live, so your new code calls the old
      one — or yours sits dead — and the suite stays green either way. Grep first; if a helper
      already does the walk/predicate/parse you need, REUSE it (cap or wrap it) instead of
      writing a second copy, and assert uniqueness where the two could collide.
- [ ] **A captured check transcript must carry its EXIT CODE and its WARNING COUNT — a bare
      PASS line is a swallowed error.** A gate that prints `✅ PASSED` while emitting N warnings
      and an unresolved sub-check reads as a clean system to everyone downstream, including the
      close reviewer, which files it as exactly that. Capture `rc=$?` beside the command, record
      the warning count, and write the measured numbers into the evidence — including the ones
      that are NOT clean ("rc=0 with N warnings and unresolved X" beats a PASS line with the
      warnings omitted). A transcript with the counts absent is not evidence: the reader cannot
      tell a clean run from a skipping one, and a summary line claiming cleanliness the
      transcript contradicts is a fabrication finding.
- [ ] **An evidence script must be READ-ONLY: never repair what it measures.** Invoke every tool
      it runs in its non-mutating mode. Measured 2026-10-14: a capture ran
      `check-skill-drift-parity.py` WITHOUT `--check`, which REGENERATES the tracked artifact it
      was comparing — so the run rewrote its own baseline and could never report it stale; the
      flag existed and was documented. Prove the mode both ways (a missing baseline must exit
      non-zero WITHOUT writing anything) rather than trusting the help text.
- [ ] **Read a script's TAIL before importing it to exercise it — a module-level entrypoint runs on
      IMPORT.** An import is not a load if the file ends in `count = work(); sys.exit(0)`: importing
      it performs the work, and repointing its paths after the import is too late. Measured: a probe
      importing a purge script to drive its shipped logic removed 780 files from the LIVE state dir
      before it could repoint anything. Check the tail first; if it has a module-level entrypoint,
      either fix it (`main()` behind `if __name__ == "__main__"` — inert on import, unchanged when
      run) or load a COPY with the entrypoint stripped. Then verify the fix in both directions: an
      import changes nothing, and running the file still does the work (redirect HOME/CORTEX_HOME in
      a subprocess and assert the effect landed THERE). Import-must-be-inert is the same rule as
      read-only evidence, applied to the module instead of the tool. **A COMMENT claiming inertness
      is not evidence — assert it, and expect the assertion to refute the comment.** Run the import
      under a redirected HOME and assert on EXACTLY what may appear there (the module's own log file
      plus the directories leading to it, and nothing on the store/state side): an `# inert on
      import: the work is behind __main__` note beside a bare `exec_module` is a claim to check, and
      a module that writes its log at import is normal — the artifact should carry the true, narrower
      statement rather than the tidy one.
- [ ] **An outbound call you make from a scratch script is outside the audited tool path — say so.**
      Calling a model endpoint (a review, a summary, a classification) from a helper under the
      scratch dir does not appear in the enforcer's log, because the enforcer audits TOOL CALLS and
      an HTTP request from a subprocess is not one. That is not automatically wrong — an independent
      review is worth having — but it must not be presented as the sanctioned reviewer, and the
      operator will ask. Make it auditable instead of hidden: commit the material that went OUT
      (extract it with `ast`/from the real file, never retype it) and the response that came back
      VERBATIM, with your accept/reject judgement after a marker, under `docs/evidence/`; resolve
      any credential through the component's own config helpers so it is never printed or passed by
      hand; state plainly in the artifact that it is advisory and authorises nothing (the push
      receipt comes from `end_change`'s own reviewer).
      **Do not build a parallel review path AT ALL — not a scratch helper, and not a convenient new
      mode on the registered script either.** A second convenience interface legitimises a capability
      the operator rejected outright ("if you can do this, why wouldn't other agents do this, but for
      nefarious purposes?"): the payoff for doing it badly is manufactured evidence of verification,
      which is the thing governance exists to prevent. Delete the shadow path and use the RECORDED
      one — `ops/scripts/orch-bus/adversarial-review.py --cycle-id <cycle> --review`, which writes a
      row into `adversarial_reviews` — because a review a future reader can re-run is the only
      deliverable; the close-time reviewer's receipt is the review of record either way.
      Any artefact you keep from an ad-hoc call must DECLARE itself: a committed file that presents a
      review carries `provenance: advisory` (commentary, never citable as verification) or
      `recorded-in: adversarial_reviews review_id=<id>` whose row EXISTS — a claimed id with no row is
      treated as fabrication. Enforcement for that lives in the ARTEFACT plus a blocking check (a
      doctor FAIL), never in prose: `references/detection-gate-design.md`.
- [ ] **Redact at the GENERATOR, and keep the redaction narrow.** A transcript committed to a
      PUBLIC repo must not carry `/home/<user>` paths, the host name, or `ls -l` ownership. Apply
      ONE normaliser to every emitted line — never hand-patch the committed copy, which soon
      disagrees with the command printed above it. Redact the host only in host CONTEXTS (`Host:`,
      `@host`): a bare replace of the host's name also mangles legitimate identifiers that share
      it (a DB role, an agent's own name).
- [ ] **An artifact must not tell the reviewer what to conclude.** A `READ THIS FIRST` block
      asserting the verdict ("note 0 fail ... both green") is injection, and it reads as
      fabrication the moment the output beside it contradicts it — the same artifact it described
      exited 1 in that very block. State PROVENANCE instead: what produced the file, which
      revisions it compares, which fields are volatile by design.
      **The same binds a SECTION HEADING, and that is the sharper case.** Rewriting a section's
      body to report a measured branch while its title keeps asserting the old conclusion is
      filed as fabrication: the heading is the reader's first impression and the output that
      disproves it sits two lines below. When a section becomes a COMPARISON ("does the running
      process carry this change?"), retitle it to name the comparison — never the outcome it used
      to claim — and let the branch print the verdict.
- [ ] **A silent-bail bug class comes in PAIRS — grep the siblings.** When a fix starts passing a
      resolved value (a lock, a session, a repo) into one helper, grep every call site of the bare
      lookup it replaced: the refusal-marker writer one function away had the identical
      `_read_lock(None)` defect, so the state it exists to make visible was never written for
      exactly the sessions that reach it.
- [ ] **A CLASS defect is fixed by a SWEEP, not by the next instance.** When a finding is really a
      rule that must hold at EVERY call site ("anything that drops a lock must first resolve the
      cycle"), enumerating the call sites is the fix: grep each one, fix those that violate it, and
      then pin the rule as a test that FAILS on any NEW call site which omits the paired action.
      Fixing today's instances and walking away leaves the class free to return with the next
      feature — and the reviewer who found it found it by enumeration, not by reading your patch.
      Two properties make the sweep durable: exemptions must be DECLARED in the test with the
      reason the release is already safe there, and each exemption's justifying gate must be
      ASSERTED against the source, so an exemption cannot rot into a false one when the gate moves.
      Expect the sweep to earn its keep immediately — the first run failed on an exemption whose
      claimed gate phrase was wrong, which forced reading the real gate instead of trusting the
      claim. **Place the sweep's action where every path CONVERGES, and pin it with a DYNAMIC test.**
      When the class is a set of EXITS (every branch that finishes the task), wire the paired action
      at the single point they all funnel through rather than at each exit — an exit added later
      then cannot skip it — and drive the decisions with injected collaborators, observing the call,
      because a test that only PARSES the source to prove the call exists verifies no behaviour and
      is filed as scope drift. The source check supplements that test; it never replaces it.
- [ ] **A piped `rc=$?` is the LAST stage's status, so regenerate an artifact rather than
      hand-patching it.** `cmd | tail -1; echo rc=$?` prints the tail's 0, which can put
      `rc=0` directly beneath a failure and read as a contradiction: run the command bare, or
      state in the artifact that the rc shown is the command's own, measured with the pipe
      removed. Piecemeal edits to a generated transcript (a path fix, a number) soon leave
      values that no longer match the command above them — re-run the generator and re-read
      its output; normalize host paths to `~` there, not in the committed copy.
      **The same swallow has two more shapes, and a reviewer files both as swallowed errors.**
      (a) A FALLBACK: `cmd || echo "(none found)"; echo "rc=$?"` prints the ECHO's status, so the
      command's own failure path reports success — capture the status first
      (`cmd; RC=$?`), then print the fallback only when `RC` is non-zero.
      (b) A LOOP: a `for`/`while` body ending in `printf` makes the trailing `rc=$?` printf's, so
      every inner command is unchecked — track the WORST status inside the loop and print THAT,
      and say in the artifact what the number means (`1` = a symbol was absent, `2` = the file
      could not be read). A claim of the form "X started after the deploy" is the same defect in
      prose: make it an assertion that COMPUTES the comparison and carries its own rc, instead of
      a comment sitting beside a timestamp the reader has to interpret.
- [ ] **Point a probe at the copy the artifact is ABOUT — deployed, not repo.** A transcript that
      resolves a store or module through the REPO path while its neighbouring section checks the
      DEPLOYED path proves nothing about what actually runs, and the inconsistency is visible in
      the diff. Pass the deployed path in (an env var such as `MODPATH=<deployed copy>`) and print
      which copy was used, so the two sections cannot disagree silently. When the store the probe
      reads is too large for the execution guard to scan, do not name it by path at all: resolve it
      through the component's own accessor (`mod.LOOP_DB`, the shipped path helper) and open it
      read-only (`sqlite3.connect('file:…?mode=ro', uri=True)`) — the accessor is both the
      sanctioned route and the one that runs, since a script naming a file the guard cannot scan is
      refused execution outright.
- [ ] **Never commit a query's output without first seeing it return rows.** Proof of a
      disposition ("recorded as this issue", "promoted to a task") must be the store's ACTUAL
      row: run the query, confirm it returns the row, then commit that. Commit a traceback or an
      empty section and it proves nothing — and because the reviewer reads the DIFF, a later
      correction of that same passage can keep reading as the broken version. List the store's
      tables before writing the query (`SELECT name FROM sqlite_master WHERE type='table'`):
      store table names are not guessable, and a task store may not be a file DB on the host at
      all — capture what the tool itself returns instead.
- [ ] A test whose verdict depends on WHO invoked it is not a test. A test that
      SPAWNS a process to exercise a component (a server, a CLI, a hook) must
      resolve an interpreter that can actually RUN that component — read it from the
      component's own registration/config — never `sys.executable`, because the
      harness's interpreter usually lacks the component's dependencies: the child
      dies before initialising and the assertion blames the component for the
      harness's choice. Fall back through known-good candidates and FAIL LOUDLY
      when none can run it. Do not hand-roll that candidate list — the fleet ships it as
      `bash ops/scripts/lib/python-with-module.sh <module> <script> [args]` (exit 3 = no
      interpreter can import the module), and the same capability test applies to any
      script that picks its own interpreter (`shell-scripting`).
- [ ] **Ambient environment is the same trap one level up: a test that reads HOME, CWD, or an
      env var another module sets is a test whose verdict depends on who invoked it.** The
      symptom is a test that passes alone and FAILS inside the full suite, where a sibling
      module's `HOME` (or a leaked `CORTEX_*` var) is in effect — and it is easy to misread as
      "my change broke it". Derive paths from the REPO under test (`Path(__file__).parents[1]`)
      or pass them in explicitly; never from the ambient `HOME`/`CORTEX_REPO`. Prove it both
      ways before shipping: run the file alone AND from a foreign directory with a foreign HOME
      (`cd /tmp && HOME=/tmp/fakehome pytest <file>`), then assert the default roots
      STRUCTURALLY (the source names the trees) rather than by a live lookup.
- [ ] When a component cannot RUN because a dependency is missing, INSTALL it (age-gated via
      `ops/scripts/health/check-package-age.py <mgr> <pkg>`) rather than teaching every
      caller to route around it. A workaround fixes the one call site you were looking at
      and leaves the component broken for the next caller — and the missing dependency is
      usually why the failure looked unrelated in the first place. Pin and match a version
      already proven on this fleet.
- [ ] A check that CANNOT RUN is a third outcome — not a pass, not a negative
      result. Give it its own exit code (`3 = could not verify`) and its own message,
      and make every caller dispatch on the code: a gate shaped
      `if ! <check>; then <report the bad thing>; fi` reports a crash AS the bad
      thing, so a host that cannot run the tool is told its artifact is stale.
      Report "cannot check" as exactly that.
- [ ] Test the could-not-verify branch by CONSTRUCTING the failure, never by waiting
      for a host that has it: run the tool with a neutered environment (non-existent
      PATH, HOME and interpreter) and assert the distinct outcome and message. A
      branch exercised only on healthy hosts is untested.
- [ ] A checker that re-implements a GATE's rule must mirror it COMPLETELY — the same
      scope and the same validator — and must never demand an input the gate does not
      require. A check that refuses a case the gate allows is a false alarm, and an alarm
      that fires on a clean run teaches its reader to ignore it; a check that validates a
      WEAKER property than the gate (a verdict string instead of a range binding) passes
      work the gate would refuse. Re-use the gate's own validator rather than writing a
      second copy of the rule — a second, looser implementation is how binding stops
      binding. Before citing the check, run it on a case each way: one the gate allows and
      one it refuses, and assert the distinct outcome AND message for each.
      **Canonicalise what you compare before comparing it**: a short revision never equals
      a full one, so normalise both sides the way the gate does (`git rev-parse`). And when
      an input CANNOT be resolved, return the could-not-verify code rather than an empty
      result — an empty range or empty result reads as "nothing to check" and passes
      silently, which is how a mistyped revision becomes a green tick. The same bite hits a
      CONTENT digest: normalise trailing newlines and whitespace before hashing a file, or a
      byte-identical copy fails the comparison by one `\n` and looks like real drift.
- [ ] **A per-item rule belongs ONLY to the items the checker owns.** A validator that
      loops over a collection (every config entry, every service, every registered host)
      and applies an ownership-specific rule to each — an identity/agent-name convention,
      a schema only its own components satisfy — fails a HEALTHY system the moment a
      legitimate foreign item sits beside its own. Scope the per-item rule to the owned
      set, keep the generic checks (does the command exist, does the path resolve) for
      every item, and REPORT the foreign items as outside the check's scope instead of
      judging them by a contract they never had. Prove all three directions: an owned item
      breaking the rule still fails, a foreign item does not fail, and a foreign item with
      a genuinely broken path still fails — otherwise "scoped" and "disarmed" are
      indistinguishable.
- [ ] A regression test must exercise the DETECTOR, not a live ambient state. A test that
      asserts "the tree is clean" / "the deployed copy matches" / "the queue is empty"
      flaps the moment normal operation dirties it — a pipeline writing a lesson, a peer
      mid-deploy — and a gate that flaps on healthy systems teaches its readers to ignore
      it. Drive the detector with controlled inputs in both directions (one it must report,
      one it must not) and keep the live state out of the assertion.
      **The same rule binds a test of a WRITE tool: never call the real governance writers
      (`begin_change` / `feedback_accept`) against the live store from a test.** Each call
      leaves a real row — an unscored PENDING cycle, which the doctor counts as a FAILURE and
      which therefore blocks the push for every agent on the host until someone finds and
      scores it. Redirect the store to a temp dir and assert what the tool wrote THERE, or test
      the helper the tool delegates to; the leak is invisible because the test still passes.
- [ ] When a heuristic warning is noisy, tighten its TRIGGER — do not add an exemption list.
      A check that cannot tell the case it exists for from a deliberate long-standing state
      fires on every instance of the latter, and the reader learns to scroll past it. Scope
      the condition to the case itself (`git diff --cached --name-only --diff-filter=A` —
      only NEWLY ADDED files), which removes the noise and keeps the real case; an
      allow-list of known-good paths instead drifts out of date and the noise returns with
      the next legitimate tool.
      **Pick the new trigger by MEASUREMENT, once — do not iterate it in the operator's view.**
      Enumerate the candidate signals, count what each would flag on the LIVE corpus in a single pass,
      decide from that output, and record the refuted candidates in the source so nobody re-tries
      them. Repeatedly widening and narrowing a rule across turns reads as churn and spends real
      budget for no extra correctness; the fix is one measured decision, not a faster loop. Reach for
      claim-verification (the artefact says it points at a record — make the record prove it) before
      pattern-matching prose.
- [ ] Test the warning BOTH ways before trusting it: the case it must report, and the case it
      must now stay silent on. A warning verified only in the reporting direction cannot show
      that the noise is gone; verify only in the silent direction and you may have deleted the
      check. (`shell-scripting` has the extraction pattern for driving one block of a large
      script this way; `tests/test_updater_robustness.py` is a worked exemplar.)
- [ ] Evidence must be self-consistent: a summary line may never name a file,
      path or count that the artifact it accompanies does not show. A stat built
      from a wider set than the diff beside it is a contradiction a reviewer will
      (correctly) read as fabrication — cite the range you actually show. **Counts are MEASURED
      in the artifact, never recalled**: a line/file total must be the one the artifact's own
      `wc -l` / `grep -c` printed, at the revision it cites — and NEVER a count read off
      `git show --stat`: it TRUNCATES long paths behind a leading `...`, so a file list taken from
      it is silently SHORT (four paths shown for eight files changed) while looking complete. Use
      `--name-only` whenever the FILE SET is the claim; `--stat` is for shape only. **And name the comparison's exact
      strength** — "identical modulo the deploy banner (N leading lines stripped)", never
      "byte-identical" — because an overclaim the check does not support reads as fabrication
      even when the check passing was real. **And state the property your artifact
      actually shows.** "ONE verdict per server" is refuted by your own evidence the
      moment the transcript prints two lines per server; write the true, narrower
      claim ("no CONTRADICTORY verdicts — the presence line is informational, the
      wiring line judges the interpreter"). An overstated claim sitting beside
      output that contradicts it is filed as fabrication even when the change is
      correct, and a reviewer reading a diff sees the wrong claim first.
- [ ] Maker/checker split — use a different model for verifier vs implementer where quality is critical.
- [ ] Record evidence — finding IDs, boundary inputs, assumptions violated, exit codes. Report "checked X, Y, Z" never "verified clean".

## Phase 2: Multi-OS Compatibility

- [ ] Hardcoded paths → use ${NGINX_DIR}, $HOME/Path.home(), guard /opt/homebrew/ with IS_MAC.
- [ ] OS binaries → systemctl→IS_LINUX; launchctl/brew→IS_MAC; apt/yum/dnf→IS_LINUX.

## Phase 3: Multi-Role Compatibility

- [ ] Process name — pgrep -f cortex-bus misses cortex_bus; check ps aux for the real argv.
- [ ] Hook/enforcer changes — test in a throwaway project repo (git init /tmp/hook-test, set core.hooksPath), since hooks fire in every repo on the host. Confirm fail-closed still blocks.
- [ ] Role matrix — Titus (macOS, no systemd/nginx, many project repos) / Joseph (Linux full stack) / Esther (Linux + orch crons) / Kustos (stricter perms, handle PermissionError). Verify none are broken.
- [ ] Non-orchestrators — no cronjob tool (request via inbox); new crons registered in the install scripts. Message audit: would a non-orchestrator read an output line and try to install an orchestrator-only service? Gate or rephrase.

## Phase 4: Documentation

- [ ] **Never document or print a command you have not executed.** Fix text, runbooks
      and changelogs are instructions an operator or another agent runs verbatim:
      check the subcommand against the tool itself (`<tool> --help`) in the same
      cycle that adds it. A plausible-but-nonexistent subcommand sends every reader
      into a dead end and discredits the rest of the doc — verify the WHOLE command,
      including which tool owns the subcommand.
      **A CHECK that prints a fix command is held to the same rule.** A doctor/watchdog
      finding carries `Fix: …` text that a reader (or another agent) pastes verbatim, so a
      wrong path there is an unrunnable instruction shipped by the very check that exists to
      catch problems: verify the printed command's paths RESOLVE and its flags exist, and
      pin it with a test that asserts the rendered fix names a path that exists. The same
      applies to a suggested action that is a decision (delete this file, add this block) —
      confirm the subject is what the check claims it is before printing the action.
- [ ] New script → register in cortex-update.sh; cron → add to install script.
- [ ] New skill → SKILL.md + docs/skills-manifest-reference.md if auto-loaded.
- [ ] Path restructure → fix live refs, update ~/.hermes/config.yaml, add compat symlinks, update repo-organization.
- [ ] Agent workflow change → update AGENTS.md / SOUL.md. Doc audit: grep -rn "<feature>" AGENTS.md docs/agent-onboarding.md — zero matches = undocumented.

## Phase 5: Final Verification

- [ ] No dangling leftovers — DECIDE, do not defer. A leftover (uncommitted files, an
      unregistered tool, a stale artifact, an unresolved finding) ends either LANDED or
      with a stated decision backed by a measurement — how many instances already share
      the state, what the alternative costs, what the tool reports. "It is not mine" is a
      description of ownership, an input to the decision, never a resting state: an
      unexamined leftover is exactly what the user has to come back for. Never land a
      peer's IN-FLIGHT edits to satisfy this — decide about them, or report them by path.
      An uncommitted `skills/` (or docs) edit is NOT automatically a leftover to discard:
      content authored on the DEPLOYED copy and never copied back is a STRANDED lesson,
      invisible to the fleet because the deploy's guardrail refuses to overwrite it. Decide
      the direction by CONTENT, never by mtime or `git checkout --`: run
      `python3 ops/scripts/manage/check-skill-drift-parity.py`, then diff repo against the
      deployed copy with the deploy header stripped, and take the deployed side only where
      it is a superset (pure additions, no deletions of repo content).
      **Land the deployed content as its OWN commit BEFORE adding your own.** The detector
      calls a file stranded when its deployed content appears in NO committed revision, so a
      single commit that copies it back AND adds to it leaves the deployed bytes in no
      revision at all — the file stays stranded and the fleet still never receives it.
      Commit the byte-identical deployed content first, then your addition on top; the file
      then reads "repo ahead", which is normal and unreported. Reconcile with
      `python3 ops/scripts/manage/reconcile-stranded-skills.py` — report by default, `--apply`
      copies only the pure-superset class and prints the dropped lines for the rewrite class,
      which needs a decision — rather than copying the file by hand.
      **A file the tool marks REVIEW is not automatically a keep-the-repo case.** The tool's
      `would drop N line(s)` counts REPO-only lines — the side at risk — so diff BOTH
      directions and check each such line's CONTENT in the deployed copy by PHRASE, not line
      by line: a paragraph that was rewritten or condensed drops lines that are still present
      in another form, and a stale claim the newer copy deliberately removed must not be
      merged back. Hand-merge only where the deployed copy genuinely lacks the content. A
      mechanical ratio over whole lines is not enough to decide (a reflowed paragraph scores
      low while losing nothing); grep the deployed copy for the distinctive phrase instead.
      **Collapse whitespace before you search, or the probe invents the loss it reports.** A
      paragraph that was REWRAPPED keeps every word while every line differs, so a
      line-by-line "is this repo line present in the deployed copy?" check flags all of it as
      missing — read the deletion hunks with `difflib` and match phrases against the
      whitespace-collapsed TEXT of both sides. Then decide per hunk, and expect the answer to
      be "superseded in place": a newer copy that CORRECTS a wrong claim (say, which call
      refreshes a heartbeat) must be landed as-is, and merging the old wording back restores
      the error. Land by copying the deployed file over the repo copy and ASSERTING the sha256
      on both sides (`shutil.copy2` + equality check, or the reconciler's `--apply` for the
      superset class) — never retype content by hand.
      **This is routine maintenance, not a one-off, so do not read a repeat as failure.** The
      lesson pipeline writes to the DEPLOYED copies continuously: a reconciliation can finish
      with 0 stranded and the same file reads stranded again within the hour. Re-run
      `python3 ops/scripts/manage/reconcile-stranded-skills.py` on a schedule (report first;
      `--apply` only ever touches the pure-superset class).
- [ ] Symptom proof — the specific error/alert/blocker is gone (not just code compiles + doctor passes). Show evidence in the cycle note.
- [ ] Stale expected-list cleanup — removed crons also removed from uninstall arrays (doctor reads them as expected list).
- [ ] Stale bus/state cleanup — delete test bus messages and stale state-file entries before end_change().
- [ ] Doctor clean — python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet
      (✅ Crons registered / Orch crons / Crons total). Record its EXIT CODE and warning count,
      not just the ✅ lines: a non-zero rc with warnings is NOT a clean doctor, and reporting it
      as one is the failure the close review catches.
      **Warnings and info are not a licence to move on.** The doctor prints `N undisposed` and
      names each warning/info check nobody has decided about. For each: fix it, or record the
      decision (`cortex-doctor.py --disposition "<check>" --as deferred|deliberate --owner <you>
      --reason "<why>"`) — and put the counts in the delivery, never a bare "pre-existing".
      "Pre-existing" is not a disposition: the tool decides what counts as known, a disposition
      expires (30 days) and returns as STALE, and `--as fixed` is refused while the check still
      warns. Nothing gates on this — it exists so that deferring is a visible decision instead of
      a silent wave-through.
- [ ] Governance scored — feedback_accept() before end_change(). **When the close is driven by a
      retry loop (a wide range closes over several rounds), SCORE BEFORE STARTING THAT LOOP.**
      Launching it in the same turn as `feedback_accept` races: the rounds execute first and each
      refuses instantly with "this task's cycle is NOT scored", so the loop spends every attempt on
      the race instead of the review. Score, then launch — and note the record cannot settle the
      ordering afterwards, because a cycle row's `timestamp` is its CREATION time (the scoring
      UPDATE does not touch it).
- [ ] **Commit the EVIDENCE artifact BEFORE you close — never after the refusal.** The close
      reviewer reads the DIFF, not your close note: any load-bearing claim that lives only in
      the note ("6 passed", "A4 GATE_PASSED", "no peer locks exist", "the push succeeded") is
      filed as unverified-claim and REFUSES the close, every time — measured three times in a
      single session, each refusal costing a full re-review. So run the checks, capture their
      real output (each command beside its own exit code, measured unpiped) into
      `docs/evidence/`, and commit that artifact in the SAME cycle that makes the change; then
      write the note as a pointer to it. A refusal of this kind is not a technical failure to
      argue with — commit the proof and call `rereview_change`.
      **This binds a READ-ONLY / DIAGNOSTIC cycle hardest, because the diff is EMPTY.** A
      measurement task (a thermal probe, a latency sample, a queue audit) changes no files, so
      the reviewer has nothing to read but your prose and files every number in it as
      unverified-claim; the remedy it names is the RAW LOG. So commit the generator's transcript
      UNMODIFIED — byte-identical md5 against the run's own output, never retyped from memory,
      never hand-patched — under `docs/evidence/` in the same cycle, and say in the note what
      produced it. A `docs/evidence/` path is not a deploy-map file, so it needs no deploy and
      cannot block the push; the same does NOT hold for a probe you had to add under `ops/scripts/`.
      Never cite a number from an earlier live run you did not save: that claim is unverifiable
      however real the run was — re-run the generator, or withdraw the figure.
      **A transcript written to a GITIGNORED path is not evidence either.** Check the destination
      before committing it: a runner that emits under `tests/artifacts/` (ignored) writes a file no
      reviewer can read in the repo, so the run happened and the claim stays unverifiable. Copy the
      capture into `docs/evidence/` with a header naming the command, the tip revision and how to
      re-run it, then cite that path — and leave the ignore rule alone rather than force-adding a
      generated tree. Print the same generator's verdict line into the capture (the last line of its
      own output plus its `rc`), so the thin file still carries the outcome a reader needs.
- [ ] Cron-governance compat — if hooks/plugins/enforcer changed, verify the cycle works in a test cron session, then delete it.
- [ ] Deploy, THEN push — that order, with nothing committed in between. The pre-push path
      itself runs pull → deploy → doctor → verify, and the gate reads `Deploy sync`, so a
      commit that changes a DEPLOY-MAP file after a deploy leaves the deployed tree trailing HEAD
      and blocks the push. **The check is scoped to the deploy-map files the range changes**, so a
      commit after the deploy that touches only non-deployed paths (an `docs/evidence/` artifact,
      a regenerated report, a skill already landed by the reconciler) does NOT block the push and
      does NOT need another deploy — re-deploying for it multiplies deploy windows on a shared
      tree for no gain. Confirm which side you are on before deploying again: the gate names the
      undeployed file when it does refuse.
      Run it as one step: `bash ~/.hermes-cortex/scripts/cortex-dogfood.sh --force` and then
      `git push origin main`. A close-time review receipt is bound to the
      RANGE, and the gate accepts it when the receipt's reviewed blobs COVER every blob that
      range changes — so a rebase that rewrites the tip of identical content no longer
      invalidates a review of that content (a tip-equality rule is exactly what a shared
      checkout breaks). A further COMMIT that adds unreviewed content still invalidates it:
      the deploy is the LAST step, not a mid-task refresh. The Deploy-sync check is scoped the
      same way — compare only the deploy-map files changed in the range, so a peer's unrelated
      commit cannot block your push, while an undeployed deploy-map file still FAILs and is named.
- [ ] Integrate a peer's work by MERGE, never `git pull --rebase`. A rebase rewrites the
      peer's unpushed commits and their authorship, and it refuses outright when another
      session holds unstaged files — which you must never stash. A merge needs neither and
      keeps every commit identity on the shared branch.
- [ ] **Scope every gate that runs on a shared checkout to CONTENT, not to the tip.** Two
      gates were tip-coupled and each blocked a push whose content was in fact fine: the
      review receipt (bound to tip+base) and the Deploy-sync check (keyed on the revision
      alone). Both now compare what the range CHANGES — receipt blobs, and the deploy-map
      files touched in the range — with ONE shared implementation of the rule
      (`review-receipt-check.py`) called by the hook, the verifier and the tests. Coverage,
      not equality: a range that GAINED an unreviewed file must still refuse, and a receipt
      with no blob list is only ever accepted by exact tip+base. A peer commit landing inside
      the pushed range is genuinely unreviewed and still refuses — correct, not a bug to widen
      away.
- [ ] **Never `git commit --amend` while a peer may be working in the tree.** `--amend`
      rewrites whatever HEAD is *now*, not "your" commit: a sibling commit that landed since
      you started becomes the target, folding THEIR files into YOUR message and stripping
      their authorship. Before amending, assert HEAD is the commit you created
      (`git log -1 --format='%h %s'`); if it is not, commit your paths as a NEW commit.
      Recovery if you already amended theirs: `git reflog` to find the peer's SHA,
      `git reset --soft <peer-sha>` to restore it verbatim (message and all files), then
      re-commit only your staged paths — never `reset --hard`, which discards their work.
      **Never reuse a previous commit's message file for a different commit.** It records work the
      diff does not contain, and an inaccurate commit record is worse than a stale one because the
      next reader trusts it: an operator reading that message would believe a fix landed that never
      was written. Write the message from the actual diff — and when it is already wrong, correct
      it by amending while HEAD is verified as yours, not by explaining the discrepancy later.
- [ ] **A plain `git commit` commits the WHOLE index — a peer's already-STAGED files ride into
      your commit.** `git add <your paths>` does not unstage theirs, so the commit captures
      whatever is staged at that moment, under YOUR message and authorship. Commit by
      pathspec every time — `git commit -F <msgfile> -- <your paths...>` — and assert the set
      first with `git diff --cached --name-only`. **Then compare that printed set against the
      pathspec you are about to type — the two drift in the OTHER direction too.** A file you
      staged but left out of the pathspec silently stays staged: the cycle's reviewed range is
      missing a file the change claims, and it lands in the NEXT commit under a message that
      does not mention it. When that happens, commit it in its own correctly-described commit
      (and say so in the message) — never paper over it with prose later. Two mechanics that
      bite in the same step: `git add a b` where one path is gitignored (even when the file is
      TRACKED and `git status` shows it modified) exits non-zero, so do not assume the rest of
      the batch landed — stage it alone with `-f`. Recovery if a wrong set already landed:
      `git reset --soft HEAD~1` (keeps every file and the message), then re-commit with the
      pathspec. Never `reset --hard`, and never unstage or discard a peer's paths to tidy up:
      their staged work is theirs to land.
- [ ] A close-review window is `base..HEAD`, so a **peer's commit landing mid-cycle shows up
      as scope drift in YOUR range**. Name the peer's SHA in the cycle note and leave their
      work untouched; reverting another session's commit to green your gate is the same
      violation as the amend above.
- [ ] Verify the landing rather than assuming it: `python3 ops/scripts/manage/verify-landed.py
      --repo . --base <previous tip>` asserts a CLEAN receipt for the tip, that every changed
      deploy-map file matches its deployed copy, and that `origin/<branch>` equals the tip.
      Exit 0 / 1 (a real mismatch, named) / 2 COULD NOT VERIFY — a partial check is not a pass.
- [ ] **Ship the automation and its evidence INSIDE the repo — a host-local script, a cron job, or a
      session transcript is not a deliverable.** Verification that lives only in the deploy dir, a
      state dir, or the operator's chat cannot be read or re-run by the next agent or the close
      reviewer, which correctly files it as an unverified claim and refuses the close. Put the
      reusable logic in a registered script (deploy-map entry + a hermetic case in a `tests/` runner
      that actually executes it), keep only the host-specific values in a thin `local-`-prefixed
      wrapper, and commit the measured transcripts (each command beside its real output, with exit
      code and warning count) under `docs/evidence/`. When the work is a watcher for a deferred
      landing, commit its contract too — the automation has to outlive the session that wrote it.
- [ ] Pushed — `git log --oneline -1 origin/main` shows your commit.
      **Load `shared-repo-push-gates` BEFORE the FIRST push attempt of a session, not after
      the first refusal.** It already carries the command-shape rule (the carve-out accepts
      only a bare `git push`) and the orphaned-PENDING-cycle recovery, and both are reachable
      only from that skill — diagnosing a refusal from scratch re-derives rules that were
      already written down, and costs the cycles the rule exists to save.
- [ ] Cron delivery audit — deliver goes somewhere visible (origin/local deliver nowhere from scripts).
- [ ] Timeout audit — deadline ≈ 3× expected worst-case completion.

## Phase 6: Reflexion

Run reflexion-check (7 questions). Score HIGH/MEDIUM/LOW/ZERO. MEDIUM → disclose; LOW/ZERO → fix before delivering. Ask: "What is the most likely thing I got wrong?" (Mandatory for multi-file/service/config changes; 10s mental pass for trivial ones.)

## Anti-Patterns
"I tested it manually" · "agents won't see that message" · "the rest is trivial" · "other OS can wait" · "docs later" · "the hook didn't catch it" · "I'll write a migration script" (the commit IS the migration) · "long sleep" (poll short intervals) · "worked from my repo terminal" (test from the deployed path — Path("") from an unset env var is the classic cron crash).

## Path Patterns by OS

| Purpose | Linux | macOS (arm64) | macOS (x86_64) |
|---------|-------|---------------|----------------|
| nginx config dir | /etc/nginx | /opt/homebrew/etc/nginx | /usr/local/etc/nginx |
| nginx sites dir | sites-available/ | servers/ | servers/ |
| htpasswd file | .hermes-htpasswd | .htpasswd | .htpasswd |
| nginx log dir | /var/log/nginx | /opt/homebrew/var/log/nginx | /usr/local/var/log/nginx |
| Service manager | systemctl --user | launchctl | launchctl |
| Package manager | apt/yum/dnf | brew | brew |
