---
name: ui
description: |
  Build or modify UI using the repository design system, existing UI patterns,
  and the correct framework skill.

  Triggers when user mentions:
  - "ui"
  - "build screen"
  - "component"
  - "frontend"
  - "layout"
  - "make it beautiful"
  - "use Design.md"
---

# UI

## Purpose
Create UI that is useful, accessible, consistent, and aligned with the project design system.

---

## Invocation

When building UI, also load `ui-strategy` for design decisions and
`design-check` for post-build audit. Load the relevant framework
skill (e.g., `tailwind`, `nextjs-app-router`, `flutter`) and
`change-test-loop` for implementation verification.

Use this as the command-level UI workflow skill. Pair it with framework skills such as `tailwind`, `bootstrap`, `nextjs-app-router`, `rails-hotwire`, `typescript`, or `flutter`.

---

## Required Reads

Before UI work, read:

1. `AGENTS.md`
2. `docs/design/DESIGN.md` if present
3. Existing nearby UI components, layouts, styles, and tokens
4. Relevant tests or stories if present

If `docs/design/DESIGN.md` is missing:

* use the nearest existing UI patterns first
* fallback to minimal accessible defaults
* report that the design source was missing

---

## Workflow

1. Identify the UI task and target files.
2. Load `docs/design/DESIGN.md`.
3. Inspect existing components and styling conventions.
4. Choose the smallest correct framework skill.
5. Plan the component hierarchy briefly.
6. Make one coherent UI change.
7. Verify with available tests, typecheck, lint, or browser/E2E checks.
8. Run `design-check` before final response when visual consistency matters.

---

## Design Rules

* Treat `docs/design/DESIGN.md` as the source of truth for visual decisions.
* Do not invent new colors, spacing, shadows, or typography unless the design file is missing or incomplete.
* Prefer existing components and tokens over one-off styling.
* Use whitespace and hierarchy before decoration.
* Keep responsive behavior explicit.
* Include accessible labels, focus states, disabled/loading/empty/error states when relevant.

---

## Output

For implementation tasks, report:

1. Files changed
2. Design system rules followed
3. Verification run
4. Anything unverified

---

## Success Criteria

* Matches `docs/design/DESIGN.md`
* Reuses repo patterns
* Responsive across expected breakpoints
* Accessible and keyboard usable
* Verified by real checks where available
