---
name: design-check
description: |
  Audit UI code against docs/design/DESIGN.md and repository UI conventions.

  Triggers when user mentions:
  - "design-check"
  - "audit UI"
  - "check design"
  - "visual consistency"
  - "does this match Design.md"
---

# Design Check

## Purpose
Find concrete mismatches between UI code and the project design system, then propose the smallest safe fixes.

---

## Required Reads

1. `docs/design/DESIGN.md`
2. Target UI files/components
3. Existing shared components, tokens, CSS config, theme config, or design utilities

If `docs/design/DESIGN.md` is missing, audit against existing repo patterns and clearly mark the design source as missing.

---

## Audit Checklist

Check for:

* typography scale and font usage
* color tokens and contrast
* spacing scale consistency
* layout width, alignment, grid/flex usage
* component radius, borders, shadows, and states
* accessibility: labels, roles, keyboard, focus, contrast
* responsive behavior
* rogue arbitrary values or one-off styles

---

## Workflow

1. Read the design system and target code.
2. Compare actual styles to allowed design tokens/patterns.
3. List only actionable issues.
4. Prefer minimal corrections over redesigns.
5. If asked to fix, patch the smallest set of files.
6. Verify with lint/typecheck/tests/browser checks when available.

---

## Output Format

```md
## Issues
- path: exact mismatch and why it matters

## Fixes
- exact correction

## Verification
- command/check: result

## Unverified
- anything not checked
```

---

## Rules

* Be strict and evidence-based.
* Do not suggest styles outside the design system.
* Do not redesign unrelated UI.
* Do not add libraries unless the repo already uses them or the user explicitly asks.
* Prefer consistency over novelty.
