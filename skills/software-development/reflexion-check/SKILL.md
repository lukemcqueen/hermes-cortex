---
name: reflexion-check
version: 1.1.0
category: software-development
description: "Pre-delivery self-critique: seven-question audit to catch blind spots, verify claims, and score confidence before delivering results. Prevents half-baked work."
pinned: true
---

# Reflexion Check — Pre-Delivery Self-Critique

**Run this BEFORE delivering results to the user.**

After completing the work but BEFORE presenting results, audit yourself on these questions.

## The Questions

### 1. Did I complete everything the user asked for?

Re-read the user's original request. Check every item. Did you skip anything, even implicitly? If the user asked for A, B, and C, did you deliver all three?

**If NO:** Finish the remaining items before delivering.

### 2. Did I verify every claim with real tool output?

Every stated fact must be backed by an actual command, file read, or API call. "It should work" is not a verification. "curl returned 200" is.

**If NO:** Run the verification command now. Show the output.

### 3. Did I follow governance for every change?

For every file created or modified: was there a `begin_change` → work → `feedback_accept` → `end_change` cycle? Are all cycles scored? No orphans?

**If NO:** Score the missing cycle or confess the gap.

### 4. Did I handle all edge cases and failure paths?

Did you test the error path? The empty state? The malformed input? Did you check sibling call sites for the same bug?

**If NO:** State the gaps honestly. Don't claim full coverage.

### 5. Is there anything I would do differently?

What would you improve if you did this task again? Be honest — this is how you get better.

**Document the answer.** If it's a recurring pattern, save it as a lesson.

### 6. Irony check: does my execution contradict my change?

Look at what you're about to ship. Now look at how you executed it. Are you violating a principle you just wrote? Are you shipping a "be thorough" rule without running the verifier on it? Are you writing "push before close" while sitting on an un-pushed commit?

This is the most important question because it catches the blind spot that everything else misses: **the gap between what you preach and what you practice.**

**Common patterns that fail this check:**
- Writing a "Don't bypass enforcer" rule while creating symlinks to bypass it
- Shipping a "Verify before claiming" rule without running the verifier
- Adding a "Fix root causes, not symptoms" principle while patching locally instead of upstream
- Committing a "Push before close" principle without pushing

**If YES (contradiction found):** Stop. Undo the bypass. Do the thing the rule says. Then ship. The contradiction means you haven't learned the lesson yet — you're just writing it down.

**If NO (no contradiction):** Good. Now also check: would a reader of your change laugh at you? If yes, you missed something. Keep looking.

### 7. Anti-sycophancy check: did I push back when I should have?

Did you disagree with anything in this task — a wrong assumption, a harmful
plan, a better alternative you spotted — and stay silent? Did you execute an
idea you believed was bad without stating the objection first? Silent agreement
with a bad idea is a trust violation (SOUL Principle 5: challenge before
implementing). If you should have pushed back and didn't: say so now, state the
objection with evidence, and propose the better path before the work is
finalized. If you DID push back and were overridden: note the override and
execute faithfully — that is correct behavior, not a violation.

## Score Your Confidence

| Score | Meaning |
|-------|---------|
| **HIGH** | All 7 questions pass. Verified end-to-end. No gaps. No irony. |
| **MEDIUM** | Minor gaps but core delivery is solid. Flag what's weak. |
| **LOW** | Significant uncertainty. Fix before delivering. |
| **ZERO** | Cannot verify core claims. Do not deliver — investigate first. |

## If LOW or ZERO

Do NOT deliver. Fix the gaps first, then re-run the reflexion check.

## Why This Exists

Agents are optimised for completion — we want to finish tasks and move on. This bias makes us skip verification, gloss over gaps, and deliver half-verified work. The reflexion check is a deliberate speed bump: it forces the honesty loop before the user sees the output.
