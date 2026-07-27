# Adversarial Techniques — Quick Reference

## Phase 1: Attack Surface Enumeration

```
INPUTS        → boundaries, injection, null, overflow, type confusion
STATE         → DB down, cache miss, stale data, disk full, file locked
DEPENDENCIES  → timeout, 500, empty response, malformed, auth failure
CONCURRENCY   → duplicate requests, read-during-write, delete-during-update, 1000x
```

## Phase 2: Active Breaking

| # | Technique | Level | What to Do | When |
|---|-----------|-------|------------|------|
| A | Input Fuzzing | A2 | Test boundary values at and beyond every limit | Every change |
| B | State Corruption | A3 | Inject failure after every state mutation | Stateful code |
| C | Dependency Sabotage | A3 | Make every external dep fail in every way | Network calls |
| D | Concurrency Attacks | A4 | Duplicate requests, race conditions, RMW | Shared state |
| E | Cheat Detection | A2 | Scan diff for error-swallow, no-op, test-relaxation | Every diff |
| F | Invariant Violation | A4 | List implicit assumptions, break each one | Business logic |
| G | Property-Based | A4 | Express properties, try to falsify | Pure functions |

## Technique A: Boundary Inputs by Type

| Type | Boundary Values |
|------|----------------|
| `str` | `""`, `"a"`, `"a"*1000`, `None`, `"' OR '1'='1"`, `"<script>"`, `"../etc/passwd"` |
| `int` | `-1`, `0`, `1`, `2**31-1`, `2**31`, `"not-a-number"`, `None`, `1.5` |
| `float` | `-1.0`, `0.0`, `1e308`, `float("inf")`, `float("nan")`, `None` |
| `bool` | `None`, `"true"`, `1`, `0`, `"false"` |
| `list` | `[]`, `[1]`, `list(range(1000))`, `None` |
| `dict` | `{}`, `{"k":"v"}`, `None` |

## Technique E: Cheat Patterns to Scan

| Pattern | What to grep |
|---------|-------------|
| Error swallow | `except\s*(?:\w+)*:\s*\n\s*(pass\|#)` |
| Type suppression | `# type: ignore`, `@ts-ignore` over changed lines |
| Lint suppression | `# flake8: noqa`, `pylint: disable=all` |
| Test relaxation | `toEqual` → `toMatch`, strict → loose |
| No-op fix | Test modified, source NOT modified |
| Assertion drop | `grep -c "expect\|assert"` before/after |

## CLI Usage

```bash
# A1: Surface scan only
adversarial-verify.py --file path/to/code.py --level A1

# A2: Surface + fuzzing + cheat detection
adversarial-verify.py --file path/to/code.py --level A2

# A2 on whole directory
adversarial-verify.py --dir path/to/project --level A2

# JSON output for programmatic consumption
adversarial-verify.py --file path/to/code.py --level A2 --json
```

## Severity Guide

| Severity | Meaning | Action |
|----------|---------|--------|
| 🔴 critical | Security, data loss, crash | Block release |
| 🟠 high | Wrong behavior on valid input | Block release |
| 🟡 medium | Edge case failure | Fix before merge |
| 🔵 low | UX degredation, non-critical error | Fix or document |
| ⚪ info | Design observation | Document |

## Evidence Package Template

```json
{
  "finding_id": "ADV-YYYY-MM-DD-NNN",
  "technique": "input-fuzzing",
  "target": "src/handler.py:42-56",
  "input": {"user_id": "'; DROP..."},
  "expected": "400 Bad Request",
  "actual": "500 Internal Server Error",
  "reproduction": "curl -X POST -d '...' http://localhost:3000/api/users",
  "root_cause": "No input sanitization",
  "severity": "critical"
}
```
