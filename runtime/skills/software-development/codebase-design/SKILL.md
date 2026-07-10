---
name: codebase-design
description: "Deep module vocabulary and design principles — module, interface, depth, seam, adapter, leverage, locality. Use when designing or improving a module's interface, finding deepening opportunities, deciding where a seam goes, or making code more testable."
version: 1.0.0
author: Titus (ported from Matt Pocock's skills)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [architecture, design, module, interface, depth, seam, testability]
    related_skills: [architecture-review, design-doc-audit, systematic-debugging, change-test-loop]
---

# Codebase Design: Deep Modules

Design **deep modules**: a lot of behaviour behind a small interface, placed at a clean seam, testable through that interface. Use this language and these principles wherever code is being designed or restructured. The aim is leverage for callers, locality for maintainers, and testability for everyone.

## Glossary

Use these terms exactly — don't substitute "component," "service," "API," or "boundary." Consistent language is the whole point.

**Module** — anything with an interface and an implementation. Deliberately scale-agnostic: a function, class, package, or tier-spanning slice. *Avoid*: unit, component, service.

**Interface** — everything a caller must know to use the module correctly: the type signature, but also invariants, ordering constraints, error modes, required configuration, and performance characteristics. *Avoid*: API, signature (too narrow — they refer only to the type-level surface).

**Implementation** — what's inside a module, its body of code. Distinct from **Adapter**: a thing can be a small adapter with a large implementation (a Postgres repo) or a large adapter with a small implementation (an in-memory fake). Reach for "adapter" when the seam is the topic; "implementation" otherwise.

**Depth** — leverage at the interface: the amount of behaviour a caller (or test) can exercise per unit of interface they have to learn. A module is **deep** when a large amount of behaviour sits behind a small interface, **shallow** when the interface is nearly as complex as the implementation.

**Seam** *(Michael Feathers)* — a place where you can alter behaviour without editing in that place; the *location* at which a module's interface lives. Where to put the seam is its own design decision, distinct from what goes behind it. *Avoid*: boundary (overloaded with DDD's bounded context).

**Adapter** — a concrete thing that satisfies an interface at a seam. Describes *role* (what slot it fills), not substance (what's inside).

**Leverage** — what callers get from depth: more capability per unit of interface they learn. One implementation pays back across N call sites and M tests.

**Locality** — what maintainers get from depth: change, bugs, knowledge, and verification concentrate in one place rather than spreading across callers. Fix once, fixed everywhere.

## Deep vs Shallow

**Deep module** = small interface + lots of implementation:

```
┌─────────────────────┐
│   Small Interface   │  ← Few methods, simple params
├─────────────────────┤
│                     │
│  Deep Implementation│  ← Complex logic hidden
│                     │
└─────────────────────┘
```

**Shallow module** = large interface + little implementation (avoid):

```
┌─────────────────────────────────┐
│       Large Interface           │  ← Many methods, complex params
├─────────────────────────────────┤
│  Thin Implementation            │  ← Just passes through
└─────────────────────────────────┘
```

When designing an interface, ask:
- Can I reduce the number of methods?
- Can I simplify the parameters?
- Can I hide more complexity inside?

## Principles

- **Depth is a property of the interface, not the implementation.** A deep module can be internally composed of small, mockable, swappable parts — they just aren't part of the interface. A module can have **internal seams** (private to its implementation, used by its own tests) as well as the **external seam** at its interface.
- **The deletion test.** Imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across N callers, it was earning its keep.
- **The interface is the test surface.** Callers and tests cross the same seam. If you want to test *past* the interface, the module is probably the wrong shape.
- **One adapter means a hypothetical seam. Two adapters means a real one.** Don't introduce a seam unless something actually varies across it.

## Designing for Testability

Good interfaces make testing natural:

1. **Accept dependencies, don't create them.**

   ```python
   # Testable
   def process_order(order, payment_gateway): ...

   # Hard to test
   def process_order(order):
       gateway = StripeGateway()
   ```

2. **Return results, don't produce side effects.**

   ```python
   # Testable
   def calculate_discount(cart) -> Discount: ...

   # Hard to test
   def apply_discount(cart) -> None:
       cart.total -= discount
   ```

3. **Small surface area.** Fewer methods = fewer tests needed. Fewer params = simpler test setup.

## Deepening a Module

When a module is shallow, deepen it. The strategy depends on the dependency category:

### Dependency Categories

| Category | Example | Strategy |
|----------|---------|----------|
| **In-process** | Pure computation, in-memory state, no I/O | Always deepenable — merge modules, test through the new interface directly |
| **Local-substitutable** | PGLite for Postgres, in-memory filesystem | Deepen with the stand-in running in-test. No port at the external interface needed |
| **Remote but owned** | Your own services across a network boundary | Define a **port** (interface) at the seam. Deep module owns the logic; transport is injected as an adapter. Production: HTTP adapter. Test: in-memory adapter |
| **True external** | Third-party services (Stripe, Twilio) | The deepened module takes the external dependency as an injected port; tests provide a mock adapter |

### Seam Discipline

- **One adapter means a hypothetical seam. Two adapters means a real one.** Don't introduce a port unless at least two adapters are justified (typically production + test). A single-adapter seam is just indirection.
- **Internal seams vs external seams.** A deep module can have internal seams (private to its implementation, used by its own tests) as well as the external seam at its interface. Don't expose internal seams through the interface just because tests use them.

### Testing Strategy: Replace, Don't Layer

- Old unit tests on shallow modules become waste once tests at the deepened module's interface exist — **delete them**.
- Write new tests at the deepened module's interface. The **interface is the test surface**.
- Tests assert on observable outcomes through the interface, not internal state.
- Tests should survive internal refactors — they describe behaviour, not implementation. If a test has to change when the implementation changes, it's testing past the interface.

## Integration with Other Skills

- **architecture-review** — Use deep module vocabulary when evaluating approach A vs B: compare their depth (interface size vs hidden complexity), seam placement, and adapter count.
- **design-doc-audit** — Call out shallow modules when auditing design docs against codebase. The "deletion test" is a quick audit heuristic.
- **systematic-debugging** — When a bug resists fixing, evaluate whether missing seam discipline (no clean interface to test against) is the root cause. Flag it as a post-mortem finding.
- **change-test-loop** — Apply deep module principles when designing the module before the first RED test.

## When to Use

- User asks to "design a module" or "improve this module's interface"
- You're reviewing a PR and the module interface is too large or too shallow
- You're preparing to write tests and finding the module hard to test
- User says "this module is doing too much" or "this interface is leaky"
- A bug is hard to fix because the module has no clear seam to test against
- During architecture review, to evaluate whether a proposed module structure is deep or shallow

## Pitfalls

- **Don't introduce a seam before it's needed.** One adapter means a hypothetical seam. Wait until you have two real uses before introducing the port.
- **Depth is not line count.** A 300-line function with no interface is not deep — it's monolithic. Depth is measured at the interface, not the implementation.
- **Don't expose internal seams.** A module can have internal seams for testing, but they should stay private. Exposing them through the interface breaks encapsulation and prevents future refactoring.
- **"Interface" is broader than types.** Interface includes error modes, ordering constraints, config requirements, and performance characteristics — not just the type signature.
