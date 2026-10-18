---
name: reflexion-check
version: 1.3.0
category: software-development
description: "Pre-delivery self-critique: eight-question audit to catch blind spots, verify claims, keep the operator informed, and score confidence before delivering results. Prevents half-baked work."
pinned: true
---

# Reflexion Check — Pre-Delivery Self-Critique

Run this BEFORE delivering results. Audit yourself on all eight questions.

## The Questions

### 1. Did I complete everything the user asked for?
Re-read the original request and check every item — including implicit ones. If NO: finish before delivering.

### 2. Did I verify every claim with real tool output?
Every stated fact must be backed by an actual command, file read, or API call. "It should work" is not verification; "curl returned 200" is. If NO: run the verification now and show the output.

**A claim that a suite passes, a script gates, or a check works is a claim about a RUN — commit the run.** A re-runnable script plus its captured output; test SOURCE existing proves tests were written, not that they pass, and a reader cannot re-run your terminal. Capture a status yourself rather than inheriting one from a filter (`cmd | tail` prints tail's), and measure numbers (sizes, RSS) rather than quoting an estimate someone else supplied.

**Name the BUILD, not just the run.** A demonstration that invokes a compiled artifact measures the last build of it, not the source: `cargo test` builds the DEBUG profile, so a demo running `target/release/<bin>` exercises pre-change code and reports the new behaviour as ABSENT — which reads exactly like the feature being unwired. Rebuild the exact artifact you are about to demonstrate, because a green suite and a current binary are two different proofs. The same trap exists wherever an installed copy stands in for the tree: a console-script, a deployed duplicate, a cached module.

**A claim about a guard is verified AT the guard, never inferred from the caller.** Reading the mechanism in one place and concluding the consequence in another is how false defect reports happen: the check that already handles the case typically sits a few lines from the code you read — an empty-list exclusion, a raise at the leaf, a condition in the consumer. Before saying a path FAILS OPEN (or that a fix works), open the function that DECIDES and quote what it returns for the exact input you claim is mishandled; a fail-open claim is only reportable against the deciding set, and a portability claim against the branch the host actually takes. A defect report you have to retract costs more than the check would have: every other claim you made in the same breath gets re-read as unverified too.

**Cite evidence the reader can REACH — a path they can open, never the name of a sibling.** A claim made in one artifact must carry its proof IN that artifact, or a pointer the reader can resolve (a committed transcript, a file path plus the symbol). "The test that proves this lives in another file of the same change" is not evidence: the reader cannot see it, so it refuses the artifact and asks for the proof again — and answering by editing the sibling buys a fresh artifact, not a new fact. Know the taste of this loop: a claim refused once for missing evidence is refused identically on every retry, so a fix must add the proof or its pointer to the artifact that MAKES the claim (or make the other file's relevant lines visible to the reader).

**A runner missing HERE is a problem to SOLVE before it is a claim to soften: install it.** "The suite cannot be run on this host" is almost never true — it means the interpreter you happened to invoke lacks the package, and reporting that as a finding rather than fixing it is the shortcut an operator will (rightly) ask you about. Install the runner into an **isolated venv**, never the runtime interpreter the harness itself imports, age-check the package first where the repo mandates it, and run the suite: one install converts an unverifiable claim into an observed result. Verify the run with the venv's own python (`<venv>/bin/python -m pytest`), and when a harness resolves the venv for you, resolve the PYTHON and not the console script — the command shape is `<interpreter> -m <tool>`, so returning the script silently runs `<tool> -m <tool>` and collects nothing.

**Only when the runner genuinely cannot execute HERE, verify the SUBSTANCE by another route and say which route you used.** Read the shipped artifact directly — parse it and assert the value or branch you claim (an extracted constant beats a quoted line), exercise the path with stubs, or cite a committed transcript of a run made elsewhere. Then label it: checked by reading the shipped source, the suite itself did NOT run here — never report that as a passing suite. A green claim you did not observe is the one error that gets every other claim in the same delivery discounted.

Recipes for the shapes above — substance-read, active-vs-repo path check, exception-type assertions, identity-not-count, pinning a deliberate default — are in `references/evidence-recipes.md`.

### 3. Did I follow governance for every change?
Every file created/modified: `begin_change` → work → `feedback_accept` → `end_change`, all scored, no orphans. If NO: score the missing cycle or confess the gap.

### 4. Did I handle all edge cases and failure paths?
Error path, empty state, malformed input, sibling call sites for the same bug. If NO: state the gaps honestly.

**Probe the gate itself.** Point the checker at input it must reject and show it failing non-zero — a green run proves the thing works, only a demonstrated failure proves the check would NOTICE a broken one. And probe the PROBE: when a check fails, verify its own assumptions before blaming the artifact (a validator with no parser, a test target that does not exist, a path that does not resolve, a test FILTER that matches nothing — an `--exact` name needs its full path, so a bare name reports `0 passed, N filtered out` and reads like a missing test) — a failure for the wrong reason is not a finding. **A shim that does not SHADOW the real binary is the same error in a portability proof**: to exercise a macOS fallback on a Linux host you put `gtimeout` on PATH and expect the `timeout` lookup to miss, but if the real `timeout` still resolves, the branch that ran is the one you meant to avoid — and the run looks like a pass. Assert the shadowing itself (`command -v <tool>` prints nothing) and record that check in the same transcript, or the proof is about the wrong branch. Fixing a warning by silencing it weakens the guard; verify both directions instead (exempt what should be exempt, still fire on what should fire).

**A failure is only a finding once you know the check RAN — run a test file with the runner it was written for.** A pytest-style file (it defines `def test_` functions) that also carries a legacy `__main__` block FAILS when executed directly — it needs fixtures, or its inline runner is stale — while its suite passes under pytest; a file with no test functions at all is a SCRIPT whose direct exit code IS its result. A harness that executes every file the same way therefore reports phantom failures, and "pre-existing failure" is the most expensive label to get wrong: it spawns a worktree comparison, a recorded issue, and a script that "proves" the claim by showing two revisions failing for the same environmental reason. Separate THREE outcomes before attributing anything — PASS, FAIL, and NOT RUN (no runner available, or nothing collected) — because a file that ran nothing proves nothing in either direction, and two of the three look identical in a bare exit code.

**A source-level probe must match the CONSTRUCT, never a bare literal.** A search for the string the bug involves also matches the docstring or comment that explains that bug, so the probe reports the explanation as the defect: `find('reviewer_text[:2000]')` hit the docstring quoting it, a line-based scan rejected a legitimately wrapped call, an assertion forbade the redacted value it was asking for, and a regex offset invented a character difference. Match a fragment WITH its neighbouring tokens (`(reviewer_text[:2000] + _ref_note)`), or parse instead of grepping. **Then count the probes that were the bug:** two or more in one session means the probe is no longer evidence — stop refining the assertion and exercise the real path instead (run the tool, read its output).

### 5. Is there anything I would do differently?
Document it; if recurring, save as a lesson.

### 6. Irony check: does my execution contradict my change?
Are you shipping a "be thorough" rule without running the verifier on it? Writing "push before close" while sitting on an un-pushed commit? This catches the gap between what you preach and what you practice.

If a contradiction is found: undo the bypass, do what the rule says, then ship. If none: would a reader of your change laugh at you? Keep looking until the answer is no.

### 7. Anti-sycophancy check: did I push back when I should have?
Silent agreement with a bad idea is a trust violation (SOUL Principle 5). If you should have pushed back and didn't: state the objection with evidence now. If you pushed back and were overridden: note the override and execute faithfully — that is correct behavior.

### 8. Visibility check: did the operator see progress during a long run?
A long stretch of work with no interim report is indistinguishable from a stall
(the operator asked "What are you doing for 45 min?" mid-session). For any run
that will exceed a few minutes — especially one waiting on a background process,
a deploy, or a test suite — send a short progress line at each phase boundary,
not just at the end. If the turn already went silent for long, answer the
question directly first, then resume.

## Score Your Confidence

| Score | Meaning |
|-------|---------|
| **HIGH** | All 8 pass. Verified end-to-end. |
| **MEDIUM** | Minor gaps; flag what's weak. |
| **LOW** | Significant uncertainty — fix before delivering. |
| **ZERO** | Cannot verify core claims — investigate, do not deliver. |

If LOW or ZERO: do not deliver. Fix the gaps, then re-run this check.
