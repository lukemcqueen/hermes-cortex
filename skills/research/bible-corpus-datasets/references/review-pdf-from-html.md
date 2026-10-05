# Findings trail as a reviewable PDF

Use when the user asks for a PDF they can review later — an issue/resolution log for a corpus
export, a verification report, a set of findings. One durable document, not chat scrollback.

## Build it

1. **Generate the document programmatically from the saved artefacts** (residual JSON, count
   JSON, comparison output). Tables written by hand drift from the data; tables built from the
   files the work actually produced cannot. Keep the raw artefacts next to the report so the
   next pass can regenerate it.
2. Author one self-contained HTML string, then convert with the weasyprint that ships in the
   Hermes venv:

   ```
   /home/esther/.hermes/hermes-agent/venv/bin/weasyprint <in.html> <out.pdf>
   ```

   There is no pandoc/xelatex on this host. A headless-browser `Page.printToPDF` is the fallback.
3. CSS that matters for a report:

   ```css
   @page { size: A4; margin: 16mm 15mm 18mm 15mm;
     @bottom-center { content: "<title> \u00b7 page " counter(page) " of " counter(pages);
                      font-size: 7.5pt; color: #666; } }
   h2 { border-bottom: 1.2pt solid #333; page-break-after: avoid; }
   .issue { border-left: 2.2pt solid #444; page-break-inside: avoid; }
   th, td { border: 0.5pt solid #999; padding: 1.1mm 1.6mm; vertical-align: top; }
   td.num { text-align: right; white-space: nowrap; }
   ```

   `page-break-before: always` on major sections; `page-break-after: avoid` on headings so a
   heading never strands at the foot of a page.
4. **Non-Latin text**: `font-family: "DejaVu Sans", "Noto Sans Hebrew", sans-serif` on the body
   plus an explicit `.he` class, and wrap Hebrew/Arabic runs in `<span dir="rtl">`. DejaVu Sans
   (already installed) covers Hebrew, so glyphs and RTL order both come out right with no font
   install; verify with the check below rather than assuming.
5. Write the final file to a durable directory (`~/Documents/<name>-<date>.pdf`). Scratch dirs are
   pruned, so a PDF left there is a PDF the user cannot find later. Keep the HTML source beside it
   when the user may want edits.

## Verify it before sending

- `pdfinfo <pdf>` — page count and page size (a 10-page A4 report renders in seconds; anything odd
  usually means an unescaped character in the HTML).
- `pdftotext <pdf> -` — probe for every section heading and for one non-Latin sample. A text layer
  containing the expected strings proves the document is complete and searchable.
- `pdftoppm -f <n> -l <n> -r 96 -png <pdf> <prefix>` then load the PNG with `vision_analyze` and ask
  specifically about (a) clipped or overflowing cells and (b) whether the non-Latin script renders
  as real glyphs in the right direction. Text extraction cannot answer either question.
- `pdffonts <pdf>` — confirm fonts are embedded (look for the Hebrew-capable family on pages that
  carry Hebrew).
- Regenerate and re-probe after every content edit: one added paragraph can push a table over a
  page boundary or strand a row.

## Shape that reviews well

Title + one-line metadata (author, date, scope, purpose) → inventory table → problems (symptom,
cause, resolution, what a future reader should watch for) → per-item findings → conventions → how
to re-verify → open items → appendices holding the row-level detail (every differing verse, every
reference list) so the body stays readable. Mark anything genuinely unresolved as unresolved, and
note in the appendix when long quotes are abbreviated by you rather than by the source. Content
that documents a decision the user made (a numbering choice, an accepted quirk) belongs here too:
it is the record that stops the same question being re-litigated next quarter.
