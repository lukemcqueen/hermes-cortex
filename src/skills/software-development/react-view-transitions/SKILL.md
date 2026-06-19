---
name: react-view-transitions
description: "Implement smooth native-browser animations between UI states using React's ViewTransition component and document.startViewTransition API. No third-party animation libraries needed. Covers shared element morphs, enter/exit, list reorder, and Next.js App Router integration."
version: 1.0.0
author: Titus (incorporating vercel-labs/agent-skills)
metadata:
  tags: [react, nextjs, animations, view-transitions, vercel]
  source: https://github.com/vercel-labs/agent-skills
---

# React View Transitions — Native Browser Animations

**Source:** Vercel Labs agent-skills (MIT). Implements smooth native-feeling animations using React's View Transition API.

## When to Animate (Priority Order)

| Priority | Pattern | What it communicates |
|----------|---------|---------------------|
| 1 | **Shared element** (`name`) | "Same thing — going deeper" |
| 2 | **Suspense reveal** | "Data loaded" |
| 3 | **List identity** (per-item `key`) | "Same items, new arrangement" |
| 4 | **State change** (`enter`/`exit`) | "Something appeared/disappeared" |
| 5 | **Route change** (layout-level) | "Going to a new place" |

**Implement ALL applicable patterns** — this is an implementation order, not a "pick one" list.

## Animation Style Selection

| Context | Animation | Why |
|---------|-----------|-----|
| Hierarchical nav (list → detail) | Type-keyed `nav-forward`/`nav-back` | Communicates spatial depth |
| Lateral nav (tab-to-tab) | `default="none"` (no animation) | No depth to communicate |
| Suspense reveal | `enter`/`exit` string props | Content arriving |
| Background refresh | `default="none"` | Silent — no animation needed |

## Core Concepts

### The `ViewTransition` Component
```jsx
import { ViewTransition } from 'react'
```
React auto-assigns `view-transition-name` and calls `startViewTransition` internally. **Never call `startViewTransition` yourself.**

### Animation Triggers
- **enter** — Element inserted during a Transition
- **exit** — Element removed during a Transition
- **update** — DOM mutations inside a `ViewTransition`
- **share** — Named VT unmounts + same `name` mounts in same Transition

**Only `startTransition`, `useDeferredValue`, or `Suspense` activate VTs.** Regular `setState` does not animate.

### Critical Placement Rule
```jsx
// CORRECT — ViewTransition is direct parent
<ViewTransition>
  <Content />
</ViewTransition>

// INCORRECT — div wraps the VT, suppressing enter/exit
<div>
  <ViewTransition>
    <Content />
  </ViewTransition>
</div>
```

## Styling with View Transition Classes

### Props
Values: `"auto"` (browser cross-fade), `"none"` (disabled), `"class-name"` (custom CSS), or `{ [type]: value }` for type-specific:
```jsx
<ViewTransition default="none" enter="slide-right" exit="slide-left">
```

### CSS Pseudo-elements
- `::view-transition-old(.class)` — outgoing snapshot
- `::view-transition-new(.class)` — incoming snapshot
- `::view-transition-group(.class)` — container
- `::view-transition-image-pair(.class)` — old + new pair

## Transition Types

Tag transitions with `addTransitionType`:
```jsx
import { addTransitionType } from 'react'
startTransition(() => {
  addTransitionType('nav-forward')
  addTransitionType('select-item')
  router.push('/detail/1')
})
```

Type-keyed animations on `enter`, `exit`, and `share`:
```jsx
<ViewTransition
  default="none"
  enter={{ 'nav-forward': 'slide-right' }}
  exit={{ 'nav-back': 'slide-left' }}
>
```

**TypeScript:** `ViewTransitionClassPerType` requires a `default` key.

## Shared Element Transitions

Same `name` on two VTs creates a shared element morph:
```jsx
// Source view
<ViewTransition name={`photo-${id}`}>
  <img src={thumb} onClick={() => startTransition(() => onSelect())} />
</ViewTransition>

// Detail view
<ViewTransition name={`photo-${id}`}>
  <img src={full} />
</ViewTransition>
```

**Key rules:**
- Only one VT with a given `name` can be mounted at a time
- Use unique names (`photo-${id}`)
- `share` takes precedence over `enter`/`exit`
- Never use fade-out exit on pages with shared morphs

## Common Patterns

### Enter/Exit
```jsx
<ViewTransition default="none" enter="fade-in" exit="fade-out">
  {show && <Content />}
</ViewTransition>
```

### List Reorder
```jsx
<ViewTransition>
  {items.map(item => (
    <ViewTransition key={item.id} default="none" enter="slide-in">
      <Item />
    </ViewTransition>
  ))}
</ViewTransition>
```

### Composing Shared Elements with List Identity
```jsx
<ViewTransition key={item.id}>
  <ViewTransition name={`photo-${item.id}`}>
    <img src={item.image} />
  </ViewTransition>
</ViewTransition>
```

## CSS Recipes

```css
/* Reduced motion — ALWAYS include */
@media (prefers-reduced-motion: reduce) {
  ::view-transition-group(*),
  ::view-transition-old(*),
  ::view-transition-new(*) {
    animation: none !important;
  }
}

/* Fade in */
@keyframes fade-in {
  from { opacity: 0; }
}
::view-transition-new(fade-in) {
  animation: 200ms fade-in ease-out;
}

/* Slide right */
@keyframes slide-right {
  from { transform: translateX(-30px); opacity: 0; }
}
::view-transition-new(slide-right) {
  animation: 250ms slide-right ease-out;
}

/* Slide left */
@keyframes slide-left {
  to { transform: translateX(30px); opacity: 0; }
}
::view-transition-old(slide-left) {
  animation: 200ms slide-left ease-in;
}

/* Scale reveal */
@keyframes scale-in {
  from { transform: scale(0.95); opacity: 0; }
}
::view-transition-new(scale-in) {
  animation: 200ms scale-in ease-out;
}
```

## Key Rules

1. **Use `default="none"` liberally** — prevents cross-interference on every transition
2. **Always pair `enter` with `exit`** — they don't have to be symmetric, but both should be present
3. **`router.back()` and browser back button don't trigger VTs** — use `router.push()` with explicit URL
4. **Nested VT limitation** — when parent exits, nested VTs don't fire their own enter/exit
5. **Always include `prefers-reduced-motion` CSS** from the CSS Recipes section above

## Availability

- **Next.js:** No need to install `react@canary` — App Router bundles it internally
- **Without Next.js:** Install `react@canary react-dom@canary`
- **Browser support:** Chromium 111+, Firefox 144+, Safari 18.2+