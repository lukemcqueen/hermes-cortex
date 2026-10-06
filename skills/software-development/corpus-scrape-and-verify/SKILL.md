---
name: corpus-scrape-and-verify
version: 1.0.0
category: software-development
description: "Use when scraping a paginated source into verified CSVs."
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [scraping, dataset, csv, verification, provenance, completeness, text-corpus]
    related_skills: [scrapling, blocked-page-recovery, agent-ergonomic-output, change-checklist]
---

# Reference-Corpus Scraping & Verification

Build a dataset from a paginated reference source — scripture editions, statutes, standards,
catalogs, transcripts — and *prove* it faithful before delivering. Extraction is the easy half;
the completeness audit and the independent-source diff are what make the file trustworthy.

## When to use

- "scrape X and give me a CSV per <unit>", "same format as the last export", "extract corpus Y"
- Extending or re-issuing an earlier export of the same corpus
- Any request whose output is a dataset somebody else will later rely on

## Deliverable contract (state it, then honour it)

1. **One file per unit**, named `NN_Unit_Name.csv` — NN is the unit's position in canonical order,
   zero-padded so the archive sorts correctly.
2. **Stable header, exact column names the user gave**, and confirm what each column *means*.
   A column described loosely ("verse count", "index") is ambiguous between a per-unit total and
   a running ordinal — ship both variants or ask; never silently pick one.
3. **Cumulative numbering scope is part of the contract**: within the export's scope (starts at 1,
   does not restart per unit) unless told otherwise — and say so in the report.
4. **Encoding/quoting**: UTF-8 without BOM; RFC-4180 (quote only when the field contains a comma,
   quote or newline); rows sorted by (unit, sub-unit index).
5. **Ship `VERIFICATION.txt` inside the archive**: source URL pattern, scope, column meaning,
   structure-check result, text-check result, and every known quirk of that edition.

## Procedure

**Step 1 — Recon the index; never hardcode it.** Enumerate the units and their sub-unit counts from the
source's own navigation (regex the chapter/part links out of the landing page, take the max per unit).
Hardcoded counts silently encode the wrong edition or a wrong division.

**Step 2 — Prove the fetch path on ONE page.** Fetch one page twice: browser-rendered DOM and a plain
HTTP request. Compare cell-for-cell. If identical (server-rendered markup), run long extractions over
plain HTTP — it survives where long-lived browser sessions do not — with a normal browser `User-Agent`,
a matching `Referer`, and *sequential* requests. A page that needs JS must stay on the browser path.

**Step 3 — Paced walk, per-unit output, bounded chunks.**
- One request at a time; jittered delay (~0.35–1.15 s) between pages; occasional longer pause + scroll if
  driving a real browser. Politeness is a rate property, not a user-agent.
- **One output file per unit, written only when that unit completes** (atomic per unit). A killed tool
  call (harness wall-clock on long calls, dropped browser session) then costs at most one unit, which is
  simply re-fetched.
- **Chunk the tool calls** so each stays under the harness wall-clock ceiling (~150 pages per call).
- Resume safely: de-duplicate on the natural key `(unit, sub-unit, index)` before building outputs —
  re-running a partially completed chunk otherwise appends duplicates.

**Step 4 — Per-unit completeness assertion (mandatory).** Before a unit file is written, assert that
**every expected sub-unit produced rows**; after the walk, audit **every sub-unit of every unit** against
an independent division. "N rows total" is a separate check from "every expected sub-unit present with the
expected count" — run both. Re-runnable: `scripts/audit_unit_completeness.py`.

**Step 5 — Build and validate the dataset.** Sort by (unit, sub-unit, index); assign cumulative numbers;
emit the files; then **re-read every file from disk** and assert header, strictly +1 numbering, no duplicate
natural key, no empty text; then `zipfile.testzip()` on the archive.

**Step 6 — Verify structure, then text, then contested readings.** Full recipe (normalization, word-sequence
diff, second-source spot checks, raw-HTML check) in `references/verification-recipe.md`.

**Step 7 — Report evidence, not adjectives.** Totals, per-unit counts, the check that was run, and every
open quirk. If you cannot verify something, say so in the note rather than implying a clean bill.

## Pitfalls

- **A dropped unit is invisible without a per-unit assertion — a total alone hides it.** A corpus can be
  short by exactly one unit (e.g. two chapters = 23 rows) while every other unit is perfect, and the total
  still looks plausible. Chases like "this edition must merge X" are the failure mode: the merge story gets
  invented to explain a gap that was actually a silent skip.
- **Suspect the probe before the data.** Comparison code manufactures false differences faster than the
  source produces real ones: markup/entities counted as tokens, combining marks *replaced by spaces* instead
  of deleted (splitting every pointed word), ligatures breaking the tokenizer, chapter-level vs word-level
  alignment. Fix the normalizer, re-run, and only then characterise the residue.
- **Edition and versification differences are data, not corruption.** Different editions legitimately split
  or merge verse numbering, keep/drop superscription rows, modernise or archaise spellings, and omit a word
  another edition carries. Document per export; never "fix" one edition to match another.
- **Before blaming your parser for a missing word, read the source's own raw HTML for that row.** Absence in
  the parsed text is only a bug if the raw markup has it. The same test works in reverse: a string that
  appears somewhere on the page may belong to a *different* row (footnote, other verse).
- **A second, unrelated source is required before calling either side wrong.** One reference dataset's quirk
  (dropped titles, appended margin notes, duplicated variant readings) is not evidence against the corpus.
- **Re-issue means renumbering.** Inserting a missing unit shifts every cumulative number after it — rebuild
  and re-validate the whole export; never patch a file mid-way.
- **When you correct an export, correct every document that describes it** — the delivery note, the
  `VERIFICATION.txt`, and any review document you produced. Grep the corpus for the stale claim. A confident
  wrong explanation survives longer than missing data, because the next reader trusts it.
- **Verify rendered artifacts, not just generated ones.** For a PDF/report: extract the text and probe for
  each section, then render a page and *read* it. Generation succeeding proves nothing about content — a
  correction banner that stated the wrong row count passed generation and was caught only by reading the page.

## Support files

- `references/verification-recipe.md` — structural check against an independent edition, text normalization +
  word-sequence diff, second-source spot checks, integrity assertions, and the evidence-report shape.
- `scripts/audit_unit_completeness.py` — re-runnable per-unit completeness audit against an expected-counts TSV;
  exits non-zero on any missing/empty/short unit or sub-unit.
