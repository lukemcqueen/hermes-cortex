---
version: alpha
name: Hermes Cortex Dashboard
description: >-
  Dark-mode-first agent observability dashboard. Engineering precision meets
  data clarity — a Linear-inspired design system for monitoring LLM agents,
  system health, and Langfuse telemetry in one glance.
colors:
  surface:
    canvas: "#0a0e17"
    card: "#111a21"
    cardAlt: "#141d28"
    elevated: "#1a2636"
    hover: "#202d3e"
  border:
    subtle: "rgba(255,255,255,0.04)"
    standard: "rgba(255,255,255,0.07)"
    prominent: "rgba(255,255,255,0.12)"
  brand:
    indigo: "#6366f1"
    indigoDim: "#4338ca"
    indigoGlow: "rgba(99,102,241,0.12)"
    indigoText: "#818cf8"
  text:
    primary: "#f1f5f9"
    secondary: "#94a3b8"
    muted: "#64748b"
    faint: "#475569"
  status:
    green: "#22c55e"
    greenGlow: "rgba(34,197,94,0.2)"
    yellow: "#eab308"
    yellowGlow: "rgba(234,179,8,0.2)"
    red: "#ef4444"
    redGlow: "rgba(239,68,68,0.2)"
    orange: "#f97316"
  chart:
    blue: "#60a5fa"
    purple: "#a78bfa"
    teal: "#2dd4bf"
typography:
  fontFamily: >
    'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, sans-serif
  fontFamilyMono: >
    'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas,
    'Liberation Mono', 'Courier New', monospace
  display:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.02em"
  displaySub:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  cardTitle:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0.06em"
  body:
    fontFamily: Inter
    fontSize: 13px
    lineHeight: 1.5
  bodySmall:
    fontFamily: Inter
    fontSize: 12px
    lineHeight: 1.4
  data:
    fontFamily: JetBrains Mono
    fontSize: 13px
    lineHeight: 1.5
  dataSmall:
    fontFamily: JetBrains Mono
    fontSize: 11px
    lineHeight: 1.4
  metric:
    fontFamily: JetBrains Mono
    fontSize: 24px
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.02em"
  metricSmall:
    fontFamily: JetBrains Mono
    fontSize: 16px
    fontWeight: 600
    lineHeight: 1.1
rounded:
  sm: 6px
  md: 10px
  lg: 14px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
components:
  card:
    backgroundColor: "{surface.card}"
    rounded: "{rounded.lg}"
    border: "{border.standard}"
    padding: 14px
  cardHover:
    backgroundColor: "{surface.hover}"
    border: "{border.prominent}"
  statusDotUp:
    backgroundColor: "{status.green}"
    boxShadow: "0 0 0 2px {status.greenGlow}"
  statusDotDown:
    backgroundColor: "{status.yellow}"
    boxShadow: "0 0 0 2px {status.yellowGlow}"
  statusDotCritical:
    backgroundColor: "{status.red}"
    boxShadow: "0 0 0 2px {status.redGlow}"
  gaugeBar:
    rounded: 4px
    height: 10px
  buttonSubtle:
    backgroundColor: "rgba(255,255,255,0.03)"
    border: "{border.standard}"
    rounded: "{rounded.sm}"
    padding: "6px 12px"
    fontSize: 12px
    fontWeight: 500
  buttonSubtleHover:
    backgroundColor: "rgba(255,255,255,0.06)"
---
# Hermes Cortex Dashboard · Design System

## Overview

The Cortex Dashboard is the operational nerve center for the Hermes multi-agent
fleet. It surfaces agent health, Langfuse observability data, system metrics,
LLM cost trends, cron status, and session activity in a single glanceable view.
The design language is *engineering precision meets atmospheric calm* — a
dark-mode-first system where data density is managed through subtle luminance
gradations rather than color noise. Every visual decision is subordinated to
the goal: get the operator from confusion to clarity in under two seconds.

The visual DNA is inspired by Linear's ultra-precise dark UI — near-black
surfaces where structure emerges from barely-visible borders and text luminance
steps. But where Linear's brand is near-achromatic (one indigo accent punctuating
an otherwise greyscale system), Cortex uses a warmer slate palette
(`#111a21` card surfaces, `#0a0e17` canvas) with a deliberate indigo accent
(`#6366f1`) for interactive elements and data emphasis. The warmth prevents
the coldness of pure monochrome while maintaining engineering credibility.

## Colors

### Surface system — luminance stacking

Elevation is communicated through background luminance steps, not drop shadows.
On a dark canvas, shadows are invisible — so depth is encoded as progressively
lighter backgrounds:

| Level | Background | Usage |
|-------|-----------|-------|
| Canvas | `#0a0e17` | Deepest background — the page frame |
| Card | `#111a21` | Default card surfaces |
| Card Alt | `#141d28` | Alternating cards, visual rhythm |
| Elevated | `#1a2636` | Hovered cards, active panels |
| Hover | `#202d3e` | Row hover, interactive feedback |

### Border system — whisper-thin separation

Borders are semi-transparent white overlays on the surface background, creating
separation without visual noise. The opacity of a border communicates its
structural importance.

- **Subtle** (`rgba(255,255,255,0.04)`): Default card borders — barely visible,
  enough to separate cards from canvas without defining their edges.
- **Standard** (`rgba(255,255,255,0.07)`): Interactive elements — buttons,
  inputs, section dividers. Visible but quiet.
- **Prominent** (`rgba(255,255,255,0.12)`): Active states, focus indicators.

### Brand — restrained indigo

The indigo accent is reserved for interactive elements, data highlights,
and the brand mark. It is never used decoratively.

- **Indigo** (`#6366f1`): Primary interactive — links, active states, brand mark.
- **Indigo Dim** (`#4338ca`): Hover states, pressed interactions.
- **Indigo Text** (`#818cf8`): Text accent for emphasized data points.
- **Indigo Glow** (`rgba(99,102,241,0.12)`): Subtle background tint for active cards.

### Status — functional color

Status colors carry semantic meaning and are the only chromatic elements
in the dashboard chrome:

- **Green** (`#22c55e`): Service up, healthy, passing scores.
- **Yellow** (`#eab308`): Degraded, warnings, approaching thresholds.
- **Red** (`#ef4444`): Down, critical failures, errors.
- **Orange** (`#f97316`): Mixed status, partial failures.

### Text — luminance hierarchy

Text is never pure white. Each text role has a specific luminance level
that creates optical hierarchy:

- **Primary** (`#f1f5f9`): Card headings, metric values, labels.
- **Secondary** (`#94a3b8`): Body content, service names, timestamps.
- **Muted** (`#64748b`): Placeholders, captions, de-emphasized data.
- **Faint** (`#475569`): The quietest text — grid headers, structural labels.

## Typography

### Font pairing

The system uses an opinionated font pairing that separates structure from data:

- **Inter**: All structural text — card titles, labels, headers, navigation.
  Inter's clean geometric character matches the engineering precision of the tool.
  No OpenType quirks — just clean, legible, professional.

- **JetBrains Mono**: All data values — metrics, trace IDs, timestamps, percentages,
  model names, session counts. The fixed-width ensures aligned, scannable data columns.
  Its slightly wider character spacing helps distinguish `1` from `l` and `0` from `O`
  at small sizes — critical for trace IDs and session identifiers.

### Hierarchy

| Role | Font | Size | Weight | Tracking | Color | Usage |
|------|------|------|--------|----------|-------|-------|
| Display | Inter | 20px | 600 | -0.02em | Primary | Dashboard title / logo |
| Display Sub | Inter | 13px | 500 | -0.01em | Muted | Subtitle, system status |
| Card Title | Inter | 11px | 600 | 0.06em (uppercase) | Secondary | Card headings |
| Body | Inter | 13px | 400 | normal | Secondary | Service names, labels |
| Body Small | Inter | 12px | 500 | normal | Muted | Tab labels, badges |
| Data | JetBrains Mono | 13px | 400 | normal | Primary | Metrics, percentages |
| Data Small | JetBrains Mono | 11px | 400 | normal | Muted | PIDs, trace IDs |
| Metric | JetBrains Mono | 24px | 600 | -0.02em | Primary | Large stat displays |
| Metric Small | JetBrains Mono | 16px | 600 | -0.01em | Primary | Medium stat displays |

### Principles

1. **Data is monospace, structure is proportional.** This is the single most
   important rule. Everything measurable uses JetBrains Mono; everything labelled
   uses Inter. The visual distinction between "what it is" (Inter) and "how much"
   (JetBrains Mono) is instant and unconscious.

2. **Card titles are uppercase + tracked.** 11px Inter at weight 600 with
   0.06em letter-spacing creates the signature card title look. The uppercase
   signals "this is metadata / a section label" without needing icons or
   decorative elements.

3. **Metric values breathe.** Large data displays (trace counts, cost totals,
   session counts) use 24px JetBrains Mono weight 600 with -0.02em tracking.
   The negative tracking at large sizes creates the compressed, engineered feel
   of a precision instrument.

## Layout & Spacing

### Grid

The dashboard uses a 4-column CSS grid on standard viewports. Primary stat
cards occupy one column each, data-rich cards span full width, and auxiliary
panels fill remaining space. On viewports below 1100px, the grid collapses
to 2 columns. Below 640px, single column.

### Spacing scale

All spacing follows an 8px base unit: 4px, 8px, 12px, 16px, 24px, 32px.
Gaps between cards are 16px. Internal card padding is 14px (slightly tighter
than 16px for a denser data feel). Section spacing between card groups is 24px.

### Card rhythm

Cards are the atomic unit. Each card has:
- 14px internal padding
- `#111a21` background with `rgba(255,255,255,0.04)` border
- 14px border-radius (larger than typical — makes the dark canvas feel
  panoramic and the cards feel like floating panels)
- A title bar: 11px uppercase Inter 600, padded below 12px

Status bars fill the card width at the bottom when the card represents
a health/status concept.

## Elevation & Depth

On a dark canvas, drop shadows are invisible. Depth is communicated through:

1. **Background luminance stepping**: The canvas (`#0a0e17`) is the darkest point.
   Cards step up to `#111a21`. Hovered cards step up to `#202d3e`. The gradient
   creates a subtle stacking effect without visible shadows.

2. **Border opacity**: More important/recent cards get more visible borders
   (from `rgba(255,255,255,0.04)` to `rgba(255,255,255,0.07)`). The brightest
   border signals "look here first."

3. **Glow halos**: Status dots (up/down/degraded) use `box-shadow` halos at 2px
   spread with the status color at 20% opacity. This creates a subtle
   self-luminescence that draws the eye to service state changes.

There is no Material-style elevation system with z-depth shadows. Elevation
is luminance and opacity, not blur and offset.

## Shapes

### Border radius scale

| Value | Usage |
|-------|-------|
| 6px | Buttons, input fields, small indicators |
| 10px | Gauge bars, progress fills |
| 14px | Cards, panels, containers |
| 50% | Status dots, circular indicators |

All corners use consistent radius. No pill shapes (9999px) except for
extreme cases — the system favors clean, rational geometry.

## Components

### Card
- Background: `#111a21`
- Border: `1px solid rgba(255,255,255,0.04)`
- Radius: 14px
- Padding: 14px
- Title: 11px Inter weight 600, 0.06em letter-spacing, uppercase, `#94a3b8`

### Status Dot
- Width/Height: 8px
- Radius: 50%
- Up: `#22c55e` with `0 0 0 2px rgba(34,197,94,0.2)` glow
- Down: `#eab308` with `0 0 0 2px rgba(234,179,8,0.2)` glow
- Degraded/Critical: `#ef4444` with `0 0 0 2px rgba(239,68,68,0.2)` glow

### Gauge Bar
- Height: 10px
- Color fills: gradient from accent to lighter variant (indigo, green, yellow, red)
- Background track: `rgba(255,255,255,0.06)`
- Radius: 4px

### Stat Display
- Large value: 24px JetBrains Mono weight 600, -0.02em
- Label: 10px Inter weight 500, 0.04em letter-spacing, uppercase, `#64748b`
- Background: `rgba(255,255,255,0.03)` with `rgba(255,255,255,0.04)` border, 10px radius
- Padding: 12px 8px

### Model Bar
- Name column: 120px, JetBrains Mono 12px, `#94a3b8`
- Count: JetBrains Mono 13px weight 600, `#f1f5f9`
- Bar: 6px height, `rgba(255,255,255,0.06)` track, indigo fill
- Cost: JetBrains Mono 11px, `#64748b`

### Trace Row
- ID: JetBrains Mono 10px, `#64748b`
- Name: Inter 12px weight 500, `#f1f5f9`
- Timestamp: JetBrains Mono 10px, `#475569`
- Cost: JetBrains Mono 10px, `#64748b`
- Separator: `rgba(255,255,255,0.03)` border

### Service Row
- Name: Inter 12px, `#94a3b8`
- Status badge: JetBrains Mono 11px, colored by status
- Label: Inter 10px, `#475569`
- Separator: `rgba(255,255,255,0.03)` border

### Button (Subtle)
- Background: `rgba(255,255,255,0.03)`
- Border: `1px solid rgba(255,255,255,0.07)`
- Radius: 6px
- Padding: 6px 12px
- Font: Inter 12px weight 500, `#6366f1`
- Hover: background `rgba(255,255,255,0.06)`, border `rgba(255,255,255,0.12)`

## Do's and Don'ts

### Do
- Use JetBrains Mono for ALL data values — metrics, counts, percentages, IDs.
- Use Inter for ALL labels, titles, and structural text.
- Keep card titles in 11px uppercase Inter 600 with 0.06em tracking.
- Use the luminance stepping model for depth — never drop shadows on dark.
- Keep gauge fills as subtle gradients — solid fills look flat and engineered.
- Use the indigo accent sparingly — it's for interactive and data emphasis only.
- Let status colors (green/yellow/red) be the only chromatic elements in the chrome.
- Always include 2px glow halos on status dots — they need to pop against the dark.

### Don't
- Don't use pure white (`#ffffff`) for text — always use `#f1f5f9` or warmer.
- Don't mix Inter and JetBrains Mono in the same text role — the pair is for
  signal separation, not decorative variety.
- Don't use drop shadows on dark — they're invisible. Use borders and luminance.
- Don't make card titles uppercase in HTML — use `text-transform: uppercase`
  in CSS so the source text stays accessible and screen-reader friendly.
- Don't apply the indigo accent decoratively — no colored borders, decorative
  backgrounds, or ornamental use.
- Don't use pill shapes (9999px radius) for standard UI — 14px radius is the
  maximum for cards, 6px for interactive elements.
- Don't use solid gauge fills — always use `linear-gradient` for a polished look.
- Don't introduce more than 3 font sizes in any single card — maintain hierarchy.
