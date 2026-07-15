---
name: task-decomposition
version: 1.0.0
category: software-development
description: >
  Break large tasks into discrete, verifiable, independently completable
  units. Uses functional decomposition, vertical slicing, dependency
  ordering, and scope gating so agents execute predictably end-to-end.
tags: [planning, decomposition, execution, workflow, estimation]
related_skills: [dev-plan, story-decomposition, project-map, subagent-driven-development]
---

# Task Decomposition

## When to Use

Load this skill when:
- Given a large, ambiguous, or multi-step request
- A task spans multiple files, services, or concerns
- You need to parallelize work across subagents
- The user said "break this down" or "make a plan"

## The Framework

Every large task decomposes along these axes:

### Axis 1: Functional Decomposition

Split by function or concern:

```
Task: "Add user authentication"
→ User model + DB schema       (data layer)
→ Registration endpoint        (API layer)
→ Login endpoint               (API layer)
→ Token generation + JWT       (service layer)
→ Auth middleware               (middleware layer)
→ Login/register forms         (UI layer)
→ Session management           (client layer)
```

### Axis 2: Vertical Slicing

Split into end-to-end slices that deliver user-visible value:

```
Instead of:  Database → API → UI (all layers horizontally)
Do:         One complete feature end-to-end, then the next
Slice 1:    User can register with email+password ✓
Slice 2:    User can log in and get a token ✓
Slice 3:    User can reset password ✓
Slice 4:    User can log in with OAuth ✓
```

### Axis 3: Dependency Ordering

What must exist before each step can be built:

```
Step A:     (no deps) Create user table + model
  depends:  nothing
Step B:     (needs A) Registration endpoint
  depends:  A
Step C:     (needs B) Login endpoint
  depends:  B
Step D:     (needs C) Auth middleware
  depends:  C
```

### Quality Gate: INVEST Criteria

Every decomposed unit should be **INVEST**:

| Letter | Stands for | Means | Check |
|--------|-----------|-------|-------|
| **I** | **Independent** | Can be delivered in any order (minimize dependencies) | Can I build this without waiting for another unit? |
| **N** | **Negotiable** | Scope can vary — not a rigid spec | Can I cut scope on this unit if needed? |
| **V** | **Valuable** | Delivers user-visible value on its own | Does this produce something demonstrable? |
| **E** | **Estimable** | Team can estimate effort with confidence | Do I know roughly how long this takes? |
| **S** | **Small** | Fits in one sprint / work session (≤2 hours for agents) | Can I finish this in a single focused session? |
| **T** | **Testable** | Clear pass/fail criteria | Can I verify this is done objectively? |

**Rule of thumb:** If a unit fails INVEST on any letter, split further or
merge with an adjacent unit. INVEST failures are early warnings of:

## Process

### Step 1: Understand the full scope

Read all relevant files (`search_files`, `read_file`). Understand:
- What exists today (current state)
- What's requested (target state)
- What shouldn't change (constraints)

### Step 2: Write a decomposition plan

For each unit of work, define:

```
Unit: <name>
Purpose: <why this exists, what value it delivers>
Files: <paths to create or modify>
Depends on: <list of units that must come first>
Estimated effort: <small|medium|large>
Verification: <how to confirm it works — test, curl, script>
```

### Step 3: Order and gate

- Sort units by dependency order (topological sort)
- Group into phases (Phase 1 = foundation, Phase 2 = features, etc.)
- Identify which units can run in parallel (no dependency chain)
- Flag units that could be deferred if scope needs cutting

### Step 4: Reflexion — Self-Critique Decomposition

Before presenting the decomposition, critique it:

- [ ] Are any units too large (>2 hours)? Split them.
- [ ] Are any units too small (<5 minutes)? Merge them.
- [ ] Are the dependencies real or imagined? (If two units share state but
  no code, they may be parallel.)
- [ ] Is each unit independently verifiable? (If you can't verify a unit
  without building the next one, the split is wrong.)
- [ ] Are there hidden assumptions about what already exists?

### Step 5: Execute

- Complete one unit fully before moving to the next
- Verify each unit before declaring it done
- If a unit reveals new scope, decide: integrate or defer?

## Output Format

When asked to decompose a task, output:

```
## Decomposition

**Total units:** N
**Parallelizable:** M

### Phase 1: <name>
1. <unit> — <purpose> (est: <size>, verified: <method>)
2. <unit> — <purpose> (est: <size>, verified: <method>)

### Phase 2: <name>
3. <unit> — <purpose> (est: <size>, verified: <method>)

### Deferred (if scope cut needed)
- <unit> — <why it's lowest priority>
```

## Examples

### Example: "Add payment processing"

```
## Decomposition

**Total units:** 5
**Parallelizable:** 2 (units 1+2 can be done together)

### Phase 1: Foundation
1. `stripe-setup` — Install Stripe SDK, configure keys, set up webhook endpoint
   Depends: nothing | Files: config/stripe.py, .env.example
   Verified: python3 -c "import stripe; stripe.api_key = 'sk_test_...'"

2. `payment-model` — Create Payment model + DB migration
   Depends: nothing | Files: models/payment.py, migrations/
   Verified: migration runs, model imports without error

### Phase 2: Checkout
3. `checkout-session` — Create Stripe Checkout Session endpoint
   Depends: 1, 2 | Files: api/checkout.py, tests/test_checkout.py
   Verified: POST /checkout returns session URL

### Phase 3: Webhooks
4. `webhook-handler` — Handle payment_intent.succeeded/failed webhooks
   Depends: 1, 2 | Files: api/webhooks.py
   Verified: stripe trigger payment_intent.succeeded → DB updated

### Phase 4: Polish
5. `error-handling` — Failed payment UI, retry logic, refund support
   Depends: 3, 4 | Files: ui/payment-failed.js, api/refund.py
   Verified: Refund flow works end-to-end

### Deferred
- `subscriptions` — Recurring billing not in scope for MVP
```

### Example: "Fix performance regression"

```
## Decomposition

### Phase 1: Measure
1. Profile — Add instrumentation to identify slow paths
   Files: middleware/profiler.py
   Verified: /slow-endpoint shows timing breakdown in logs

### Phase 2: Fix
2. N+1 query — Add select_related() to User query
   Files: views/user_list.py
   Verified: SQL count drops from 42 to 3

3. Cache — Add Redis cache for expensive calculation
   Files: services/pricing.py
   Verified: Response time drops from 2.1s to 320ms

### Phase 3: Verify
4. Load test — Run locust to confirm improvement under load
   Files: tests/load/locustfile.py
   Verified: p99 latency <500ms at 100 concurrent users
```

## Pitfalls

- **Don't over-decompose.** If a unit takes <5 minutes, it's probably too
  small. Group related micro-steps.
- **Don't under-decompose.** If a unit takes >2 hours, it's probably too
  large. Split further.
- **Scope creep happens in the middle units.** The first and last are usually
  well-defined. Watch the middle ones for expansion.
- **Parallel units must be truly independent.** Shared state (same DB, same
  file, same config) creates dependencies that aren't obvious.
- **Verify before parallelizing.** Run unit A alone first, then parallel A and
  B once A is proven to produce stable output.
