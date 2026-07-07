---
name: systematic-debugging
description: "6-phase root cause debugging: feedback loop, reproduce, pattern, hypothesise + instrument, fix, cleanup. Understand bugs before fixing."
version: 2.0.0
author: Hermes Agent (adapted from obra/superpowers + Matt Pocock/diagnosing-bugs)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [debugging, troubleshooting, problem-solving, root-cause, investigation]
    related_skills: [change-test-loop, plan, subagent-driven-development, codebase-design]
---

# Systematic Debugging

## Overview

Random fixes waste time and create new bugs. Quick patches mask underlying issues.

**Core principle:** ALWAYS build a tight feedback loop before theorizing. ALWAYS find root cause before attempting fixes. Symptom fixes are failure.

**Violating the letter of this process is violating the spirit of debugging.**

## The Iron Law

```
NO FIXES WITHOUT FEEDBACK LOOP FIRST
```

If you haven't completed Phase 0 (built a tight pass/fail signal for the bug), you cannot propose fixes.

## When to Use

Use for ANY technical issue:
- Test failures
- Bugs in production
- Unexpected behavior
- Performance problems
- Build failures
- Integration issues

**Use this ESPECIALLY when:**
- Under time pressure (emergencies make guessing tempting)
- "Just one quick fix" seems obvious
- You've already tried multiple fixes
- Previous fix didn't work
- You don't fully understand the issue

**Don't skip when:**
- Issue seems simple (simple bugs have root causes too)
- You're in a hurry (rushing guarantees rework)
- Someone wants it fixed NOW (systematic is faster than thrashing)

## The Six Phases

You MUST complete each phase before proceeding to the next.

---

## Phase 0: Build a Feedback Loop

**This is the skill.** Everything else is mechanical.

If you have a **tight** pass/fail signal for the bug — one that goes red on *this* bug — you will find the cause; bisection, hypothesis-testing, and instrumentation all just consume it. If you don't have one, no amount of staring at code will save you.

Spend disproportionate effort here. **Be aggressive. Be creative. Refuse to give up.**

### Ways to construct one — try in roughly this order

1. **Failing test** at whatever seam reaches the bug — unit, integration, e2e.
2. **Curl / HTTP script** against a running dev server.
3. **CLI invocation** with a fixture input, diffing stdout against a known-good snapshot.
4. **Headless browser script** (Playwright / Puppeteer) — drives the UI, asserts on DOM/console/network.
5. **Replay a captured trace.** Save a real network request / payload / event log to disk; replay it through the code path in isolation.
6. **Throwaway harness.** Spin up a minimal subset of the system (one service, mocked deps) that exercises the bug code path with a single function call.
7. **Property / fuzz loop.** If the bug is "sometimes wrong output", run 1000 random inputs and look for the failure mode.
8. **Bisection harness.** If the bug appeared between two known states (commit, dataset, version), automate "boot at state X, check, repeat" so you can `git bisect run` it.
9. **Differential loop.** Run the same input through old-version vs new-version (or two configs) and diff outputs.
10. **HITL bash script.** Last resort. If a human must click, drive *them* with a structured loop script so the loop is still repeatable. Captured output feeds back to you.

Build the right feedback loop, and the bug is 90% fixed.

### Tighten the loop

Treat the loop as a product. Once you have *a* loop, **tighten** it:

- Can I make it faster? (Cache setup, skip unrelated init, narrow the test scope.)
- Can I make the signal sharper? (Assert on the specific symptom, not "didn't crash".)
- Can I make it more deterministic? (Pin time, seed RNG, isolate filesystem, freeze network.)

A 30-second flaky loop is barely better than no loop; a 2-second deterministic one is a debugging superpower.

### Non-deterministic bugs

The goal is not a clean repro but a **higher reproduction rate**. Loop the trigger 100×, parallelise, add stress, narrow timing windows, inject sleeps. A 50%-flake bug is debuggable; 1% is not — keep raising the rate until it's debuggable.

### When you genuinely cannot build a loop

Stop and say so explicitly. List what you tried. Ask the user for: (a) access to whatever environment reproduces it, (b) a captured artifact (HAR file, log dump, core dump, screen recording with timestamps), or (c) permission to add temporary production instrumentation. Do **not** proceed to hypothesise without a loop.

### Phase 0 Completion Checklist

- [ ] A tight, deterministic pass/fail signal exists
- [ ] The signal goes red on *this specific bug* (proven by running it)
- [ ] The loop is fast enough to iterate on (seconds, not minutes)
- [ ] It can be run unattended (or HITL script exists for manual steps)

**STOP:** Do not proceed to Phase 1 without a tight feedback loop.

---

## Phase 1: Reproduce + Minimise

**Before anything else:** confirm the bug.

Run the loop from Phase 0. Watch it go red.

Confirm:
- [ ] The loop produces the failure mode the **user** described — not a different failure that happens to be nearby. Wrong bug = wrong fix.
- [ ] The failure is reproducible across multiple runs (or, for non-deterministic bugs, reproducible at a high enough rate to debug against).
- [ ] You have captured the exact symptom (error message, wrong output, timing) so later phases can verify the fix actually addresses it.

### Minimise

Once it's red, shrink the repro to the **smallest scenario that still goes red**. Cut inputs, callers, config, data, and steps **one at a time**, re-running the loop after each cut — keep only what's load-bearing for the failure.

Why bother: a minimal repro shrinks the hypothesis space (fewer moving parts left to suspect) and becomes the clean regression test in Phase 4.

Done when **every remaining element is load-bearing** — removing any one of them makes the loop go green.

### Evidence Gathering

Now that you have a minimised repro, gather evidence systematically:

1. **Read Error Messages Carefully** — stack traces, line numbers, error codes
2. **Check Recent Changes** — `git log --oneline -10`, `git diff`
3. **Trace Data Flow** — where does the bad value originate? Trace upstream to find the source

**Action:** Use `read_file` on relevant source files. Use `search_files` to trace references:

```python
# Find where the function is called
search_files("function_name(", path="src/", file_glob="*.py")

# Find where the variable is set
search_files(r"variable_name\s*=", path="src/", file_glob="*.py")
```

4. **Multi-Component Systems** — for each component boundary, log what enters and exits. Find WHERE it breaks before investigating the specific component.

### Phase 1 Completion Checklist

- [ ] Bug reproduced and confirmed as the *correct* bug
- [ ] Repro minimised to smallest load-bearing scenario
- [ ] Error messages fully read and understood
- [ ] Recent changes identified and reviewed
- [ ] Evidence gathered (logs, state, data flow)
- [ ] Problem isolated to specific component/code

---

## Phase 2: Pattern Analysis

**Find the pattern before hypothesising:**

### 1. Find Working Examples

- Locate similar working code in the same codebase
- What works that's similar to what's broken?

**Action:** Use `search_files` to find comparable patterns:

```python
search_files("similar_pattern", path="src/", file_glob="*.py")
```

### 2. Compare Against References

- If implementing a pattern, read the reference implementation COMPLETELY
- Don't skim — read every line
- Understand the pattern fully before applying

### 3. Identify Differences

- What's different between working and broken?
- List every difference, however small
- Don't assume "that can't matter"

### 4. Understand Dependencies

- What other components does this need?
- What settings, config, environment?
- What assumptions does it make?

### Phase 2 Completion

- [ ] Working examples found and compared
- [ ] Differences identified between working and broken

---

## Phase 3: Hypothesise + Instrument

### Generate 3-5 Ranked Hypotheses

Generate **3-5 ranked hypotheses** before testing any of them. Single-hypothesis generation anchors on the first plausible idea.

Each hypothesis must be **falsifiable**: state the prediction it makes.

> Format: "If <X> is the cause, then <changing Y> will make the bug disappear / <changing Z> will make it worse."

If you cannot state the prediction, the hypothesis is a vibe — discard or sharpen it.

**Show the ranked list to the user before testing.** They often have domain knowledge that re-ranks instantly ("we just deployed a change to #3"), or know hypotheses they've already ruled out. Cheap checkpoint, big time saver. Don't block on it — proceed with your ranking if the user is AFK.

### Instrument — One Variable at a Time

Each probe must map to a specific prediction from Phase 3. **Change one variable at a time.**

**Tool preference:**
1. **Debugger / REPL inspection** if the env supports it. One breakpoint beats ten logs.
2. **Targeted logs** at the boundaries that distinguish hypotheses.
3. Never "log everything and grep".

**Tag every debug log** with a unique prefix, e.g. `[DEBUG-a4f2]`. Cleanup at the end becomes a single grep. Untagged logs survive; tagged logs die.

**Perf branch.** For performance regressions, logs are usually wrong. Instead: establish a baseline measurement (timing harness, `performance.now()`, profiler, query plan), then bisect. Measure first, fix second.

**When You Don't Know**
- Say "I don't understand X"
- Don't pretend to know
- Ask the user for help
- Research more

### Phase 3 Completion Checklist

- [ ] 3-5 ranked hypotheses generated (shown to user if present)
- [ ] Each hypothesis is falsifiable with a prediction
- [ ] Instrumentation probes one variable at a time
- [ ] Debug logs tagged with unique prefix
- [ ] Perf bugs: baseline measurement established before fix

---

## Phase 4: Fix + Regression Test

**Fix the root cause, not the symptom:**

### 1. Check for a Correct Test Seam

Write the regression test **before the fix** — but only if there is a **correct seam** for it.

A correct seam is one where the test exercises the **real bug pattern** as it occurs at the call site. If the only available seam is too shallow (unit test that can't replicate the chain that triggered the bug), a regression test there gives false confidence.

**If no correct seam exists, that itself is the finding.** Note it. The codebase architecture is preventing the bug from being locked down. This is a candidate for the `codebase-design` skill — the module needs deepening to create a testable seam.

### 2. If a Correct Seam Exists

1. Turn the minimised repro into a failing test at that seam (RED)
2. Watch it fail for the correct reason
3. Apply the fix — ONE change at a time
4. Watch it pass (GREEN)
5. Re-run the Phase 0 feedback loop against the **original (un-minimised)** scenario

```bash
# Run the specific regression test
pytest tests/test_module.py::test_regression -v

# Run full suite — no regressions
pytest tests/ -q
```

### 3. If Fix Doesn't Work — The Rule of Three

- **STOP.**
- Count: How many fixes have you tried?
- If < 3: Return to Phase 1, re-analyse with new information
- **If ≥ 3: STOP and question the architecture (step 4 below)**
- DON'T attempt Fix #4 without architectural discussion

### 4. If 3+ Fixes Failed: Question Architecture

**Pattern indicating an architectural problem:**
- Each fix reveals new shared state/coupling in a different place
- Fixes require "massive refactoring" to implement
- Each fix creates new symptoms elsewhere

**STOP and question fundamentals.** Discuss with the user before attempting more fixes. This is NOT a failed hypothesis — this is a wrong architecture. Use the `codebase-design` skill to evaluate module depth, seam placement, and adapter strategy.

### Phase 4 Completion Checklist

- [ ] Correct seam identified (or absence documented)
- [ ] Regression test passes at the seam
- [ ] Original Phase 0 loop goes green
- [ ] Full test suite passes
- [ ] No regressions introduced

---

## Phase 5: Cleanup + Post-mortem

**Required before declaring done:**

- [ ] Original repro no longer reproduces (re-run the Phase 0 loop)
- [ ] Regression test passes (or absence of seam is documented)
- [ ] All `[DEBUG-...]` instrumentation removed (`grep` the prefix)
- [ ] Throwaway prototypes deleted (or moved to a clearly-marked debug location)
- [ ] The hypothesis that turned out correct is stated in the commit / PR message — so the next debugger learns

**Then ask: what would have prevented this bug?** If the answer involves architectural change (no good test seam, tangled callers, hidden coupling), hand off to the `codebase-design` skill with the specifics. Make the recommendation **after** the fix is in, not before — you have more information now than when you started.

---

## Red Flags — STOP and Follow Process

If you catch yourself thinking:
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Add multiple changes, run tests"
- "Skip the test, I'll manually verify"
- "It's probably X, let me fix that"
- "I don't fully understand but this might work"
- "Pattern says X but I'll adapt it differently"
- "Here are the main problems: [lists fixes without investigation]"
- Proposing solutions before a tight feedback loop exists
- **"One more fix attempt" (when already tried 2+)**
- **Each fix reveals a new problem in a different place**

**ALL of these mean: STOP. Return to Phase 0.**

**If 3+ fixes failed:** Question the architecture (Phase 4 step 4).

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple, don't need process" | Simple issues have root causes too. Process is fast for simple bugs. |
| "Emergency, no time for process" | Systematic debugging is FASTER than guess-and-check thrashing. |
| "Just try this first, then investigate" | Without a feedback loop, you can't tell if the fix worked. Build the loop first. |
| "I'll write test after confirming fix works" | Untested fixes don't stick. Test first proves it. |
| "Multiple fixes at once saves time" | Can't isolate what worked. Causes new bugs. |
| "Reference too long, I'll adapt the pattern" | Partial understanding guarantees bugs. Read it completely. |
| "I see the problem, let me fix it" | Seeing symptoms ≠ understanding root cause. |
| "One more fix attempt" (after 2+ failures) | 3+ failures = architectural problem. Question the pattern, don't fix again. |

## Quick Reference

| Phase | Key Activities | Success Criteria |
|-------|---------------|------------------|
| **0. Feedback Loop** | Build tight pass/fail signal; 10 construction methods; tighten loop | One command that goes red on *this bug* |
| **1. Reproduce + Minimise** | Run the loop, confirm correct bug, minimise, gather evidence | Minimal repro; bug understood |
| **2. Pattern Analysis** | Find working examples, compare, identify differences | Know what's different |
| **3. Hypothesise + Instrument** | 3-5 ranked hypotheses, tagged debug logs, one variable at a time | Confirmed hypothesis; root cause identified |
| **4. Fix + Regression Test** | Check seam, RED-GREEN, verify original loop goes green | Bug resolved, all tests pass |
| **5. Cleanup + Post-mortem** | Remove instrumentation, document hypothesis, ask "what would prevent this?" | Clean commit; architecture note if applicable |

## Hermes Agent Integration

### Investigation Tools

Use these Hermes tools during debugging:

- **`search_files`** — Find error strings, trace function calls, locate patterns
- **`read_file`** — Read source code with line numbers for precise analysis
- **`terminal`** — Run tests, check git history, reproduce bugs

### With delegate_task

For complex multi-component debugging, dispatch investigation subagents:

```python
delegate_task(
    goal="Investigate why [specific test/behavior] fails",
    context="""
    Follow systematic-debugging skill:
    0. Build a tight feedback loop first
    1. Reproduce and minimise
    2. Find pattern differences
    3. Generate ranked hypotheses
    4. Report findings — do NOT fix yet

    Error: [paste full error]
    File: [path to failing code]
    Test command: [exact command]
    """,
    toolsets=['terminal', 'file']
)
```

### With change-test-loop

When fixing bugs:
1. Phase 0 → build the feedback loop that proves the bug
2. Write a test that reproduces the bug (RED)
3. Debug systematically to find root cause
4. Fix the root cause (GREEN)
5. The test proves the fix and prevents regression

### With codebase-design

When a bug resists fixing because no good test seam exists, use the `codebase-design` skill:
- Evaluate whether the module is deep or shallow
- Identify whether a seam can be introduced
- Design the deepened module before attempting the fix

## Real-World Impact

From debugging sessions:
- Systematic approach: 15-30 minutes to fix
- Random fixes approach: 2-3 hours of thrashing
- First-time fix rate: 95% vs 40%
- New bugs introduced: Near zero vs common

**No shortcuts. No guessing. Systematic always wins.**
