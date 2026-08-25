---
name: pdf-template-match
description: "Use when matching a PDF to a reference PDF's layout."
version: 1.0.0
author: Esther + Gagan Sharma (catalog)
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [pdf, template, matching, reportlab, design, catalog]
    category: productivity
    related_skills: [pdf, ocr-and-documents, vision]
---

# PDF Template Match — Export Consistent with a Reference PDF

Turn an **input/reference PDF** into a new PDF that looks like it belongs to the
same document family — same page size, margins, grid, typography hierarchy,
color usage, header/footer treatment, and table styling — using the
169-pattern **pdf-design catalog** (vendored: `references/pdf-design.csv`, MIT,
by Gagan Sharma) to shortlist a concrete ReportLab recipe, then build and
verify visually.

Load the `pdf` skill alongside this one — its `scripts/pdf_*.py` helpers are
the inspection and build tooling this workflow calls. This skill adds the
*"match the reference"* procedure and the design catalog on top.

## When to Use

- "Export this report/letterhead/invoice in the same style as the attached PDF"
- Regenerate a document with new data but identical layout/branding
- Reproduce a client's template (their PDF is the spec — no source file needed)
- Keep a multi-page series visually consistent with a fixed reference
- NOT for scanned/image-only inputs: run `ocr-and-documents` first to get a
  text layer, or work purely from rendered pages
- NOT for pixel-perfect HTML-to-PDF (use a headless browser)

## Prerequisites

- Python 3.10+ with `pypdf`, `reportlab`, `pdfplumber`, `pypdfium2` (or
  poppler `pdftoppm`) — same stack as the `pdf` skill:
  `python -m pip install pypdf reportlab pdfplumber pypdfium2`
- The vendored catalog + search script in this skill (`scripts/catalog_search.py`,
  `references/pdf-design.csv`)

## Workflow — Inspect → Tokenize → Match → Build → Verify

### 1. Inspect the reference PDF (hard facts)

```bash
python <pdf-skill>/scripts/pdf_read.py input.pdf --meta
python <pdf-skill>/scripts/pdf_read.py input.pdf --text      # page 1 content
python <pdf-skill>/scripts/pdf_page_image.py input.pdf --pages 1-3 --dpi 150 --out-dir ref_imgs/
```

Record: page size (points), page count, rotation, encryption, fonts used
(`--meta` reports sizes/encrypted/scanned flags; fonts come from the render +
vision pass). If `likely_scanned_pages` is true, work from rendered pages only.

### 2. Extract design tokens (vision pass)

`vision_analyze` each rendered page (`ref_imgs/page-1.png` …) asking for:
- margins + content grid (columns, bands, image placement, whitespace)
- typography hierarchy (display/heading/body: serif vs sans, size contrast,
  case treatment, any rotated/sidebar text)
- color palette with roles (background, bands, accents, text)
- recurring furniture: header/footer, page numbers, rules, badges, TOC style

Write the tokens down as a compact "design brief" — you'll use it for the
catalog query AND the final build spec.

### 3. Match a catalog pattern (design direction + ReportLab recipe)

```bash
python <this-skill>/scripts/catalog_search.py "annual report editorial cover" -n 3
python <this-skill>/scripts/catalog_search.py "invoice minimal" -n 3
```

Search 2–3 keyword angles from your design brief (document type + mood +
distinctive feature). Each result row gives: **Layout Spec** (grid/margins/
bands), **Typography** (hierarchy), **Color Palette** (hex + roles),
**ReportLab Notes** (exact primitives: `BaseDocTemplate` + `PageTemplates`,
`onPage` callbacks for bands/footers, `Table` with `colWidths`, chart modules).
Shortlist 1–2 rows whose layout spec matches your reference's grid — adopt the
recipe and adapt palette hexes to the reference's actual colors.

### 4. Build with reportlab

Use the `pdf` skill's `pdf_create.py` for spec-driven builds, or write a
custom reportlab script when the reference needs onPage bands/frames/rotated
text the JSON spec can't express. Ground rules (from the catalog):

- Register a Unicode TTF (DejaVu Sans, or the reference's embedded font if
  extractable) — built-in Type1 Helvetica breaks non-ASCII glyphs
- Style every Paragraph explicitly; never rely on default styles
- Explicit `colWidths` on every Table; `repeatRows=1` for running headers
- Light backgrounds for business docs; color in bands and accents
- Match the reference's page size exactly (from `--meta`)

### 5. Verify side-by-side (never ship blind)

```bash
python <pdf-skill>/scripts/pdf_page_image.py out.pdf --pages 1-3 --dpi 150 --out-dir out_imgs/
```

Render the reference and the output at the same DPI, then `vision_analyze`
both (or a composited comparison) asking: margins aligned? heading/body scale
proportional? palette consistent? header/footer position matches? Iterate the
spec until the pages read as the same family.

## Pitfalls

- **Fonts**: the reference may use fonts you don't have (embedded subset).
  Extract with `pdffonts`-style inspection or pypdf; substitute a metric-
  compatible family (e.g. Helvetica Neue → Helvetica) and note the change.
- **Page size mismatch**: always carry the reference's exact size (points)
  into the build — a letter-vs-A4 drift silently breaks "consistent".
- **Scanned reference**: no text layer → render at 300 DPI for analysis and
  OCR if content matters; layout matching still works from images.
- **Grid, not pixels**: match margins/columns/bands, not pixel positions —
  the output uses new text content, so the *system* must match, not the bytes.
- **Color accuracy**: catalog hexes are estimates; always pull the reference's
  real palette from the vision pass and use those values.
- **Rotated text/sidebars**: reportlab needs `canvas.rotate()` inside an
  `onPage` or a custom flowable — plain Paragraph won't reproduce them.
- **Tables**: match ruling style (full/partial/none), cell padding, header
  repeat, and emphasis (bold/color on header row) from the reference.
- **Verify visually before reporting success** — text extraction can't confirm
  layout; only rendered pages can. Never report "consistent" without the
  side-by-side.

## Verification

- `pdf_read.py out.pdf --meta`: page count + size match the reference
- Side-by-side rendered pages at same DPI, reviewed with `vision_analyze`:
  margins/grid/type-scale/palette/furniture all match the reference
- Text spot-check: `pdf_read.py out.pdf --text` confirms content present
- If the reference is a form: `pdf_read.py ref.pdf --fields` and match field
  positions in the output

## Related

- `pdf` — the underlying create/read/merge/form tooling
- `ocr-and-documents` — scanned/image-only references
- Catalog attribution: `pdf-design-skill` by Gagan Sharma (MIT) — 169
  print/PDF patterns, BM25 search, ReportLab recipes
