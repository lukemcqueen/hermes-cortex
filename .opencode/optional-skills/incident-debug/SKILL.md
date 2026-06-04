---
name: incident-debug
description: |
  Diagnose and resolve production or test failures using structured,
  log-first debugging and minimal safe fixes.

  Triggers when user mentions:
  - "incident"
  - "production bug"
  - "something broke"
  - "error logs"
  - "debug this"
  - "root cause"
---

# Incident Debug

## Purpose
Identify root cause and fix issues safely using:
- logs first
- minimal changes
- verified fixes

Use for:
- production incidents
- failing tests
- runtime errors
- performance issues

---

## Core Rule

Do NOT guess.

Use evidence → isolate → fix → verify.

---

## Workflow (STRICT)

1. Define symptom
2. Collect evidence (logs, errors, failing tests)
3. Reproduce issue (if possible)
4. Narrow scope
5. Identify root cause
6. Apply minimal fix
7. Verify fix
8. Document findings

---

## Step 1: Define Symptom

Clarify:

- what is failing?
- where? (API, UI, DB, job, etc.)
- when did it start?
- impact level?

---

## Step 2: Collect Evidence

Gather:

- error logs
- stack traces
- request IDs
- failing tests
- recent changes (`git diff`)
- metrics (if available)

---

## Step 3: Reproduce

Try:

- local reproduction
- running failing test
- simulating input

If not reproducible:
→ rely on logs + recent changes

---

## Step 4: Narrow Scope

Reduce possibilities:

- isolate component (API, DB, UI)
- check recent commits
- identify failing dependency
- remove unrelated variables

---

## Step 5: Root Cause

Classify issue:

- logic bug
- data issue
- migration issue
- config/env mismatch
- dependency failure
- performance bottleneck
- race condition
- tool/proxy failure

---

## Step 6: Fix (STRICT)

- apply smallest possible fix
- do NOT refactor unrelated code
- preserve existing behavior
- add guardrails if needed

---

## Step 7: Verification

Run:
