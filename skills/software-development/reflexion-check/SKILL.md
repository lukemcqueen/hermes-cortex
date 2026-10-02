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

### 3. Did I follow governance for every change?
Every file created/modified: `begin_change` → work → `feedback_accept` → `end_change`, all scored, no orphans. If NO: score the missing cycle or confess the gap.

### 4. Did I handle all edge cases and failure paths?
Error path, empty state, malformed input, sibling call sites for the same bug. If NO: state the gaps honestly.

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
