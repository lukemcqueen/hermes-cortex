---
language: html
tags: [accessibility, a11y, wcag, inclusive]
title: Accessibility (a11y) Best Practices
description: WCAG standards, ARIA roles, keyboard navigation, focus management, color contrast, screen reader guidance
source: pattern
---

## Semantic HTML (Foundation of a11y)

```html
<!-- Use semantic elements instead of generic divs -->
<header>
  <nav aria-label="Main navigation">
    <ul>
      <li><a href="/">Home</a></li>
      <li><a href="/about">About</a></li>
    </ul>
  </nav>
</header>

<main>
  <article>
    <h1>Page Title</h1>
    <section aria-labelledby="section-heading">
      <h2 id="section-heading">Section Title</h2>
      <p>Content with proper heading hierarchy — no skipping levels.</p>
    </section>
  </article>
</main>

<footer>
  <p>&copy; 2026 Company Name</p>
</footer>
```

## ARIA Roles & Attributes

```html
<!-- Landmark roles (use semantic HTML when possible, ARIA when not) -->
<div role="banner">...</div>          <!-- Use <header> instead -->
<div role="navigation">...</div>      <!-- Use <nav> instead -->
<div role="main">...</div>            <!-- Use <main> instead -->
<div role="contentinfo">...</div>     <!-- Use <footer> instead -->

<!-- When semantic HTML isn't available -->
<div role="tablist" aria-label="Product tabs">
  <button role="tab" aria-selected="true" aria-controls="panel-1" id="tab-1">Details</button>
  <button role="tab" aria-selected="false" aria-controls="panel-2" id="tab-2">Reviews</button>
</div>
<div role="tabpanel" id="panel-1" aria-labelledby="tab-1">
  <p>Product details content.</p>
</div>
<div role="tabpanel" id="panel-2" aria-labelledby="tab-2" hidden>
  <p>Customer reviews content.</p>
</div>

<!-- Live regions for dynamic content -->
<div aria-live="polite" aria-atomic="true" class="sr-only">
  <!-- Screen reader announces changes here without interrupting -->
  Cart updated: 3 items
</div>

<div aria-live="assertive" aria-atomic="true">
  <!-- For time-critical notifications (use sparingly) -->
  Error: Please fix the form fields highlighted in red.
</div>

<!-- aria-expanded for toggleable content -->
<button aria-expanded="false" aria-controls="menu-dropdown" id="menu-button">
  Menu
</button>
<ul id="menu-dropdown" role="menu" aria-labelledby="menu-button" hidden>
  <li role="menuitem"><a href="/item1">Item 1</a></li>
  <li role="menuitem"><a href="/item2">Item 2</a></li>
</ul>
```

## Keyboard Navigation

```html
<!-- Skip link — first focusable element on page -->
<a href="#main-content" class="skip-link">Skip to main content</a>

<main id="main-content">
  <!-- Tabindex values -->
  <!-- tabindex="0": element becomes focusable in natural tab order -->
  <button tabindex="0">Focusable button</button>

  <!-- tabindex="-1": programmatically focusable but not in tab order -->
  <div tabindex="-1" id="focus-target">Focus me via JS</div>

  <!-- tabindex="1+" (avoid): creates awkward tab order -->
  <div tabindex="5">Don't do this</div>
</main>

<!-- Keyboard event handlers for custom widgets -->
<div
  role="listbox"
  aria-label="Country selector"
  tabindex="0"
  aria-activedescendant="option-1"
  onkeydown="handleListboxKeydown(event)"
>
  <div role="option" id="option-1" aria-selected="true">United States</div>
  <div role="option" id="option-2" aria-selected="false">Canada</div>
</div>

<!-- Modal focus trap — keep focus within modal -->
<div
  role="dialog"
  aria-modal="true"
  aria-labelledby="modal-title"
  tabindex="-1"
>
  <h2 id="modal-title">Confirm Action</h2>
  <p>Are you sure you want to delete this item?</p>
  <button autofocus>Cancel</button>
  <button>Delete</button>
</div>
```

## Focus Management

```html
<!-- Visible focus indicators — never remove outline without replacement -->
/* In CSS — recommended focus styles */
:focus-visible {
  outline: 2px solid #2563eb;
  outline-offset: 2px;
  border-radius: 2px;
}

/* Custom focus ring for specific components */
.button:focus-visible {
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.5);
}

/* For mouse users, hide focus ring (but keep for keyboard) */
.button:focus:not(:focus-visible) {
  outline: none;
  box-shadow: none;
}
```

```html
<!-- Focus management on route changes -->
<div id="app" role="application">
  <!-- Programmatically move focus to new content after navigation -->
  <main tabindex="-1" id="main-content" class="focus:outline-none">
    <h1>New Page Title</h1>
    <!-- Content here -->
  </main>
</div>
```

## Color Contrast

```css
/* WCAG 2.2 contrast ratios:
   AA: 4.5:1 for normal text, 3:1 for large text (≥18px bold or ≥24px)
   AAA: 7:1 for normal text, 4.5:1 for large text
*/

:root {
  /* Accessible color pairs */
  --text-primary: #1a1a1a;        /* On white: ~14.5:1 — AAA */
  --text-secondary: #4a4a4a;      /* On white: ~7.5:1 — AAA */
  --text-muted: #6b6b6b;          /* On white: ~4.8:1 — AA (not for small text) */
  --text-on-primary: #ffffff;     /* On #2563eb: ~5.2:1 — AA */

  /* Link colors */
  --link-color: #1a56db;          /* On white: ~6.5:1 — AA */
  --link-visited: #5a2d8a;        /* On white: ~5.0:1 — AA */

  /* Error states — must also meet contrast */
  --error: #b91c1c;               /* On white: ~7.5:1 — AAA */
  --error-bg: #fef2f2;           /* Background for error text */
}

/* Don't rely on color alone to convey information */
.error-message {
  color: var(--error);
  /* Include an icon or text indicator */
  &::before {
    content: "⚠ ";
  }
}
```

## Screen Reader Best Practices

```html
<!-- Screen reader only text (visually hidden, accessible) -->
<style>
  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }
</style>

<!-- Descriptive link text (never use "click here") -->
<!-- Bad -->
<a href="/download">Click here</a> to download the report.

<!-- Good -->
<a href="/download" aria-label="Download Q2 2026 report (PDF, 2.4 MB)">
  Download Q2 2026 Report
  <span class="sr-only">(PDF, 2.4 MB)</span>
</a>

<!-- Icon buttons need accessible names -->
<button aria-label="Close dialog">
  <svg aria-hidden="true" focusable="false" width="24" height="24">
    <!-- X icon path -->
  </svg>
</button>

<!-- Form field descriptions -->
<label for="email">Email address</label>
<input
  id="email"
  type="email"
  aria-describedby="email-hint"
  aria-required="true"
>
<p id="email-hint" class="sr-only">We'll never share your email.</p>

<!-- Status announcements -->
<div role="status" aria-live="polite" class="sr-only">
  Search results updated. 12 results found.
</div>

<!-- Progress indicators -->
<div
  role="progressbar"
  aria-valuenow="60"
  aria-valuemin="0"
  aria-valuemax="100"
  aria-label="Upload progress"
>
  60%
</div>
```

## Accessible Forms

```html
<form novalidate>
  <!-- Each field needs an associated label -->
  <div class="form-group">
    <label for="name">Full Name</label>
    <input
      id="name"
      type="text"
      autocomplete="name"
      aria-required="true"
      aria-describedby="name-error"
    >
    <p id="name-error" class="error" role="alert" hidden>
      Please enter your full name.
    </p>
  </div>

  <!-- Fieldset/legend for related fields -->
  <fieldset>
    <legend>Contact preference</legend>
    <label>
      <input type="radio" name="contact" value="email">
      Email
    </label>
    <label>
      <input type="radio" name="contact" value="phone">
      Phone
    </label>
  </fieldset>

  <!-- Error summary at top of form -->
  <div
    role="alert"
    aria-live="assertive"
    class="error-summary"
    tabindex="-1"
    hidden
  >
    <h2>There are 3 errors in your form</h2>
    <ul>
      <li><a href="#name">Name is required</a></li>
      <li><a href="#email">Email is invalid</a></li>
    </ul>
  </div>
</form>
```