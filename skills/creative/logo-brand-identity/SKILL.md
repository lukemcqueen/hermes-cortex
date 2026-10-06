---
name: logo-brand-identity
description: "Use when designing a logo or brand identity mark."
version: 1.0.0
metadata:
  hermes:
    tags: [logo, brand, identity, vector, svg, pillow, design]
---

# Logo & Brand Identity Design

Design a distinctive, professional logo (symbol + wordmark) and the full application set:
primary lockup, standalone symbol, monochrome, reversed, app icon, dark background, SVG masters.

## When to Use
- The user provides a brand brief and asks for a logo / visual identity.
- Any mark that must work at 16–32 px, in monochrome, engraved, and beside a wordmark.

## Core decision: code, not diffusion
Build the mark **programmatically** (SVG and/or Pillow). An image-diffusion generator cannot hold
exact geometry or render a clean wordmark, and its output fails the small-size / monochrome tests.
If no SVG rasterizer is installed (`rsvg-convert`, `inkscape`, `cairosvg`), render PNGs with
**Pillow** and also write **hand-authored SVG masters** so the identity stays vector-scalable.

## Procedure
1. **Translate the brief into 1–3 named geometric elements**, each carrying one value (e.g. outer
   hexagon = boundary/governance, inner ring = accountability, central column = steadfastness).
   Choose ONE proprietary abstraction — reject the literal/cliché iconography the brief forbids.
2. **Work in a fixed design space** (e.g. 256×256) with pure functions per shape
   (`hexagon(cx,cy,r)`, point lists). Keep geometry data separate from rendering.
3. **TDD the pure geometry**: vertex counts, symmetry, in-bounds assertions before rendering. Fast,
   and it catches coordinate slips.
4. **Anti-alias by supersampling**: draw at 4× the target size, then downscale with `Image.LANCZOS`
   (Pillow polygons are not anti-aliased).
5. **Wordmark**: a refined humanist/geometric sans (Ubuntu Sans, Noto Sans) at heavy weight,
   uppercase, generous tracking; draw glyph-by-glyph to control letter-spacing. Avoid stereotypical
   futuristic tech fonts. Pull symbol and word from one shared palette constant.
6. **Review the render with `vision_analyze`.** You cannot otherwise see your own output — ask
   specifically about geometry balance, proportion, negative space, and readability, then iterate.
   This is the highest-value step; it reliably catches a too-thin element or an empty-looking mark.
7. **Produce the full set**: primary lockup, standalone symbol, black monochrome, white reversed,
   app icon (rounded square), dark-background application, square avatar, SVG masters, and a
   one-page presentation board.
8. **Legibility strip** at 16/24/32/48/64 px. Thin inner details blur below ~32 px → ship a
   **simplified** variant (fewer elements, thicker strokes) for favicons/small app icons.
   Rule: full mark ≥32 px, simple mark below.

## Pitfalls
- **Points and tapered tips read as "rocket"/"flame".** For stability concepts prefer a flat-topped
  monolith or grounded column over a sharp spire.
- **Thin nested outlines vanish at small sizes** — always ship a simplified variant for ≤32 px.
- **A white-on-transparent mark looks "blank" to a naive ink test** (which treats white as
  background) — count alpha, not colour, when verifying.
- **Delivery**: send PNGs/SVGs with `MEDIA:` absolute paths; PNGs arrive as photos, SVG as a
  document. Always include the `.svg` master.
