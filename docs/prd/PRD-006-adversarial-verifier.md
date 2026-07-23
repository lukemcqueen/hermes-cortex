# PRD: Adversarial Verifier — Breaking Code to Make It Better

> **PRD-006 | Status: Draft | Date: 2026-07-23**
>
> Derived from [wshobson/agents](https://github.com/wshobson/agents) validator pattern,
> [swarm-orchestrator](https://github.com/moonrunnerkc/swarm-orchestrator) cheat detection,
> and falsification-battery concept.

---

## Problem Statement

Standard code verification follows a cooperative pattern: the verifier checks if the
code **does what it's supposed to do**. This catches omissions but misses a critical
class of failures — the code may pass all its tests while still being wrong,
brittle, or insecure.

Four specific gaps:

1. **Tests can be gamed** — an agent can write tests that pass against a cheating
   implementation. The verifier sees green tests and approves.
2. **Edge cases are invisible** — the code works for the happy path but fails on
   every boundary. Standard testing only checks what the implementer thought of.
3. **Brittle correctness** — the code passes now but breaks under slightly
   different conditions (different input order, different timing, different scale).
4. **Security through obscurity** — the code isn't attacked, so vulnerabilities
   remain hidden.

A **cooperative verifier** asks: *"Does this code work?"*
An **adversarial verifier** asks: *"How can I prove this code wrong?"*

## Goals

1. **Adversarial verification as a first-class phase** — every delivery includes an
   adversarial attempt to break the code BEFORE it ships
2. **Attack surface enumeration** — systematically identify all the ways the code
   could fail
3. **Edge-case discovery** — find inputs, states, and sequences that cause failures
4. **Implementation cheating detection** — catch code that passes tests without
   genuine correctness
5. **Resilience certification** — code that survives adversarial review earns a
   higher trust level
6. **Learning feedback** — patterns discovered by adversarial review feed back into
   test suites and design rules

## Non-Goals

- Finding ALL bugs — adversarial verification is complementary to testing, not a replacement
- Automating full penetration testing — scope is code-level, not infrastructure-level
- Replacing human review — adversarial output feeds human decision-making

## Architecture

### The Adversarial Loop

```
Implementer writes code
  → Test suite passes (standard verification)
    → ADVERSARIAL VERIFIER ACTIVATED
      → Phase 1: Attack Surface Enumeration
         What could break? List every input, state, dependency, boundary.
      → Phase 2: Active Breaking
         Try to crash it, cheat it, bypass it, fool it.
      → Phase 3: Evidence Packaging
         What broke, how to reproduce, root cause.
      → Phase 4: Feedback
         Fix suggestions + regression test seeds + design rule updates.
  → If adversarial verifier finds failures:
     → Fix → Re-run adversarial → Loop
  → If adversarial verifier passes:
     → Code is adversarially certified → Ship
```

### Adversarial vs Cooperative Verification

| Dimension | Cooperative Verifier | Adversarial Verifier |
|-----------|--------------------|---------------------|
| **Question** | "Does this code work?" | "How can I prove this wrong?" |
| **Starting point** | Code + tests | Code, tests, failure modes |
| **Approach** | Check correctness | Attempt to break |
| **Output** | Pass/fail + findings | Reproduction cases + failure proofs |
| **Tone** | Supportive, constructive | Suspicious, probing |
| **Model** | Same or weaker model | Often stronger model |
| **Tools** | Test runner, linter | Fuzzer, property checker, mutation tester |

## Detailed Requirements

### REQ-001: Attack Surface Enumeration (Phase 1)

Before attempting to break anything, the adversarial verifier MUST enumerate the
full attack surface:

```yaml
attack_surface:
  inputs:
    - parameter: user_id
      type: string
      constraints: non-empty, alphanumeric
      failure_modes:
        - empty string
        - SQL injection attempt
        - Unicode normalization edge case
        - max length overflow
        - null/nil value
    - parameter: amount
      type: integer
      constraints: 0 < amount < 1000000
      failure_modes:
        - negative number
        - zero
        - overflow (max_int + 1)
        - float instead of int
        - NaN
  state:
    - component: database
      states:
        - connection lost mid-query
        - timeout
        - concurrent write from other process
        - stale read after write
    - component: cache
      states:
        - cache miss (cold start)
        - stale entry
        - corrupted entry
  dependencies:
    - service: payment-gateway
      failures:
        - network timeout
        - 500 error
        - malformed response
        - delayed response (>30s)
        - auth token expired
  concurrency:
    - two identical requests at same time (idempotency)
    - request during previous request's cleanup
    - 1000 concurrent requests (resource exhaustion)
```

**Acceptance:** Every code change produces an attack surface enumeration before
active breaking begins.

### REQ-002: Active Breaking Techniques (Phase 2)

The adversarial verifier applies these techniques in order:

#### Technique A: Input Fuzzing

Generate inputs at and beyond every boundary:

```python
# For a function that accepts 1-100 items
inputs = [0, 1, 2, 50, 99, 100, 101, -1, "string", None, []] 
# For a function that expects valid email
inputs = ["", "a@b.c", "no-at-sign", "@no-local", "a"*320 + "@b.com", None]
```

#### Technique B: State Corruption

Corrupt the state at every possible point:

```python
# After every state mutation, inject a failure
db.commit()  → what if this throws?
cache.set()  → what if this silently fails?
queue.send() → what if this timeouts?
```

#### Technique C: Dependency Sabotage

Make every external dependency fail:

```python
# For each external call, simulate:
- Network timeout
- 500 error  
- Empty response
- Malformed response format
- Auth failure
- Rate limit exceeded
```

#### Technique D: Concurrency Attacks

Identify and exploit race conditions:

```python
- Send two identical create requests → duplicate? crash? corruption?
- Read during write → stale data?
- Delete during update → partial state?
- Two operations that should be atomic — are they?
```

#### Technique E: Cheat Detection

Check if the implementation is cheating to pass tests:

```python
# Known cheat patterns (from swarm-orchestrator):
- error-swallow: empty catch blocks
- no-op-fix: test modified with no source change
- fake-refactor: renamed with old callers still using old name
- test-relaxation: strict matcher → loose matcher
- type-suppression: @ts-ignore over changed lines
- assertion-strip: net assertion count drops
```

#### Technique F: Invariant Violation

Identify and test implicit invariants:

```python
# The code assumes X is true — what if X is false?
assumptions = [
    "user exists in database",
    "transaction is in pending state",
    "cache is populated",
    "third-party API is available",
    "file system has space",
    "clock is monotonically increasing",
]
for assumption in assumptions:
    violate(assumption)  # what breaks?
```

#### Technique G: Property-Based Breaking

Express properties the code should satisfy and try to falsify them:

```python
# Property: sorting returns same-length list
property: len(sort(lst)) == len(lst)
counterexample: sort(non_list) → TypeError ≠ property violation

# Property: authorization is idempotent
property: check_auth(token) == check_auth(check_auth(token))
counterexample: check_auth(expired_token) → raises vs returns false
```

**Acceptance:** For each technique applicable to the code, the verifier produces
reproduction cases that demonstrate the failure (or proves the technique
cannot produce one).

### REQ-003: Evidence Packaging (Phase 3)

Every adversarial finding produces:

```json
{
  "finding_id": "ADV-2026-07-23-001",
  "technique": "input-fuzzing",
  "target": "src/handler.ts:42-56",
  "input": {"user_id": "'; DROP TABLE users; --"},
  "expected": "400 Bad Request (validation error)",
  "actual": "500 Internal Server Error",
  "reproduction": "curl -X POST -d '{\"user_id\": \"\\'; DROP TABLE users; --\"}' http://localhost:3000/api/users",
  "root_cause": "No input sanitization on user_id field before SQL query construction",
  "classification": "security-injection",
  "severity": "critical",
  "regression_test_template": "test('rejects SQL injection in user_id', async () => {\n  const res = await request(app).post('/api/users').send({ user_id: \"'; DROP TABLE...\" });\n  expect(res.status).toBe(400);\n});"
}
```

**Acceptance:** Every finding is reproducable from the evidence package alone.

### REQ-004: Feedback Integration (Phase 4)

Adversarial findings feed into:

1. **Regression test suite** — each finding seeds a regression test
2. **Design rules** — patterns found by adversarial review become design rules
3. **Attack surface library** — discovered failure modes are recorded for re-use
4. **Implementer brief** — the implementer sees what the adversary found, so they
   learn to avoid those patterns

```yaml
feedback:
  regression_tests:
    - test_id: REG-SQL-INJECTION-001
      source: ADV-2026-07-23-001
      file: tests/regression/sql-injection.test.ts
  design_rules:
    - rule: "All user-provided strings MUST pass through input sanitizer before reaching SQL"
      source: ADV-2026-07-23-001
      file: docs/design-rules/input-sanitization.md
  attack_surface_updates:
    - added: "SQL injection"
      category: input-injection
      to_library: yes
```

**Acceptance:** After adversarial review, regression tests, design rules, and
attack surface library are updated with findings.

### REQ-005: Integration with Session Waves (PRD-003)

The adversarial verifier slots into Wave 4 (Quality) AFTER the simplification pass
and BEFORE finalization:

```
Wave 4: Quality
  Step 1: Simplify generated code (remove AI over-engineering)
  Step 2: Write standard tests
  Step 3: Run standard test suite → must pass
  Step 4: ADVERSARIAL VERIFICATION
    → Attack surface enumeration
    → Active breaking (all 7 techniques)
    → Evidence packaging
  Step 5: If findings → fix → re-run adversarial → loop
  Step 6: If pass → proceed to Wave 5
```

**Acceptance:** A session with adversarial verification enabled runs all 7
breaking techniques before proceeding to finalization.

### REQ-006: Integration with Loop Maker/Checker Split (PRD-001)

In the maker/checker split, the adversarial verifier IS the checker for
quality-critical work:

```
Loop Cycle:
  Schedule → Triage → Implementer (maker)
    → Standard test suite
    → Adversarial Verifier (checker)
      → If finds failures → back to Implementer
      → If passes → certified
```

The implementer and adversarial verifier MUST use different models. The verifier
uses a stronger model when available.

**Acceptance:** A loop with adversarial verification enabled rejects code that
passes all standard tests but has adversarial failure modes.

### REQ-007: Integration with Cheat Detection (PRD-004)

Cheat detection (swarm-orchestrator) is DIFFERENT from adversarial verification:

| Aspect | Cheat Detection (PRD-004) | Adversarial Verification (PRD-006) |
|--------|---------------------------|-----------------------------------|
| **Scope** | Diff analysis — static patterns | Dynamic — actually runs/tests the code |
| **Method** | Structural analysis of the diff | Active breaking, fuzzing, state corruption |
| **Output** | Cheat flags (advisory) | Reproduction cases (actionable) |
| **Cost** | Fast (seconds) | Medium (minutes) |
| **When** | On every PR/diff | On quality-critical changes only |

They COMPOSE: cheat detection runs FAST on every diff. If it flags something,
ADVERSARIAL verification runs DEEP to confirm and reproduce.

**Acceptance:** A PR flagged by cheat detection triggers adversarial verification
to confirm and reproduce the finding.

### REQ-008: Adversarial Maturity Levels

| Level | Name | What's Included | Cost (tokens) |
|-------|------|----------------|---------------|
| A0 | None | No adversarial verification | 0 |
| A1 | Surface Scan | Attack surface enumeration only | ~2K |
| A2 | Input Fuzzing | A1 + input boundaries + cheat detection | ~10K |
| A3 | State Sabotage | A2 + state corruption + dependency sabotage | ~25K |
| A4 | Full Adversarial | A3 + concurrency + invariants + property-based | ~50K |
| A5 | Certified | A4 + evidence packaging + regression test seeding | ~75K |

Recommended: A2 for standard changes, A4 for security-critical, A5 for F3
(unattended) agent output.

## Acceptance Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| AC-001 | Attack surface enumeration covers inputs, state, dependencies, concurrency | Check output for all 4 categories |
| AC-002 | Input fuzzing finds boundary violations | Inject known boundary bug → found |
| AC-003 | State corruption finds incomplete rollbacks | Inject state corruption → found |
| AC-004 | Dependency sabotage finds missing error handling | Inject dependency failure → found |
| AC-005 | Concurrency attack finds race conditions | Inject race → found |
| AC-006 | Cheat detection (re-used from PRD-004) identifies known patterns | Known cheat → flagged |
| AC-007 | Invariant violation finds hidden assumptions | Break invariant → caught |
| AC-008 | Every finding includes reproduction command | Run reproduction → reproduces |
| AC-009 | Findings seed regression tests | Check test suite after fix |
| AC-010 | Adversarial verifier uses a DIFFERENT model than implementer | Config check |

## Implementation Phases

### Phase 1 — Foundation (Week 1)
- Attack surface enumeration format
- Input fuzzing technique (A1→A2)
- Evidence packaging format

### Phase 2 — Deep Breaking (Week 2-3)
- State corruption technique (A3)
- Dependency sabotage technique (A3)
- Invariant violation technique (A3)
- Concurrency attack technique (A4)

### Phase 3 — Cheat Detection Integration (Week 3)
- Re-use swarm-orchestrator core detectors
- Trigger path: cheat detection flags → adversarial verification confirms

### Phase 4 — Learning Loop (Week 4)
- Regression test seeding from findings
- Design rule extraction
- Attack surface library maintenance

### Phase 5 — Integration (Week 5)
- Add adversarial verification to Wave 4 (session-orchestration)
- Add adversarial verification to loop maker/checker split
- Maturity level configuration (A1-A5)
- F3 certification requirement

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Adversarial verifier costs too many tokens | Medium | Maturity levels; A2 default, A4/A5 for critical only |
| False positives erode trust | Medium | Reliable reproduction is mandatory — not "maybe" findings |
| Verifier finds nothing = false confidence | Low | Report what was checked and why no failures found |
| Verifier and implementer same model = blind spots | Low | Enforce DIFFERENT model in config |
| Concurrency attacks are non-deterministic | Medium | Run 3x; report only if consistently reproducible |
