---
name: adversarial-verifier
version: 1.0.0
category: software-development
description: >-
  Adversarial verification — systematically attempts to break code BEFORE
  it ships. Covers A0-A5 maturity levels: surface scan, input fuzzing,
  state corruption, dependency sabotage, concurrency attacks, cheat
  detection, invariant violation, and property-based breaking.
pinned: true
related_skills:
  - change-checklist
  - loop-governance
  - agent-contract
---

# Adversarial Verifier — Break Code to Make It Better

**Load this skill during the quality phase of any code change.**

Standard verification asks: *"Does this code work?"*
Adversarial verification asks: *"How can I prove this code wrong?"*

## When to Use

- Before shipping any code change (recommended: A2 for standard, A4 for security-critical)
- During the quality phase (Wave 4) of session orchestration
- As the checker in maker/checker split

## Maturity Levels

| Level | Name | What's Included | Token Cost |
|-------|------|----------------|------------|
| **A0** | None | No adversarial verification | 0 |
| **A1** | Surface Scan | Attack surface enumeration only | ~2K |
| **A2** | Input Fuzzing | A1 + boundary testing + cheat detection | ~10K |
| **A3** | State Sabotage | A2 + state corruption + dependency sabotage | ~25K |
| **A4** | Full Adversarial | A3 + concurrency + invariants + property-based | ~50K |
| **A5** | Certified | A4 + evidence packaging + regression test seeding | ~75K |

**Default: A2** for standard changes. Use A4 for security-critical. Use A5 for F3 (unattended) agent output.

## Overview: The 4-Phase Loop

```
Implementer writes code
  → Test suite passes (standard verification)
    → ADVERSARIAL VERIFIER ACTIVATED
      → Phase 1: Attack Surface Enumeration
      → Phase 2: Active Breaking (selected techniques)
      → Phase 3: Evidence Packaging
      → Phase 4: Feedback
  → If findings: Fix → Re-run adversarial → Loop
  → If pass: Code is adversarially certified → Ship
```

---

## Phase 1: Attack Surface Enumeration

Before breaking anything, enumerate the full attack surface. Cover ALL four categories.

### Inputs

For every function/endpoint parameter, list:

| Parameter | Type | Constraints | Failure Modes |
|-----------|------|-------------|---------------|
| `user_id` | string | non-empty, alphanumeric | empty, SQL injection, unicode edge case, max length, null |
| `amount` | integer | 0 < amount < 1000000 | negative, zero, overflow, float, NaN |
| `email` | string | valid email format | empty, no-at-sign, too long, unicode, null |

**Run the `adversarial-verify.py` script** for automated boundary analysis:
```bash
python3 ~/.hermes-cortex/scripts/adversarial-verify.py --file <path> --level A1
```

### State

For every stateful component, list failure states:

| Component | States to Test |
|-----------|---------------|
| Database | Connection lost mid-query, timeout, concurrent write, stale read |
| Cache | Cold start (miss), stale entry, corrupted entry |
| File system | Disk full, permission denied, file locked |
| Network | Connection reset, DNS failure, timeout |

### Dependencies

For every external dependency, list failure modes:

| Dependency | Failures to Simulate |
|------------|---------------------|
| Payment gateway | Network timeout, 500 error, malformed response, auth expired |
| Auth service | Token expired, invalid signature, user not found |
| Queue/Message bus | Send timeout, queue full, message too large |

### Concurrency

Identify race windows:

| Scenario | What Could Go Wrong |
|----------|-------------------|
| Two identical requests | Duplicate, crash, corruption |
| Read during write | Stale data |
| Delete during update | Partial state |
| 1000 concurrent requests | Resource exhaustion |

### Checklist for Phase 1

- [ ] Every function parameter enumerated with failure modes
- [ ] Every stateful component listed
- [ ] Every external dependency listed
- [ ] Race windows identified
- [ ] Results saved for Phase 2

---

## Phase 2: Active Breaking

### Technique A: Input Fuzzing (A2)

For every input boundary, test at and beyond it:

```python
# For a function that accepts 1-100 items
boundary_inputs = [0, 1, 2, 50, 99, 100, 101, -1, "string", None, []]

# For a function that expects valid email
email_inputs = [
    "", "a@b.c", "no-at-sign", "@no-local",
    "a" * 320 + "@b.com", None
]

# For a numeric range 0 < amount < 1000000
numeric_inputs = [
    -1, 0, 1, 500000, 999999, 1000000, 1000001,
    1.5, "not-a-number", None
]
```

**Run the fuzzing script:**
```bash
python3 ~/.hermes-cortex/scripts/adversarial-verify.py --file <path> --level A2
```

### Technique B: State Corruption (A3)

For every state mutation point, simulate failure:

```python
# After every state mutation, ask:
db.commit()  → what if this throws?
cache.set()  → what if this silently fails?
queue.send() → what if this times out?
file.write() → what if disk is full?
```

**How to test:** Use monkey-patching / dependency injection to replace real calls with failing stubs. Or wrap the call in a try/except and verify the error path.

### Technique C: Dependency Sabotage (A3)

For each external dependency, simulate ALL of:

- Network timeout
- 500 error
- Empty response
- Malformed response format
- Auth failure (token expired)
- Rate limit exceeded

**How to test:** Replace the real dependency client with a mock that raises/spoofs each failure. Verify the code handles each one gracefully.

### Technique D: Concurrency Attacks (A4)

For race conditions, run scenarios:

```bash
# Two identical requests
curl -X POST ... & curl -X POST ... & wait

# Read during write
curl -X PUT ... & curl -X GET ... & wait

# 1000 concurrent requests
seq 1 1000 | xargs -P 100 -I {} curl -s -o /dev/null -w "%{http_code}\n" ...
```

### Technique E: Cheat Detection (A2)

Scan the diff for known cheat patterns:

| Pattern | What to Check |
|---------|---------------|
| Error swallowing | Empty `except:` or `catch {}` blocks over changed lines |
| No-op fix | Test was modified but source was not |
| Fake refactor | Renamed function but old callers still use old name |
| Test relaxation | `toEqual` → `toMatch`, strict → loose assertion |
| Type suppression | `@ts-ignore`, `# type: ignore` over changed lines |
| Assertion drop | Net assertion count in test file decreases |

```bash
# Check for assertion drops in changed test files
grep -c "expect\|assert\|should" tests/old.py  # before
grep -c "expect\|assert\|should" tests/new.py  # after
```

### Technique F: Invariant Violation (A4)

Identify implicit assumptions and break them:

```python
# The code assumes:
assumptions = [
    "user exists in database",
    "transaction is in pending state",
    "cache is populated",
    "third-party API is available",
    "file system has space",
    "clock is monotonically increasing",
    "input is valid (already validated)",
]
for assumption in assumptions:
    violate(assumption)  # what breaks?
```

### Technique G: Property-Based Breaking (A4)

Express properties the code should satisfy and try to falsify:

```python
# Property: sorting returns same-length list
property: len(sort(lst)) == len(lst)
counterexample: sort(non_list) → TypeError ≠ property violation

# Property: idempotent
property: process(data) == process(process(data))

# Property: monotonic
property: timestamp2 >= timestamp1
```

---

## Phase 3: Evidence Packaging

Every finding MUST be reproducible. Package it as:

```json
{
  "finding_id": "ADV-YYYY-MM-DD-NNN",
  "technique": "input-fuzzing",
  "target": "src/handler.py:42-56",
  "input": {"user_id": "'; DROP TABLE users; --"},
  "expected": "400 Bad Request (validation error)",
  "actual": "500 Internal Server Error",
  "reproduction": "curl -X POST -d '{\"user_id\": \"...\"}' http://localhost:3000/api/users",
  "root_cause": "No input sanitization on user_id",
  "classification": "security-injection",
  "severity": "critical",
  "regression_test_template": "def test_rejects_sql_injection():\\n    ..."
}
```

### Severity Classification

| Severity | Meaning | Action |
|----------|---------|--------|
| **critical** | Security vulnerability, data loss, or crash | Block release |
| **high** | Wrong behavior on valid input | Block release |
| **medium** | Wrong behavior on edge case | Fix before merge |
| **low** | Degraded UX, non-critical error path | Fix or document |
| **info** | Design observation, not a bug | Document |

### Checklist for Phase 3

- [ ] Every finding has a reproduction command
- [ ] Reproduction command actually reproduces
- [ ] Severity classified
- [ ] Root cause identified
- [ ] Regression test template provided

---

## Phase 4: Feedback

After adversarial review, update:

1. **Regression test suite** — each finding seeds a regression test
2. **Design rules** — discovered patterns become rules
3. **Attack surface library** — record failure modes for re-use
4. **Implementer brief** — show findings to the implementer

```yaml
feedback:
  regression_tests:
    - test_id: REG-SQL-INJECTION-001
      source: ADV-YYYY-MM-DD-001
      file: tests/regression/test_sql_injection.py
  design_rules:
    - rule: "All user-provided strings must pass through input sanitizer"
      source: ADV-YYYY-MM-DD-001
      file: docs/design-rules/input-sanitization.md
  attack_surface_updates:
    - added: "SQL injection"
      category: input-injection
```

---

## Integration Checklist

### With change-checklist (pre-ship)

When loaded before `end_change()`, run adversarial verification at the specified level:

```bash
python3 ~/.hermes-cortex/scripts/adversarial-verify.py --file <changed-files> --level A2
```

If findings are critical/high: block the release.
If findings are medium/low: fix or document before releasing.

### With session orchestration (Wave 4)

Adversarial verification runs in Wave 4 (Quality) AFTER standard tests pass
and BEFORE finalization. If findings:
- Critical/high → block Wave 4 → return to Wave 2 (Impl-Core)
- Medium/low → fix in Wave 4, proceed to Wave 5

### With maker/checker split

The adversarial verifier IS the checker for quality-critical work.
Use a DIFFERENT model for verifier vs implementer (hard requirement).

---

## Anti-Patterns

| Anti-pattern | Why It's Wrong |
|-------------|----------------|
| Running adversarial before standard tests | Standard tests should catch basic failures first |
| Same model for implementer and verifier | Blind spots are shared — defeats the purpose |
| "No findings = no bugs" | Report what was checked and why no failures found |
| Skipping evidence packaging | Unreproducible findings are not findings |
| Concurrency test run once | Non-deterministic — run 3x, report only if consistent |
