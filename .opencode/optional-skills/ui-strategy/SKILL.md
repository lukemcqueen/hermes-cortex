---
name: ui-strategy
description: |
  Choose and apply the right UI system across Tailwind, Bootstrap,
  shadcn/ui, custom CSS, and design-system patterns.

  Triggers when user mentions:
  - "ui strategy"
  - "make it beautiful"
  - "improve design"
  - "tailwind or bootstrap"
  - "gorgeous UI"
  - "design system"
---

# UI Strategy

## Purpose
Choose the best UI approach and produce clean, beautiful, accessible interfaces.

Use for:
- Tailwind
- Bootstrap
- shadcn/ui
- component systems
- responsive layouts
- design polish
- enterprise UI consistency

---

## Core Rule

Use the project’s existing UI system first.

Do not mix Tailwind, Bootstrap, and custom CSS unless the repo already does.

---

## Decision Order

1. Existing project components
2. Existing design tokens
3. Current CSS framework
4. Component library
5. Minimal custom CSS

---

## Framework Selection

### Use Tailwind when:
- app already uses Tailwind
- custom modern UI is needed
- shadcn/ui is available
- design system flexibility matters

### Use Bootstrap when:
- app already uses Bootstrap
- rapid admin/internal UI is needed
- legacy Rails/server-rendered UI exists
- consistency matters more than uniqueness

### Use shadcn/ui when:
- project uses Tailwind
- polished modern components are needed
- forms, dialogs, tables, cards, dashboards are required

### Use custom CSS only when:
- existing framework cannot solve it cleanly
- design token or animation requires it
- utility classes become unreadable

---

## Gorgeous UI Rules

Good UI should feel:
- clean
- calm
- premium
- spacious
- consistent
- easy to scan

Use:
- strong visual hierarchy
- generous spacing
- soft borders
- subtle shadows
- rounded corners
- clear typography
- restrained color
- responsive layout
- polished empty/loading/error states

Avoid:
- clutter
- too many colors
- tiny spacing
- weak contrast
- inconsistent radius/shadows
- decorative complexity without purpose

---

## Layout Defaults

Prefer:
- max-width containers
- grid-based layout
- cards for grouped content
- clear section headers
- consistent spacing scale

Example layout direction:

```txt
page shell
→ header
→ summary cards
→ main content grid
→ secondary actions
→ footer/help state
```

---

## Component Quality Checklist

Every UI should include:

* responsive layout
* accessible labels
* visible focus states
* hover/active/disabled states
* loading state
* empty state
* error state
* consistent spacing
* readable typography

---

## Enterprise UI Rules

* Reuse shared components
* Avoid one-off styles
* Keep design tokens centralized
* Preserve accessibility
* Make UI maintainable, not just pretty
* Do not introduce new libraries without need

---

## Refactoring Rules

When improving UI:

1. Preserve behavior
2. Improve structure first
3. Improve spacing/layout
4. Improve typography
5. Improve states
6. Verify responsiveness

---

## Output (STRICT ORDER)

1. **UI Strategy**

   * chosen framework
   * reason
2. **Code**
3. **Design Notes** ≤5 bullets
4. **Verification**

   * viewport/state checks

---

## Verification

Check:

* mobile
* tablet
* desktop
* hover/focus/disabled states
* empty/loading/error states
* contrast/readability

---

## Anti-Patterns

Avoid:

* mixing UI frameworks unnecessarily
* redesigning unrelated screens
* adding heavy libraries casually
* custom CSS sprawl
* inaccessible visual-only controls
* beauty that reduces usability

---

## Goal

Produce UI that is:

* beautiful
* accessible
* consistent
* responsive
* maintainable
* aligned with the existing codebase