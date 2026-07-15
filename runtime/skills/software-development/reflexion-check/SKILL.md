---
name: reflexion-check
version: 1.0.0
category: software-development
description: >
  Universal self-critique protocol for agents. Before declaring any task
  done, review your own work as if you were a senior engineer: check
  blind spots, verify claims, assess completeness, score confidence.
  Pair with PEV for rigorous quality assurance.
tags: [reflexion, self-critique, quality, review, audit, verification, confidence]
related_skills: [reasoning-patterns, change-checklist, agent-contract, code-review, survey-before-action]
---

# Reflexion Check — Self-Critique Protocol

## When to Load This Skill

**Always.** Load this skill before declaring any task complete. The
reflexion check is the last gate before presenting results.

Specifically:
- After implementing code, before showing the user
- After writing documentation, before delivering
- After debugging, before presenting the fix
- After researching, before presenting findings
- **After change-checklist, before end_change()**

## The Protocol

### Step 1: Take the Reviewer Role

Mentally shift from "builder" to "reviewer." Ask:

> *"If I were a senior engineer seeing this for the first time, what would I question?"*

The builder is optimistic. The reviewer is skeptical. You need both.

### Step 2: The Five-Question Audit

Answer each question honestly — out loud in your reasoning:

**1. COMPLETENESS — "Did I actually do everything I said I did?"**
- Did I verify each claim with a tool call, or did I assume?
- Did I read the actual output, or just the first few lines?
- Are there any TODOs, stubs, or placeholders I left behind?

**2. CORRECTNESS — "Is my reasoning valid?"**
- Did I jump to any conclusions without evidence?
- Did I conflate correlation with causation?
- Did I check the right things, or what was easiest to check?
- Is there a simpler explanation I dismissed too quickly?

**3. EDGE CASES — "What happens when things go wrong?"**
- Did I handle empty/null/missing inputs?
- Did I handle network failures, timeouts, and malformed data?
- Did I handle permission errors, missing files, and race conditions?
- Did I handle the "what if the user does X unexpectedly" case?

**4. SIDE EFFECTS — "What else did I change?"**
- Did I check for unintended changes (diff review)?
- Did I check for hidden dependencies (other callers, other configs)?
- Did I check that I didn't break anything outside my scope?
- Did I check the full test suite, not just the one test I wrote?

**5. EVIDENCE — "Can I prove every claim?"**
- For each claim in my response: what tool call produced the evidence?
- Did I cite sources for researched claims?
- Did I distinguish between verified facts and informed opinions?

### Step 3: Score Your Confidence

| Score | Meaning | Required action |
|-------|---------|-----------------|
| **HIGH** | No concerns found. All claims verified. Edge cases handled. | Deliver result. |
| **MEDIUM** | Minor concerns found but mitigated. One area of uncertainty. | Disclose uncertainty in response. |
| **LOW** | Significant concerns. Unable to verify key claim. Edge case unhandled. | Do not deliver. Go back and fix before presenting. |
| **ZERO** | Cannot vouch for any of the work. | Start over or escalate to user. |

### Step 4: Act on the Score

**If HIGH:**
- Deliver result with confidence stated
- One-sentence summary of what was done

**If MEDIUM:**
- Deliver result
- State the uncertainty explicitly: "I'm confident about X, but Y should be double-checked because..."
- Suggest what to verify

**If LOW:**
- Do NOT deliver yet
- Identify the specific gap
- Go back and fix it
- Re-run the reflexion check after fixing
- If still LOW after fixing, escalate to user

**If ZERO:**
- Do NOT deliver
- State honestly: "I cannot vouch for this work. Here's why..."
- Ask for guidance or a different approach

### Step 5: The Blunder Check

One final question before delivering:

> *"What is the most likely thing I got wrong?"*

If you can answer this honestly, you've done your reflexion. If you can't,
you haven't looked hard enough.

## Pattern-Specific Checklists

### For Code Changes

- [ ] Does the code compile/parse without errors?
- [ ] Did I test the exact code paths that changed (not just the happy path)?
- [ ] Did I check for regressions in the full test suite?
- [ ] Is there a test for each new function?
- [ ] Are error-handling paths also tested?
- [ ] Did I check for hardcoded values, secrets, or credentials?
- [ ] Did I check the diff for unintended changes?
- [ ] Does the code follow the project's existing patterns?

### For Documentation

- [ ] Did I verify each code example works (not "should work" — actually ran it)?
- [ ] Did I check for broken links?
- [ ] Is the tone consistent with existing docs?
- [ ] Are there actionable steps (not just concepts)?
- [ ] Does the doc match the current state of the code?

### For Debugging

- [ ] Did I build a feedback loop BEFORE theorizing?
- [ ] Did I reproduce the bug before fixing it?
- [ ] Did I verify the fix resolves the original (unminimised) scenario?
- [ ] Did I check for other occurrences of the same bug pattern?
- [ ] Did I remove all debug instrumentation?
- [ ] Did I save the fix as a lesson?

### For Research

- [ ] Are my sources cited (URL, document reference)?
- [ ] Did I check multiple sources for critical claims?
- [ ] Did I distinguish established fact from opinion/best practice?
- [ ] Did I note remaining unknowns or uncertainties?
- [ ] Is the answer actionable, or does it need more investigation?

## Anti-Patterns

| Anti-pattern | Why it's wrong |
|-------------|----------------|
| "I'm sure it's fine" without checking | Confidence without evidence is faith, not certainty |
| "I'll just deliver and they'll tell me if something's wrong" | Shifts verification burden to the user |
| "I checked the first few lines of output" | The error might be on line 50 |
| "It compiled, so it must work" | Compilation ≠ correctness |
| "I tested it manually" | Manual ≠ repeatable. Can't prove later |
| "Reflexion takes too long" | A 2-minute reflexion can prevent a 2-hour debugging session |
| "I already reviewed it in my head" | Writing it down makes it concrete. Write the reflexion. |

## Quick Reference Card

```
BEFORE DELIVERING:
1. Step into reviewer role
2. Five-question audit (Completeness, Correctness, Edge Cases, Side Effects, Evidence)
3. Score confidence (HIGH / MEDIUM / LOW / ZERO)
4. Act on score (deliver, disclose, fix, or escalate)
5. Blunder check ("What did I most likely get wrong?")
```
