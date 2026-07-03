---
language: css
tags: [animation, motion, ux, transition]
title: Motion & Animation Patterns
description: CSS animations, transitions, prefers-reduced-motion, Framer Motion basics, performant animations
source: pattern
---

## CSS Transitions

```css
/* Simple hover transitions — only animate transform and opacity when possible */
.button {
  background: #3b82f6;
  color: white;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 0.375rem;
  cursor: pointer;
  /* Smooth, performant transitions */
  transition:
    transform 200ms ease,
    opacity 200ms ease,
    background-color 300ms ease;
  will-change: transform;
}

.button:hover {
  transform: translateY(-1px);
  opacity: 0.95;
  background: #2563eb;
}

.button:active {
  transform: translateY(0) scale(0.98);
}

/* Enter/exit transitions for modals and panels */
.overlay {
  opacity: 0;
  transition: opacity 250ms ease;
}

.overlay.open {
  opacity: 1;
}

.panel {
  transform: translateX(100%);
  transition: transform 300ms cubic-bezier(0.16, 1, 0.3, 1);
}

.panel.open {
  transform: translateX(0);
}

/* Staggered list animation */
.list-item {
  opacity: 0;
  transform: translateY(1rem);
  transition:
    opacity 400ms ease,
    transform 400ms ease;
}

.list-item:nth-child(1) { transition-delay: 0ms; }
.list-item:nth-child(2) { transition-delay: 50ms; }
.list-item:nth-child(3) { transition-delay: 100ms; }
.list-item:nth-child(4) { transition-delay: 150ms; }
.list-item.visible {
  opacity: 1;
  transform: translateY(0);
}
```

## CSS Keyframe Animations

```css
/* Fade in */
@keyframes fadeIn {
  from { opacity: 0; }
  to   { opacity: 1; }
}

/* Slide up */
@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(1.5rem);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Scale in */
@keyframes scaleIn {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

/* Shimmer / skeleton loading */
@keyframes shimmer {
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
}

/* Spin */
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Pulse */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* Usage */
.hero-section {
  animation: fadeIn 500ms ease, slideUp 600ms ease;
}

.skeleton-loader {
  background: linear-gradient(
    90deg,
    #e2e8f0 25%,
    #f8fafc 50%,
    #e2e8f0 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid #e2e8f0;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

/* Framer Motion style spring animation in CSS */
@keyframes springIn {
  0% {
    transform: scale(0);
  }
  50% {
    transform: scale(1.05);
  }
  70% {
    transform: scale(0.98);
  }
  100% {
    transform: scale(1);
  }
}

.badge {
  animation: springIn 500ms cubic-bezier(0.34, 1.56, 0.64, 1);
  /* cubic-bezier(0.34, 1.56, 0.64, 1) mimics spring( stiffness: 300, damping: 20 ) */
}
```

## prefers-reduced-motion

```css
/* Respect user's system motion preference — ALWAYS do this */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}

/* More nuanced: use reduced motion toggle */
:root {
  --motion-duration-fast: 200ms;
  --motion-duration-normal: 400ms;
  --motion-duration-slow: 600ms;
}

/* When motion is reduced, skip transforms but keep opacity */
@media (prefers-reduced-motion: reduce) {
  .card-enter {
    opacity: 0;
    transform: none; /* No slide */
    transition: opacity 300ms ease;
  }
  .card-enter.active {
    opacity: 1;
  }
}

/* Allow users to opt out of motion via a toggle */
[data-motion="reduced"] {
  --motion-enabled: 0;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.element {
  animation: fadeIn 300ms ease;
  /* Conditionally disable transforms */
  --slide-distance: 1.5rem;
  --slide-distance: calc(var(--motion-enabled, 1) * 1.5rem);
  transform: translateY(var(--slide-distance));
}
```

## Performant Animations (transform/opacity only)

```css
/* ✅ GOOD: Only animating transform and opacity (GPU-accelerated) */
.performant-card {
  transition:
    transform 300ms ease,
    opacity 300ms ease;
  transform: translateY(0);
  opacity: 1;
}

.performant-card:hover {
  transform: translateY(-4px) scale(1.02);
  opacity: 0.95;
}

/* ❌ BAD: Animating layout properties (causes expensive reflow) */
.bad-card {
  transition: all 300ms ease; /* "all" is a performance trap */
}

.bad-card:hover {
  width: 110%;        /* Triggers layout */
  height: 105%;       /* Triggers layout */
  margin-left: -5%;   /* Triggers layout */
  left: 10px;         /* Triggers layout */
  font-size: 1.2rem;  /* Triggers layout + repaint */
}

/* ✅ GOOD: Use transform instead of layout properties */
/* Instead of left/right/top/bottom, use translate */
.modal {
  /* ❌ position + left causes layout */
  /* ✅ use transform instead */
  transform: translate(-50%, -50%) scale(0.9);
  transition: transform 300ms cubic-bezier(0.16, 1, 0.3, 1);
  position: fixed;
  top: 50%;
  left: 50%;
}

.modal.open {
  transform: translate(-50%, -50%) scale(1);
}

/* Instead of width/height, use scale */
.expandable {
  transform: scaleY(0);
  transform-origin: top;
  transition: transform 300ms ease;
}

.expandable.open {
  transform: scaleY(1);
}

/* Use opacity for show/hide instead of display: none */
.dropdown {
  opacity: 0;
  pointer-events: none;
  transition:
    opacity 200ms ease,
    transform 200ms ease;
  transform: translateY(-4px);
}

.dropdown.open {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}
```

## Framer Motion Basics (React)

```jsx
import { motion, AnimatePresence } from 'framer-motion';

// Basic animated component
<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  exit={{ opacity: 0, y: -20 }}
  transition={{ duration: 0.3, ease: 'easeOut' }}
>
  Content
</motion.div>

// Spring animation
<motion.button
  whileHover={{ scale: 1.05 }}
  whileTap={{ scale: 0.95 }}
  transition={{ type: 'spring', stiffness: 400, damping: 17 }}
>
  Click me
</motion.button>

// Variants for complex animations
const variants = {
  hidden: { opacity: 0, scale: 0.8 },
  visible: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.8 },
};

<motion.div
  variants={variants}
  initial="hidden"
  animate="visible"
  exit="exit"
/>

// Staggered list animation
const container = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.1 },
  },
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 },
};

<motion.ul variants={container} initial="hidden" animate="show">
  {items.map((item, i) => (
    <motion.li key={i} variants={item}>
      {item.name}
    </motion.li>
  ))}
</motion.ul>

// AnimatePresence for enter/exit animations
<AnimatePresence mode="wait">
  {isVisible && (
    <motion.div
      key="modal"
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ duration: 0.2 }}
    >
      Modal content
    </motion.div>
  )}
</AnimatePresence>

// Layout animations (automatically animate layout changes)
<motion.div layout>
  {/* Layout animations handle position changes automatically */}
</motion.div>

// Gesture-based animations
<motion.div
  drag="x"
  dragConstraints={{ left: -100, right: 100 }}
  whileDrag={{ scale: 1.05 }}
  onDragEnd={(_, info) => {
    if (info.offset.x > 100) onSwipeRight();
  }}
>
  Swipeable card
</motion.div>
```

## Accessibility in Motion

```css
/* Always provide a motion preference hook */
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

```jsx
// In React with Framer Motion
import { useReducedMotion } from 'framer-motion';

function AnimatedComponent() {
  const prefersReducedMotion = useReducedMotion();

  return (
    <motion.div
      animate={prefersReducedMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
      initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 20 }}
      transition={{ duration: prefersReducedMotion ? 0 : 0.3 }}
    >
      Accessible animation
    </motion.div>
  );
}
```