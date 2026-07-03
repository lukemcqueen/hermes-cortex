---
language: css
tags: [css, modern, layout, design]
title: Modern CSS Patterns
description: Container queries, CSS nesting, :has(), @layer, cascade, custom properties/theming
source: pattern
---

## Container Queries

```css
/* Define a containment context */
.card-container {
  container-type: inline-size;
  container-name: card;
}

/* Query the container's width, not the viewport */
@container card (min-width: 400px) {
  .card {
    display: grid;
    grid-template-columns: 200px 1fr;
    gap: 1rem;
  }
  .card-image {
    border-radius: 0.5rem 0 0 0.5rem;
  }
}

@container card (max-width: 399px) {
  .card {
    display: flex;
    flex-direction: column;
  }
  .card-title {
    font-size: 1.25rem;
  }
}

/* Style queries — check if container has a certain style */
@container card style(--variant: featured) {
  .card {
    border: 2px solid gold;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }
}
```

## CSS Nesting

```css
.card {
  background: var(--surface);
  border-radius: 0.75rem;
  padding: 1.5rem;

  & .header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  & .title {
    font-size: 1.25rem;
    font-weight: 600;
  }

  & .body {
    margin-block: 1rem;
    line-height: 1.6;
  }

  & .footer {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    padding-block-start: 1rem;
    border-block-start: 1px solid var(--border);
  }

  /* Nesting media queries */
  @media (width < 768px) {
    padding: 1rem;

    & .title {
      font-size: 1.1rem;
    }
  }
}

/* Nesting with pseudo-classes */
.btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 0.375rem;
  cursor: pointer;

  &:hover {
    opacity: 0.9;
  }

  &:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}
```

## The :has() Selector

```css
/* Style a parent based on its children */
.card:has(img) {
  grid-template-rows: auto 1fr;
}

/* Style a form group when its input is invalid */
.form-group:has(:invalid) {
  & .error-message {
    display: block;
  }
  & input {
    border-color: var(--color-danger);
  }
}

/* Style a parent when a checkbox is checked */
.pricing-card:has(input[type="checkbox"]:checked) {
  border-color: var(--color-primary);
  background: var(--color-primary-light);
  box-shadow: 0 0 0 2px var(--color-primary);
}

/* Previous sibling styling */
label:has(+ input:focus) {
  color: var(--color-primary);
  font-weight: 600;
}

/* Multiple conditions */
.card:has(.avatar):has(.status-indicator) {
  display: grid;
  grid-template-columns: auto 1fr auto;
}

/* :has() with :not() */
.sidebar:not(:has(nav)) {
  display: none;
}

/* Quantity queries — style a container based on how many children it has */
.row:has(> :last-child:nth-child(2)) {
  & > * { flex: 1 1 50%; }
}

.row:has(> :last-child:nth-child(3)) {
  & > * { flex: 1 1 33.33%; }
}
```

## Cascade Layers (@layer)

```css
/* Define layer order — first defined = lowest priority */
@layer reset, base, components, utilities;

/* Reset layer */
@layer reset {
  *,
  *::before,
  *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }
}

/* Base layer — element defaults */
@layer base {
  html {
    font-family: system-ui, sans-serif;
    line-height: 1.5;
    color: var(--text-primary);
  }

  h1 { font-size: 2rem; }
  h2 { font-size: 1.5rem; }
  a { color: var(--color-primary); }
}

/* Components layer — reusable patterns */
@layer components {
  .card {
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    padding: 1rem;
  }
}

/* Utilities layer — highest priority overrides */
@layer utilities {
  .text-center { text-align: center; }
  .mt-4 { margin-block-start: 1rem; }
}

/* Nested layers */
@layer components {
  @layer buttons, forms, navigation;

  @layer buttons {
    .btn {
      display: inline-flex;
      align-items: center;
      padding: 0.5rem 1rem;
      border-radius: 0.375rem;
    }
  }
}

/* Layer with anonymous rules */
@layer reset {
  /* These always win over unlayered styles */
}
```

## Custom Properties & Theming

```css
:root {
  /* Color palette */
  --color-primary: #3b82f6;
  --color-primary-hover: #2563eb;
  --color-primary-light: #dbeafe;
  --color-danger: #ef4444;
  --color-success: #22c55e;
  --color-warning: #f59e0b;

  /* Surfaces */
  --surface: #ffffff;
  --surface-secondary: #f8fafc;
  --surface-tertiary: #f1f5f9;

  /* Text */
  --text-primary: #0f172a;
  --text-secondary: #475569;
  --text-muted: #94a3b8;

  /* Borders */
  --border: #e2e8f0;
  --border-light: #f1f5f9;

  /* Spacing scale */
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --space-12: 3rem;

  /* Typography */
  --font-sans: system-ui, -apple-system, sans-serif;
  --font-mono: 'SF Mono', 'Fira Code', monospace;
  --text-sm: 0.875rem;
  --text-base: 1rem;
  --text-lg: 1.125rem;
  --text-xl: 1.25rem;
  --text-2xl: 1.5rem;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.05);
  --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
  --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);

  /* Radii */
  --radius-sm: 0.25rem;
  --radius-md: 0.375rem;
  --radius-lg: 0.5rem;
  --radius-xl: 0.75rem;
}

/* Dark theme */
[data-theme="dark"] {
  --color-primary: #60a5fa;
  --color-primary-hover: #93c5fd;
  --color-primary-light: #1e3a5f;

  --surface: #0f172a;
  --surface-secondary: #1e293b;
  --surface-tertiary: #334155;

  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;

  --border: #334155;
  --border-light: #1e293b;

  --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.3);
  --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.4);
  --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.4);
}

/* Usage in components */
.card {
  background: var(--surface);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  box-shadow: var(--shadow-sm);
  font-family: var(--font-sans);
}

/* Dynamic theming with prefers-color-scheme */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme]) {
    /* Fallback when no data-theme attribute is set */
    --surface: #0f172a;
    --text-primary: #f1f5f9;
  }
}
```

## Cascade & Specificity

```css
/* Understanding the cascade order (last wins at same specificity) */
/* 1. Origin & importance: !important > animation > normal */
/* 2. Context: inline > layers > unlayered > @layer */
/* 3. Specificity: inline > id > class/attribute/pseudo > element */
/* 4. Order: later declarations override earlier ones */

/* Use :where() for zero specificity */
:where(.card) .title {
  /* :where() has 0 specificity, so .title is the only selector counted */
  font-weight: 600;
}

/* Use :is() for the highest specificity of its arguments */
:is(.card, .panel, .widget) .header {
  /* Takes the highest specificity among card, panel, widget */
  border-bottom: 1px solid var(--border);
}
```