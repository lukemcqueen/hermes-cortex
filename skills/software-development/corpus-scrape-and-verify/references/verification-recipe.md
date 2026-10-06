# Verification recipe for a scraped corpus

Four checks, in this order. Each one catches a class the others cannot.

## 1. Structure — against an INDEPENDENT edition

Per-unit chapter/part counts and per-sub-unit row counts compared unit by unit. Not a total comparison:
compare `expected[unit][subunit] == len(rows)` for every key, and compare the unit list itself (a fully
missing unit never appears in a totals-only check).

Cheap independent sources for whole corpora: a single-file open dataset (one HTTP request, whole corpus) or a
per-unit API (`/api/v3/texts/<Unit>?version=...`). Fetch once, cache to disk, then diff locally.

Expect and *record* legitimate differences: different verse division (one edition carrying an extra verse),
chapter counts that differ by design (e.g. a 4-chapter book in one tradition vs 3 in another). Counts that
differ are a finding to document, not automatically a defect.

## 2. Text — flat word-sequence diff, not verse-by-verse

Flatten both sides to a single token sequence per unit and diff. This is division-agnostic: verse-split
differences disappear, so every remaining difference is real content. `difflib.SequenceMatcher(...).ratio()`
per unit gives a headline; the opcodes give the evidence.

Normalization that matters (each of these was a false-positive generator):

```python
import re, html, unicodedata

def tokens(s, drop_variant_markup=True):
    if s is None: return []
    s = re.sub(r"<[^>]+>", " ", s); s = html.unescape(s)      # reference markup/entities
    if drop_variant_markup:
        s = re.sub(r"\([^)]*\)", " ", s)                     # parenthesised variant (ketiv-style)
        s = s.replace("[", " ").replace("]", " ")            # bracketed reading / supplied word
    s = re.sub(r"\([\d:]+\s*\)", " ", s)                    # inline numbering markers
    s = unicodedata.normalize("NFKC", s)                       # precomposed forms -> base letters
    s = s.replace("\u05be", " ")                              # maqaf joins words: make it a separator
    s = re.sub(r"[\u0591-\u05c7\u05f3\u05f4]", "", s)          # DELETE combining marks, never space them
    s = s.replace("\u00e6", "ae").replace("\u00c6", "AE")      # ligatures split the tokenizer otherwise
    s = re.sub(r"[^\w\s]", " ", s)
    return [t for t in re.split(r"\s+", s.lower()) if t]
```

Then classify the *entire* residue into named classes with counts, and quote one example per class
(variant markup only in the reference; orthography conventions of the edition; source-level readings;
reference artifacts such as appended margin notes or dropped titles). "0 differences" is a red flag —
check the probe is actually comparing anything.

## 3. Contested readings — a second source, then the raw page

For each residual, ask a *second* independent online source. Then, for anything that looks like an
omission, fetch the source page's raw HTML and inspect the row: the parsed text is only wrong if the markup
has the content. Both directions matter — a word present somewhere on the page may belong to a neighbour row.

## 4. Extraction integrity

- Re-fetch a sample page after the run and compare with the stored rows (catches post-hoc edits and drift).
- Compare a raw-HTML parse against a real-browser DOM render of the same page, cell for cell (proves the
  parser reads what a human would see).
- Re-read every emitted file from disk: header equality, cumulative column strictly +1, no duplicate natural
  key, no empty text, then `zipfile.testzip()`.

## Reporting the findings

One document, four parts: (1) pipeline problems that can recur, with symptom → cause → resolution → what to
check; (2) per-export findings, one subsection each; (3) the conventions the files follow (column meaning,
numbering scope, encoding); (4) how to re-verify, as commands. Append the row-level detail (the exact
references that differ, with both readings) so a reader never has to re-derive it.

Generate the appendices *from the saved data files*, not from memory of the run — hand-written lists drift
the moment the data is corrected.

### Rendered-artifact verification (PDF/HTML report)

```bash
weasyprint report.html report.pdf          # HTML -> PDF
pdfinfo report.pdf                          # pages, size
pdftotext report.pdf - | grep -c <section>  # text layer: probe for every section heading + key numbers
pdftoppm -f 1 -l 1 -r 96 -png report.pdf p1 # render a page, then READ the image
```

- Probe the extracted text for each section heading and each headline number — that is the cheap automated
  half.
- Render at least the first page and any page carrying non-Latin script, and read them: this catches wrong
  numbers, tofu glyphs, and RTL text rendered LTR. Pick a font known to cover the script and confirm the
  glyphs in the render rather than assuming.
- Write `dir="rtl"` on RTL runs inside LTR prose; without it the sequence renders reversed.
- When the report is corrected, re-run the probes and re-read the changed region — and fix every stale number
  in the source document, not just the one the reader noticed.
