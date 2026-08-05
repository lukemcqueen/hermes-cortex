---
name: brand-guidelines
version: 1.0.0
description: "When the user wants to apply, document, or enforce brand guidelines for any product or company. Also use when the user mentions 'brand guidelines,' 'brand colors,' 'typography,' 'logo usage,' 'brand voice,' 'visual identity,' 'tone of voice,' 'brand standards,' 'style guide,' 'brand consistency,' or 'company design standards.' Covers color systems, typography, logo rules, imagery guidelines, and tone matrix for any brand — including Anthropic's official identity."
triggers:
  - "brand guidelines"
  - "brand identity"
  - "brand voice"
  - "brand style"
---

## When to Use
Use when creating, documenting, enforcing, or auditing a brand's visual and verbal identity: logo usage, color systems, typography, voice & tone, imagery, and application specs. Also use to produce a brand guidelines document, audit existing assets for compliance, or generate a fix list.

## Document Structure
A complete brand guidelines doc has six mandatory sections:

1. **Logo usage** — approved logo files/versions (primary, monochrome, reversed), minimum size, clearspace rule (a measurable unit — typically 2× the cap height on all sides), prohibited uses (no stretching, recoloring, shadows, gradients, rotation, or busy-background placement), and background/contrast requirements.
2. **Color palette** — for each color: name, HEX (screen), CMYK (print), and PMS/Pantone (offset print). Define primary/secondary/accent roles with usage ratios (e.g. 60/30/10), WCAG AA contrast pairs (4.5:1 minimum for text), and never-use combinations.
3. **Typography** — primary and secondary typefaces with license notes, weights, and fallback stacks; hierarchy (headline/body/caption sizes, line-height, letter-spacing); what to use when the brand font is unavailable.
4. **Voice & tone** — brand personality traits, a tone matrix by context (social vs. support vs. legal), and concrete do/don't examples.
5. **Imagery** — photography/illustration style, color grading, subject matter, iconography rules, and what is out of brand.
6. **Application specs** — spacing, layout grids, corner radii, shadow rules, and templates for key artifacts (social tiles, email headers, print, swag).

## Voice & Tone Do/Don't
| Context | Do | Don't |
|---|---|---|
| Product copy | Short, concrete verbs; benefit first | Jargon, superlatives ("best", "revolutionary") |
| Social | Conversational, warm, specific | Corporate boilerplate, hashtag stuffing |
| Error states | Acknowledge, state what happened, next step | Blame the user or vague "something went wrong" |
| Legal/Trust | Plain language, precise, no hype | Buried caveats or fine-print tricks |

## Enforcement Workflow
1. Gather the asset inventory — list every deliverable that carries the brand (site, social profiles, docs, decks, ads, packaging).
2. Audit each asset against the six sections above. Record every violation with the exact guideline reference (e.g. "Logo on slide 14 violates clearspace rule §1.3").
3. Score severity: Critical (logo/color misuse, wrong typeface), Major (voice mismatch, off-palette color), Minor (spacing, sizing).
4. Produce the fix list: asset → issue → required change → owner → due date. Track to closure.
5. Re-audit quarterly and after any rebrand or new asset template.

## Versioning
- Store guidelines as a versioned document; bump minor on clarifications, major on any color/logo/type change.
- Keep a changelog per version: date, what changed, who approved.
- When a new version ships, update all templates and re-run the enforcement audit — assets referencing the prior spec are now violations.

## Pitfalls
- Don't define colors only in HEX — print vendors need CMYK/PMS values.
- Don't skip accessibility contrast pairs; on-screen palettes that fail WCAG will be rejected at review.
- Clearspace must be a measurable rule, not "give it space."
- Enforcement without a fix list produces no change — always end an audit with assigned action items.
