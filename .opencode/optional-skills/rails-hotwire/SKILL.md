---
name: rails-hotwire
description: |
  Build, refactor, and test Rails + Hotwire code using conventions,
  Turbo, Stimulus, and enterprise-grade patterns.

  Triggers when user mentions:
  - "rails hotwire"
  - "turbo stream"
  - "stimulus controller"
  - "rails refactor"
  - "rails test"
---

# Rails + Hotwire

## Purpose
Generate, refactor, and test Rails code using:
- Rails conventions (thin controllers, rich models/services)
- Hotwire (Turbo + Stimulus)
- Safe, testable, production-ready patterns

---

## Inputs
- Feature request OR existing code
- Optional: failing test, error, or performance issue

---

## Output
ALWAYS return in this order:

1. **Code** (complete, ready to run)
2. **Explanation** (≤3 sentences, why this approach)
3. **Test** (`*_test.rb`, covering success + edge cases)

---

## Workflow (STRICT)

1. Understand intent (feature, refactor, bug, or test)
2. Prefer Rails conventions over custom patterns
3. Extract complexity into:
   - models
   - PORO service objects (`app/services`)
4. Add/modify Turbo/Stimulus only if needed
5. Ensure security (params, auth, CSRF)
6. Add/Update tests FIRST or alongside code
7. Keep output minimal and deterministic

---

## Architecture Rules (MANDATORY)

### Controllers
- Thin: only orchestration
- No business logic
- Use `before_action` for shared setup

### Models
- Contain domain logic
- Use validations + scopes
- Avoid fat callbacks → prefer services

### Services (REQUIRED for complexity)
Use when:
- multi-step logic
- external APIs
- transactions

Pattern:
```ruby
class CreateOrder
  def self.call(...)
    new(...).call
  end

  def call
    ActiveRecord::Base.transaction do
      # logic
    end
  end
end
```

---

## Hotwire Rules

### Turbo Frames

* Use for scoped partial updates
* Avoid over-nesting

### Turbo Streams

* Use for create/update/destroy flows
* Prefer server-rendered updates

Example:

```ruby
respond_to do |format|
  format.turbo_stream
  format.html { redirect_to ... }
end
```

### Stimulus

* Only for UI behavior (NOT business logic)
* Keep controllers small (<100 lines)

---

## Testing (MANDATORY)

Use Minitest (Rails default)

### Rules

* Test behavior, not implementation
* Cover:

  * success case
  * failure case
  * edge case

### Types

* Model tests → validations + logic
* Controller/Request tests → responses + auth
* System tests → Turbo/UX flows

Example:

```ruby
test "creates order with valid data" do
  assert_difference("Order.count", 1) do
    post orders_path, params: { order: valid_params }
  end
end
```

---

## Refactoring Guidelines

* Remove duplication first
* Extract methods > extract services
* Replace conditionals with polymorphism when large
* Keep methods ≤10–15 lines
* Name things clearly (critical)

---

## Security Rules (STRICT)

* Use strong params ALWAYS
* Never trust client input
* Keep CSRF enabled
* Escape output in views
* Validate all model inputs

---

## Performance (ENTERPRISE)

* Avoid N+1 → use `includes`
* Use background jobs for heavy work
* Cache where appropriate (fragment/cache keys)
* Prefer pagination for large datasets

---

## Commands (REFERENCE)

```bash
./run rails routes
./run rails test
./run rails db:migrate
./run rails console
```

---

## Anti-Patterns (AVOID)

* Fat controllers
* Business logic in views or JS
* Overusing Stimulus
* Skipping tests
* Large unstructured methods
* Direct SQL unless necessary

---

## Examples

### Example 1

User: "refactor this rails controller"

→ Extract service, slim controller, add tests

---

### Example 2

User: "add turbo stream create flow"

→ Add:

* controller `respond_to`
* turbo_stream view
* system test

---

## Goal

Produce **clean, testable, scalable Rails code** that:

* follows conventions
* uses Hotwire correctly
* passes tests
* is ready for production