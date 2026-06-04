---
name: tailwind
description: |
  Build and refactor UI using Tailwind CSS with consistent design tokens,
  responsive layouts, and accessible, maintainable styling.

  Triggers when user mentions:
  - "tailwind"
  - "css classes"
  - "responsive layout"
  - "ui styling"
  - "fix layout"
  - "design system"
---

# Tailwind CSS

## Purpose
Create clean, consistent, and accessible UI using:
- utility-first styling
- design tokens
- responsive patterns
- minimal custom CSS

---

## Output (STRICT ORDER)

1. **Code** (component or markup)
2. **Explanation** (≤3 sentences)
3. **Verification** (viewports + states to check)

---

## Workflow (STRICT)

1. Identify UI goal (layout, spacing, interaction)
2. Inspect existing patterns/components
3. Reuse existing tokens/classes first
4. Apply minimal Tailwind utilities
5. Ensure responsive behavior
6. Ensure accessibility (focus, contrast, labels)
7. Make one clean, readable change
8. Verify across states and breakpoints

---

## Core Rules

- Prefer existing design tokens and patterns
- Keep class lists readable and grouped
- Avoid duplication → extract components when repeated
- Do not introduce large custom CSS unless necessary
- Keep styling close to markup

---

## Layout Patterns

### Container

```html
<div class="mx-auto max-w-5xl px-4 py-8">
```

### Flex / Grid

```html
<div class="flex items-center justify-between gap-4">
<div class="grid grid-cols-1 md:grid-cols-2 gap-6">
```

---

## Responsive Rules

Use responsive prefixes intentionally:

```txt
sm: → small screens
md: → tablets
lg: → desktop
xl: → large desktop
```

Rules:

* mobile-first by default
* override progressively
* avoid conflicting classes

---

## Spacing & Sizing

* Use scale (`p-4`, `mt-6`, `gap-2`)
* Avoid arbitrary values (`px-[13px]`) unless justified
* Keep spacing consistent across components

---

## Component Extraction

Extract when:

* class list becomes long (>8–12 utilities)
* repeated pattern appears ≥2 times
* UI concept has a clear name (Card, Button, etc.)

---

## Accessibility (MANDATORY)

Always ensure:

* visible focus states (`focus:ring`, `outline`)
* sufficient color contrast
* proper labels for inputs/buttons
* semantic HTML where possible

Example:

```html
<button class="focus:outline-none focus:ring-2 focus:ring-blue-500">
```

---

## State Handling

Use state variants:

```txt
hover:
focus:
active:
disabled:
group-hover:
```

Example:

```html
<button class="bg-blue-600 hover:bg-blue-700 disabled:opacity-50">
```

---

## Dark Mode (if enabled)

Use:

```txt
dark:
```

Ensure contrast and readability.

---

## Design System Rules (ENTERPRISE)

* Align with existing tokens (colors, spacing, typography)
* Avoid introducing new arbitrary styles
* Prefer consistency over uniqueness
* Coordinate with component library (e.g., shadcn/ui)

---

## Performance

* avoid excessive conditional class logic
* prefer static class composition
* minimize runtime class generation where possible

---

## Verification

Check:

* mobile (small screen)
* tablet
* desktop
* hover/focus/active states
* disabled states
* overflow and wrapping behavior

---

## Anti-Patterns

Avoid:

* long unreadable class strings
* arbitrary values without reason
* mixing Tailwind with large custom CSS blocks
* inconsistent spacing scales
* missing focus states
* layout hacks (absolute positioning when not needed)
* styling that breaks responsiveness

---

## Final Report

```md
## Result
What changed.

## Files changed
- path: purpose

## Verification
- viewport/state: result

## Notes
Accessibility, edge cases, follow-ups
```

---

## Goal

Produce clean, consistent, responsive UI that:

* follows design system rules
* remains accessible
* is easy to maintain
* works reliably with smaller models