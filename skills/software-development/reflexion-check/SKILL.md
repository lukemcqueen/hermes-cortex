---
name: reflexion-check
version: 1.0.0
category: software-development
description: "Pre-delivery self-critique: five-question audit to catch blind spots, verify claims, and score confidence before delivering results. Prevents half-baked work."
pinned: true
---

# Reflexion Check — Pre-Delivery Self-Critique

**Run this BEFORE delivering results to the user.**

After completing the work but BEFORE presenting results, audit yourself on these five questions.

## The Five Questions

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

## Score Your Confidence

| Score | Meaning |
|-------|---------|
| **HIGH** | All 5 questions pass. Verified end-to-end. No gaps. |
| **MEDIUM** | Minor gaps but core delivery is solid. Flag what's weak. |
| **LOW** | Significant uncertainty. Fix before delivering. |
| **ZERO** | Cannot verify core claims. Do not deliver — investigate first. |

## If LOW or ZERO

Do NOT deliver. Fix the gaps first, then re-run the reflexion check.

## Why This Exists

Agents are optimised for completion — we want to finish tasks and move on. This bias makes us skip verification, gloss over gaps, and deliver half-verified work. The reflexion check is a deliberate speed bump: it forces the honesty loop before the user sees the output.
