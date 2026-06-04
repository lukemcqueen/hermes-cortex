---
name: bootstrap
description: |
  Build and refactor UI using Bootstrap with consistent layout,
  components, and accessible patterns.

  Triggers when user mentions:
  - "bootstrap"
  - "bootstrap layout"
  - "grid system"
  - "navbar"
  - "form styling"
  - "bootstrap refactor"
---

# Bootstrap

## Purpose
Create clean, consistent UI using:
- Bootstrap grid system
- built-in components
- minimal custom CSS
- accessible patterns

---

## Output (STRICT ORDER)

1. **Code** (HTML/JSX)
2. **Explanation** (≤3 sentences)
3. **Verification** (viewport + interaction checks)

---

## Workflow (STRICT)

1. Identify UI goal (layout, component, form, etc.)
2. Use Bootstrap components first
3. Apply grid system for layout
4. Avoid unnecessary custom CSS
5. Ensure responsiveness
6. Ensure accessibility
7. Make one clean, minimal change
8. Verify across breakpoints

---

## Core Rules

- Prefer Bootstrap classes over custom CSS
- Use built-in components before building new ones
- Keep markup clean and readable
- Avoid mixing multiple CSS systems (e.g., Tailwind + Bootstrap)
- Keep consistent spacing and structure

---

## Layout (Grid System)

Use container + rows + columns:

```html
<div class="container">
  <div class="row">
    <div class="col-12 col-md-6">
      Content
    </div>
  </div>
</div>
```

### Rules

* mobile-first layout
* use `col-*`, `col-md-*`, `col-lg-*`
* avoid unnecessary nesting

---

## Common Components

### Button

```html
<button class="btn btn-primary">Submit</button>
```

### Form

```html
<input class="form-control" type="text" placeholder="Enter name">
```

### Card

```html
<div class="card">
  <div class="card-body">Content</div>
</div>
```

### Navbar

```html
<nav class="navbar navbar-expand-lg navbar-light bg-light">
```

---

## Spacing

Use spacing utilities:

```txt
m-*, p-*, mt-*, mb-*, mx-*, py-*
```

Example:

```html
<div class="mt-4 mb-2 px-3">
```

Avoid custom margins unless necessary.

---

## Responsive Rules

Use breakpoints:

```txt
sm, md, lg, xl, xxl
```

Example:

```html
<div class="col-12 col-md-6 col-lg-4">
```

---

## Accessibility (MANDATORY)

Ensure:

* labels for inputs
* proper button roles
* aria attributes where needed
* visible focus states
* semantic HTML structure

---

## JavaScript Behavior

Use Bootstrap JS only when needed:

* modals
* dropdowns
* collapse
* tooltips

Avoid unnecessary JS for simple UI.

---

## Refactoring Rules

* Replace custom CSS with Bootstrap utilities
* Simplify layout using grid
* Extract repeated components
* Keep markup minimal
* Avoid large rewrites

---

## Enterprise Rules

* follow consistent component usage
* align with design system if present
* avoid inline styles
* keep styles predictable and maintainable
* do not override Bootstrap globally without reason

---

## Verification

Check:

* mobile layout
* tablet layout
* desktop layout
* forms and inputs
* interactive components (dropdowns, modals)
* overflow and alignment

---

## Anti-Patterns

Avoid:

* mixing Tailwind + Bootstrap
* excessive custom CSS overrides
* deeply nested grid structures
* inline styles
* inconsistent spacing
* missing accessibility attributes
* using Bootstrap JS unnecessarily

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
Accessibility, layout issues, follow-ups
```

---

## Goal

Produce clean, responsive, accessible UI using Bootstrap that:

* is fast to implement
* easy to maintain
* consistent across the application
* reliable for enterprise use