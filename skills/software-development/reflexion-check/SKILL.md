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

### 3. Did I follow governance for every change?
Every file created/modified: `begin_change` → work → `feedback_accept` → `end_change`, all scored, no orphans. If NO: score the missing cycle or confess the gap.

### 4. Did I handle all edge cases and failure paths?
Error path, empty state, malformed input, sibling call sites for the same bug. If NO: state the gaps honestly.

**Probe the gate itself.** Point the checker at input it must reject and show it failing non-zero — a green run proves the thing works, only a demonstrated failure proves the check would NOTICE a broken one. And probe the PROBE: when a check fails, verify its own assumptions before blaming the artifact (a validator with no parser, a test target that does not exist, a path that does not resolve, a test FILTER that matches nothing — an `--exact` name needs its full path, so a bare name reports `0 passed, N filtered out` and reads like a missing test) — a failure for the wrong reason is not a finding. Fixing a warning by silencing it weakens the guard; verify both directions instead (exempt what should be exempt, still fire on what should fire).

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
