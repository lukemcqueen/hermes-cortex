---
name: reasoning-patterns
version: 1.0.0
category: software-development
description: >
  Four cognitive reasoning patterns for structured agent thinking: ReAct
  (Reason + Act), Plan-Execute-Verify, Reflexion (self-critique), and
  Tree of Thoughts. Each with trigger conditions, flow diagram, and
  verification gates. Agents load this to understand HOW to think.
tags: [reasoning, cognition, reaCT, plan-execute-verify, reflexion, tree-of-thoughts, patterns]
related_skills: [agent-flow, systematic-debugging, change-test-loop, task-decomposition, survey-before-action]
---

# Reasoning Patterns — How to Think

## When to Load This Skill

Load this skill when:
- Starting any non-trivial task (multi-step, multi-file, complex logic)
- You're unsure how to approach a problem
- A previous attempt failed and you need a fresh reasoning strategy
- The user explicitly asks you to "think through this"
- You catch yourself guessing or jumping to conclusions

## Overview: Four Patterns

| Pattern | Core idea | Best for | Worst for |
|---------|-----------|----------|-----------|
| **ReAct** | Interleave reasoning + tool calls | Debugging, exploration, open-ended | Routine tasks, well-defined specs |
| **PEV** | Plan → Execute → Verify in phases | Features, changes, deployments | Rapid iteration, exploratory work |
| **Reflexion** | Act → Observe → Critique → Revise | Quality-critical output, code review | Time-sensitive, trivial changes |
| **ToT** | Branch → Evaluate → Backtrack → Select | Architecture decisions, trade-off analysis | Simple, single-path tasks |

## Pattern 1: ReAct (Reason + Act)

The foundational pattern: **reason, act, observe, repeat.**

### Flow

```
Thought: "The query is slow. I need to check the query plan."
Action:  EXPLAIN ANALYZE the query
Observe: Seq Scan on users (cost=10000)
Thought: "No index on email. I should add one."
Action:  CREATE INDEX ON users(email)
Observe: Index created
Thought: "Now re-check the plan."
Action:  EXPLAIN ANALYZE again
Observe: Index Scan (cost=0.5) — fixed
```

### When to Use

- Debugging a problem where you don't know the root cause
- Exploring an unfamiliar codebase
- Investigating a production incident
- Any task where the path is unclear and each step reveals the next

### Rules

1. **Always state your thought before each action.** "I think X because Y. I'll check by doing Z."
2. **Observe the actual output.** Read it fully. Don't assume what it says.
3. **One action at a time.** Don't batch actions — you can't tell which one worked.
4. **If observation contradicts thought, update your mental model immediately.** Don't force evidence to fit.

### Verification Gate

Before declaring done:
- [ ] Did I state my reasoning before each action?
- [ ] Did I read each observation fully?
- [ ] Does my final mental model match the evidence?

---

## Pattern 2: Plan-Execute-Verify (PEV)

The enterprise default. **Plan first, then execute, then verify.**

### Flow

```
PLAN:    "I need to: (1) define the schema, (2) write migration,
          (3) update model, (4) add endpoint, (5) test. Expected:
          3 files changed, 0 regressions."
         → Snap the plan to .hermes/plans/ or a todo list
EXECUTE: Execute step 1 → step 2 → step 3 → ...
         → Each step: do it → verify it → move on
VERIFY:  "Does the output match the plan? Did I miss anything?
          Run tests. Check edge cases. Review diff."
```

### When to Use

- **Default for most tasks.** If you're not sure which pattern, use PEV.
- Feature implementation
- Configuration changes
- Deployments
- Any task with a clear spec

### Rules

1. **PLAN must be written before EXECUTE.** Even if just 3 bullet points in a comment. Writing it down catches assumptions.
2. **Each execute step is one atomic change.** If multiple files need changing, it's multiple steps.
3. **VERIFY is not optional.** The verification criteria were set during PLAN. Check each one.
4. **If VERIFY fails, don't patch — re-plan.** Go back to PLAN, update it, re-execute.

### Decision: Is this task simple enough to skip planning?

| Criterion | Must plan | Can skip planning |
|-----------|-----------|-------------------|
| Files changed | >1 | 1 |
| Risk of breaking something | Moderate+ | Low (cosmetic, docs) |
| User explicitly asked for quality | Yes | No |
| You've done this exact task before | — | Yes, same repo, same patterns |
| Time to plan vs time to fix mistakes | Plan saves time | Risk is low |

**Rule of thumb:** If you're asking "should I plan?" the answer is yes.

### Verification Gate

- [ ] **Plan written** — 3+ steps, each with expected outcome
- [ ] **Each step verified** — tool output inspected
- [ ] **Final state matches plan** — no scope creep, no missed steps
- [ ] **Coverage** — tests pass, edge cases handled
- [ ] **Diff reviewed** — no unintended changes

---

## Pattern 3: Reflexion (Self-Critique)

The quality multiplier. **After doing the work, critique your own output before presenting it.**

### Flow

```
ACT:    Do the work (implement, write, fix)
CRITIQUE: "If I were a senior engineer reviewing this, what would I flag?"
         → List 3-5 criticisms unprompted
REVISE:  Fix the top 2-3 issues
VERIFY:  Confirm revisions didn't break anything
PRESENT: Deliver the result with confidence score
```

### When to Use

- After completing any task before presenting results to the user
- Code review (review your own diff first)
- Documentation (review your own doc before asking for feedback)
- API design (review your own endpoint before submitting PR)
- **Always pair with PEV** — PEV for doing, Reflexion for reviewing

### Self-Critique Checklist (Generic)

Ask yourself each question honestly:

**Completeness:**
- Did I actually verify this works, or did I assume? (If assumed → go verify)
- Did I handle error states, edge cases, and empty/null inputs?
- Did I check all references, not just the first one?

**Correctness:**
- Is my reasoning valid, or did I jump to a conclusion?
- Am I conflating correlation with causation?
- Did I check the actual output of each tool call, or just glance at it?

**Scope:**
- Did I do more than asked (scope creep)?
- Did I do less than asked (missed requirement)?
- Did I check for side effects (other paths that call the same code)?

**Clarity:**
- Is my explanation clear enough that someone unfamiliar could follow it?
- Did I cite sources for claims that came from research?
- Did I distinguish fact from opinion?

### Calibration: When to trust vs when to double-check

| If you ... | Action |
|-----------|--------|
| Have done this exact task before with same tools | Trust but reflexion-check |
| Used tools you know well | Trust, quick reflexion |
| Used new tools or patterns | Deep reflexion |
| Are in a hurry | **Don't skip reflexion** — hurry is when mistakes happen |
| Feel "pretty sure" | Double-check your key assumption |
| Feel "absolutely certain" | Check your certainty against evidence |

### Verification Gate

- [ ] 3-5 self-criticisms generated unprompted
- [ ] Top 2-3 issues revised
- [ ] Revisions verified (no new bugs)
- [ ] Confidence score stated: HIGH / MEDIUM / LOW
- [ ] If LOW: what uncertainty remains?

---

## Pattern 4: Tree of Thoughts (ToT)

For when one answer isn't enough. **Generate multiple approaches, evaluate each, then choose.**

### Flow

```
BRANCH:  Generate 3+ approaches for the same problem
         A: "Use a relational DB with normalized schema"
         B: "Use a document store with denormalized data"
         C: "Use a hybrid: relational for core entities, docs for logs"
EVALUATE: Score each on defined criteria
         Speed:  A=3  B=2  C=1
         Simplicity: A=2  B=3  C=1
         Scalability: A=2  B=3  C=3
BACKTRACK: Discard dominated approaches
         C is dominated by A and B on all criteria
SELECT:  Best overall: B (document store)
         → State rationale: "B wins on simplicity + scalability,
            acceptable speed for our throughput"
```

### When to Use

- Architecture decisions
- Tool/library selection
- Design trade-offs with multiple valid options
- Any "which one should I use?" question
- Debugging where multiple root causes are plausible

### Rules

1. **Generate BEFORE evaluating.** Listing options and judging them at the same time produces confirmation bias (you favor the first idea).
2. **Define criteria BEFORE comparing.** Otherwise you'll pick the first option and rationalize it.
3. **At least 3 branches.** Two branches is a false dichotomy. Three reveals the design space.
4. **If branches look similar, they're not different enough.** Find the dimension where they diverge fundamentally.

### Evaluation Criteria Table

| Criterion | A | B | C |
|-----------|---|---|---|
| Correctness | 3 | 2 | 1 |
| Maintainability | 2 | 3 | 2 |
| Performance | 2 | 3 | 3 |
| Simplicity | 3 | 2 | 1 |
| Total | 10 | 10 | 7 |

**Score: 1=weak, 2=good, 3=excellent**

### Verification Gate

- [ ] 3+ branches generated before evaluation
- [ ] Evaluation criteria defined before comparing
- [ ] Each branch scored independently
- [ ] Choosing rationale stated explicitly
- [ ] Runner-up documented (if first choice fails)

---

## Pattern Selection Quick Reference

```
Is the task exploratory or well-defined?
  ├─ Exploratory (don't know the path) → ReAct
  └─ Well-defined (know what needs doing)
       ├─ Is there a quality concern?
       │   ├─ Yes → PEV + Reflexion (do it, then review)
       │   └─ No → PEV
       └─ Is there a design trade-off?
           ├─ Yes → ToT (evaluate options) → PEV (implement)
           └─ No → PEV
```

## Mandatory: State Your Pattern

**Before starting any non-trivial task, state which reasoning pattern you're using:**

> "I'll use Plan-Execute-Verify for this feature implementation. First, I'll write the plan..."

> "This looks like a ReAct problem — I need to explore the codebase to understand the bug. I'll reason one step at a time."

This lets the user (and future logs) see what thinking strategy you chose and whether it was appropriate.
