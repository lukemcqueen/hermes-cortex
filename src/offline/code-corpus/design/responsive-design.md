---
language: css
tags: [responsive, design, mobile-first, ux]
title: Responsive Design Strategy
description: Mobile-first breakpoints, fluid typography with clamp(), image optimization, and srcset
source: pattern
---

## Mobile-First Breakpoint Strategy

```css
/* Mobile-first: base styles target smallest screens, then enhance upward */
/* Recommended breakpoints (feel free to adjust based on content, not devices) */

/* Base: mobile (default, no media query) */
.container {
  padding: 1rem;
  max-width: 100%;
}

/* Tablet (≥640px) */
@media (min-width: 640px) {
  .container {
    padding: 1.5rem;
    max-width: 640px;
  }
  .grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* Desktop (≥1024px) */
@media (min-width: 1024px) {
  .container {
    padding: 2rem;
    max-width: 1024px;
  }
  .grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

/* Wide (≥1280px) */
@media (min-width: 1280px) {
  .container {
    max-width: 1280px;
  }
  .grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

/* Use logical properties for RTL support */
@media (min-width: 768px) {
  .sidebar-layout {
    display: grid;
    grid-template-columns: 280px 1fr;
    gap: 2rem;
  }
}
```

## Fluid Typography with clamp()

```css
/* Fluid typography scale using clamp() */
/* clamp(MIN, PREFERRED, MAX) — scales between values */

:root {
  /* Fluid headings */
  --text-h1: clamp(2rem, 4vw + 1rem, 3.5rem);        /* 32px → 56px */
  --text-h2: clamp(1.5rem, 3vw + 0.75rem, 2.5rem);   /* 24px → 40px */
  --text-h3: clamp(1.25rem, 2vw + 0.5rem, 2rem);     /* 20px → 32px */
  --text-h4: clamp(1.125rem, 1.5vw + 0.5rem, 1.5rem);/* 18px → 24px */

  /* Fluid body text */
  --text-body: clamp(1rem, 1vw + 0.5rem, 1.125rem);  /* 16px → 18px */
  --text-small: clamp(0.875rem, 0.5vw + 0.5rem, 0.9375rem); /* 14px → 15px */

  /* Fluid line height */
  --leading-tight: 1.2;
  --leading-normal: 1.6;
  --leading-relaxed: 1.8;
}

/* Usage */
h1 { font-size: var(--text-h1); line-height: var(--leading-tight); }
h2 { font-size: var(--text-h2); line-height: 1.2; }
p, body { font-size: var(--text-body); line-height: var(--leading-normal); }

/* Alternative: manual clamp() for specific use cases */
.hero-title {
  font-size: clamp(2.25rem, 5vw + 1rem, 5rem);
  letter-spacing: clamp(-0.02em, -0.01vw, 0);
}

/* Fluid spacing */
.section {
  padding-block: clamp(2rem, 5vw, 5rem);
}

.card {
  padding: clamp(1rem, 2vw, 2rem);
  gap: clamp(0.75rem, 1.5vw, 1.5rem);
}
```

## Image Optimization

```css
/* Responsive images — always prevent overflow */
img {
  max-width: 100%;
  height: auto;
  display: block;
}

/* Aspect ratio containers */
.hero-image {
  aspect-ratio: 16 / 9;
  object-fit: cover;
  width: 100%;
}

.portrait-image {
  aspect-ratio: 3 / 4;
  object-fit: cover;
}

/* Art-directed cropping with object-position */
.team-photo {
  aspect-ratio: 1 / 1;
  object-fit: cover;
  object-position: center top; /* Focus on faces */
}

/* Background images with responsive sizing */
.hero {
  background-image: url('hero-mobile.webp');
  background-size: cover;
  background-position: center;
  min-height: 50vh;
}

@media (min-width: 768px) {
  .hero {
    background-image: url('hero-tablet.webp');
    min-height: 60vh;
  }
}

@media (min-width: 1024px) {
  .hero {
    background-image: url('hero-desktop.webp');
    min-height: 70vh;
  }
}

/* Lazy loading with blur-up placeholder */
.lazy-image {
  filter: blur(10px);
  transition: filter 0.3s ease;
}

.lazy-image.loaded {
  filter: blur(0);
}
```

## Responsive Images with srcset

```html
<!-- Simple srcset with width descriptors — browser picks best size -->
<img
  src="photo-800.webp"
  srcset="
    photo-400.webp 400w,
    photo-800.webp 800w,
    photo-1200.webp 1200w,
    photo-1600.webp 1600w
  "
  sizes="
    (max-width: 640px) 100vw,
    (max-width: 1024px) 50vw,
    33vw
  "
  alt="Responsive image"
  loading="lazy"
  decoding="async"
>

<!-- Art direction with <picture> — different crops per breakpoint -->
<picture>
  <source
    media="(min-width: 1024px)"
    srcset="hero-desktop.webp"
    type="image/webp"
  >
  <source
    media="(min-width: 640px)"
    srcset="hero-tablet.webp"
    type="image/webp"
  >
  <source
    srcset="hero-mobile.webp"
    type="image/webp"
  >
  <!-- Fallback for browsers that don't support webp -->
  <img
    src="hero-fallback.jpg"
    alt="Hero banner"
    loading="lazy"
    decoding="async"
    width="1200"
    height="600"
  >
</picture>

<!-- Using density descriptors for Retina displays -->
<img
  src="photo-1x.jpg"
  srcset="
    photo-1x.jpg 1x,
    photo-2x.jpg 2x,
    photo-3x.jpg 3x
  "
  alt="Retina-aware image"
  width="800"
  height="600"
>
```

## Layout Patterns

```css
/* Responsive grid with auto-fit and min() */
.responsive-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(300px, 100%), 1fr));
  gap: 1.5rem;
}

/* Sidebar that collapses on mobile */
.with-sidebar {
  display: grid;
  grid-template-columns: 1fr;
  gap: 2rem;
}

@media (min-width: 768px) {
  .with-sidebar {
    grid-template-columns: 250px 1fr;
  }
}

/* Holy grail layout (header, footer, nav, main, aside) */
.holy-grail {
  display: grid;
  grid-template-areas:
    "header"
    "nav"
    "main"
    "aside"
    "footer";
  grid-template-columns: 1fr;
  min-height: 100vh;
}

@media (min-width: 768px) {
  .holy-grail {
    grid-template-areas:
      "header header header"
      "nav    main   aside"
      "footer footer footer";
    grid-template-columns: 200px 1fr 200px;
  }
}

.header { grid-area: header; }
.nav { grid-area: nav; }
.main { grid-area: main; }
.aside { grid-area: aside; }
.footer { grid-area: footer; }
```