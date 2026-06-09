---
name: improve-codebase-architecture
description: Find deepening opportunities in a codebase. Surface architectural friction and propose refactors that turn shallow modules into deep ones. Use when the user wants to improve architecture, find refactoring opportunities, consolidate tightly-coupled modules, or make a codebase more testable and AI-navigable.
category: software-development
---

# Improve Codebase Architecture

Surface architectural friction and propose **deepening opportunities** — refactors that turn shallow modules into deep ones. The aim is testability and AI-navigability.

## Glossary

Use these terms exactly in every suggestion. Consistent language is the point — don't drift into "component," "service," "API," or "boundary."

- **Module** — anything with an interface and an implementation (function, class, package, slice).
- **Interface** — everything a caller must know to use the module: types, invariants, error modes, ordering, config. Not just the type signature.
- **Implementation** — the code inside.
- **Depth** — leverage at the interface: a lot of behaviour behind a small interface. **Deep** = high leverage. **Shallow** = interface nearly as complex as the implementation.
- **Seam** — where an interface lives; a place behaviour can be altered without editing in place. (Use this, not "boundary.")
- **Adapter** — a concrete thing satisfying an interface at a seam.
- **Leverage** — what callers get from depth.
- **Locality** — what maintainers get from depth: change, bugs, knowledge concentrated in one place.

### Key Principles

- **Deletion test**: imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across N callers, it was earning its keep.
- **The interface is the test surface.** Callers and tests cross the same seam.
- **One adapter = hypothetical seam. Two adapters = real seam.** Don't introduce a seam unless something actually varies across it.
- **Depth is a property of the interface, not the implementation.** A deep module can be internally composed of small, mockable parts — they just aren't part of the interface.
- **Internal seams** (private to implementation, used by own tests) are distinct from the **external seam** at the module's interface.

### Relationships

- A **Module** has exactly one **Interface** (the surface it presents to callers and tests).
- **Depth** is a property of a **Module**, measured against its **Interface**.
- A **Seam** is where a **Module**'s **Interface** lives.
- An **Adapter** sits at a **Seam** and satisfies the **Interface**.
- **Depth** produces **Leverage** for callers and **Locality** for maintainers.

## When to Use

- User says "this codebase is hard to change" or "tests are brittle"
- You find modules where understanding requires bouncing between many small files
- Pure functions extracted for testability, but real bugs hide in how they're called
- Tightly-coupled modules leak across their seams
- Parts of the codebase are untestable through their current interface
- As a pre-step before planning a refactor (load this skill, then load `plan`)

## Process

### 1. Explore

Read the project's domain glossary and any ADRs in the area you're touching first.

Walk the codebase organically. Note where you experience friction:

- Where does understanding one concept require bouncing between many small modules?
- Where are modules **shallow** — interface nearly as complex as the implementation?
- Where have pure functions been extracted just for testability, but the real bugs hide in how they're called (no **locality**)?
- Where do tightly-coupled modules leak across their seams?
- Which parts of the codebase are untested, or hard to test through their current interface?

Apply the **deletion test** to anything you suspect is shallow: would deleting it concentrate complexity, or just move it? A "yes, concentrates" is the signal you want.

### 2. Present candidates

For each candidate, document:

- **Files** — which files/modules are involved
- **Problem** — why the current architecture is causing friction
- **Solution** — plain English description of what would change
- **Benefits** — explained in terms of locality and leverage, and how tests would improve
- **Before / After** — illustrating the shallowness and the deepening
- **Recommendation strength** — one of `Strong`, `Worth exploring`, `Speculative`

Use domain vocabulary for the project (from CONTEXT.md) and the glossary vocabulary above for architecture. If the domain defines "Order," talk about "the Order intake module" — not "the FooBarHandler," and not "the Order service."

## Relationship to Other Skills

### With code-structure (service-layer pattern)

The **deep-module** vocabulary and **deletion test** identify *when* a module needs restructuring. The **service-layer** pattern provides one concrete solution: extract repeated operational mechanics into composable service functions. Use them together:

1. `improve-codebase-architecture` — find shallow modules and surface friction
2. `code-structure` — extract the repeated mechanics into a service layer

The deletion test answers "is this module earning its keep?" The service-layer migration checklist answers "how do I extract it safely?"

### With change-test-loop

During the REFACTOR phase, apply the deletion test before extracting. A module that passes the deletion test (complexity reappears across callers) is a good extraction target. A module that fails (complexity was just pass-through) should be inlined or deleted, not extracted.

### With plan

During Design Approach, consider module depth. Shallow interfaces lead to brittle tests and scattered logic. Deep interfaces create leverage and locality.

## Mental Model

```
Shallow module:                       Deep module:
┌──────────────────────┐              ┌──────────────────────┐
│ Small implementation │              │ Large implementation │
│ Complex interface    │              │ Simple interface     │
│ Caller knows details │              │ Caller just calls    │
│ Test is fragile      │              │ Test is stable       │
└──────────────────────┘              └──────────────────────┘

Deletion test → complexity reappears across N callers? → Deep ✓
Deletion test → complexity just vanishes? → Shallow (was pass-through)
```

Your architecture in one sentence: **Prefer deep modules with simple interfaces. Use the deletion test to find shallow ones. Extract seams only when two adapters prove they're real.**
