---
name: office-document-generation
description: "Use when producing .docx/.pdf/.md deliverables and files."
version: 1.0.0
metadata:
  hermes:
    tags: [docx, pdf, markdown, documents, deliverables, python-docx, fpdf2]
---

# Office Document Generation (.docx / .pdf / .md)

Produce polished, downloadable document deliverables — reports, briefings, resumes,
job descriptions, bios — as Word (.docx), PDF, and Markdown, and send the files in chat.

## When to Use
- The user asks for a document "as a .docx / .pdf / Word file".
- A recurring report or briefing must ship as formatted attachments.
- Any deliverable where one body of content must exist in several formats.

## Toolchain
```bash
python3 -m pip install python-docx fpdf2     # docx + pdf writers
# poppler's `pdftotext` (usually preinstalled) extracts PDF text for verification
```

## Procedure
1. **Define content once, render to every format.** Write one build script (`build_<name>.py`):
   the top holds the content as data (title, contact line, sections, bullet lists); the body
   renders that same data to `.md`, `.docx`, and `.pdf`. Never hand-edit an output — rerun the
   script so the three formats cannot drift apart.
2. **DOCX** (`python-docx`): set the `Normal` style font/margins and a section-heading helper
   (bold, colored, bottom rule via a `w:pBdr`/`w:bottom` XML snippet).
3. **PDF** (`fpdf2`): register a Unicode font first (pitfall 1), then write headings, paragraphs,
   and bullets. Set an explicit content width once and reuse it.
4. **Verify by extracting the produced files** (see Verification) — not by trusting the build log.
5. **Deliver** every file with an absolute `MEDIA:` line in the chat response.
6. **Governance**: file writes are gated — `begin_change` first; score with real numbers at
   `end_change` (a bare note may be refused — supply completeness/quality/progress, or an
   `unscored_reason`).

## Pitfalls
- **fpdf2 core fonts are Latin-1 only.** An en dash (–), em dash, curly quote, or other non-ASCII
  character raises `FPDFUnicodeEncodingException` / `UnicodeEncodeError` mid-render. Register a
  Unicode TTF and use it everywhere:
  `pdf.add_font("DejaVu", "", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")` plus the
  `-Bold` file for the `"B"` style, then `set_font("DejaVu", ...)`. DejaVu ships on most Linux
  hosts; Ubuntu/Noto TTF work too.
- **fpdf2 `multi_cell` leaves the cursor mid-line**, so the NEXT cell starts at the wrong x and
  text truncates or wraps wrongly — symptoms: `Not enough horizontal space to render a single
  character`, or a line cut down to a few words. Call `pdf.set_x(pdf.l_margin)` before every
  `multi_cell` (or pass an explicit width). For inline bold within one line, use `pdf.write()`
  for both runs, then `pdf.ln()`.
- **Uppercased section headings defeat mixed-case verification.** Headings rendered via `.upper()`
  (a common docx/PDF section style) will not match a grep for "Professional Experience" even when
  the document is correct. Verify against the UPPERCASED string, or search case-insensitively.
- **A clean build is not correct content** — always extract and grep the produced file.
- **Blank-render check**: print byte sizes (a few hundred bytes = empty/failed). For transparent
  PNGs count alpha, not colour — a white mark on transparency looks "empty" to a colour test.

## Verification
- **DOCX**: `"\n".join(p.text for p in Document(path).paragraphs)` — assert each section marker present.
- **PDF**: `pdftotext file.pdf -` (or pymupdf) — assert each marker present; magic bytes start `%PDF-`.
- **MD**: read the file and assert markers.

## Delivery in chat
- One `MEDIA:/absolute/path/file.ext` line per file; reference only files that exist.
- Telegram: `.png`/`.jpg` arrive as photos; `.docx`, `.pdf`, `.md`, `.svg` arrive as documents.
