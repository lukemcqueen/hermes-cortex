---
name: debugging
description: |
  Root-cause debugging: errors, failing tests, broken tools, unclear behavior.
  Triggers: "bug", "error", "failing test", "debug", "unexpected behavior"
---

# Debugging

## Core

Fix the cause, not the symptom.

## Workflow (STRICT)

1. Capture exact error — no paraphrasing
2. Identify failing layer: syntax/compile | runtime | test expectation | config/env | dependency/tool | data/state
3. Inspect nearest relevant code
4. Form ONE hypothesis
5. Confirm by reading code, logs, data
6. Hand off to `change-test-loop` for fix

```
observe → isolate → classify → confirm → report
```

## Confidence

Before handoff, score: **3** (confirmed by exact error/failing test/code inspection) | **2** (plausible) | **1** (weak guess) | **0** (no evidence)

Never edit below 3 unless diagnostic and reversible.

## Output

```md
## Debug Result
Root cause identified

## Location
file:line

## Type
failure classification

## Confidence
score: 0–3

## Next Step
handoff to change-test-loop
```

## Anti-Patterns

Guessing fixes | changing multiple areas | skipping error inspection | blind log injection | masking failures
