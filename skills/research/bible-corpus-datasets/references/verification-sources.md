# Independent Online Verification Sources

Use two independent sources for a Bible corpus: a **bulk dataset** for full structural +
text comparison, and a **per-verse API** to adjudicate the verses the bulk set disputes.
Neither is an authority on edition spelling — they are controls, not the standard.

## Bulk reference dataset (whole Bible, one request)

```
https://raw.githubusercontent.com/thiagobodruk/bible/master/json/en_kjv.json   # ~4.2 MB
```

Shape: `[{"abbrev": "gn", "name": "Gênesis", "chapters": [["verse 1 text", ...], ...]}, ...]`

- **Positional, not name-keyed**: index 0..38 = Old Testament (Genesis..Malachi),
  39..65 = New Testament. The `name` field is localised (Portuguese) — match books by
  index order, never by name.
- Chapters are arrays of verse strings; verse numbers are positional within a chapter.
- Its chapter and verse counts match canonical KJV exactly, which makes it a strong
  structural control.
- Its known artifacts (classify, do not treat as corpus errors): marginal notes appended
  into the verse text (`": or, JEHOVAH"`, `"therefore, etc"`, `"Heb. ..."`), dropped psalm
  superscriptions, dropped italic supplied-words, and hyphenated proper names
  (`Beer-sheba`, `Tubal-cain`, `El-paran`).
- Fetch with `urllib.request` and a normal `User-Agent`; save it beside the records so the
  comparison is re-runnable without a second download.

## Per-verse / per-chapter API

```
https://bible-api.com/Genesis%201:1?translation=kjv     # one verse
https://bible-api.com/Genesis+1?translation=kjv          # whole chapter
```

- Returns `{"reference", "verses": [{"book_name", "chapter", "verse", "text"}], "translation_name"}`.
- **A whole-book query (`/Genesis?translation=kjv`) 404s** — fetch a chapter or a verse. Do
  not plan a 929-request chapter sweep when the bulk dataset settles the structural question
  in one download.
- Use it for spot checks in a loop with ~1 s between calls; it is a free service.
- Italic supplied-words are printed without brackets and marginal notes are omitted, so
  normalise punctuation/brackets before comparing.
- Its KJV is the familiar 1769-style text: `enquire`, `razor`, `Abidah`, `counsellors`,
  `Jehovah-nissi`. A Pure-Cambridge-Edition corpus will differ on exactly those — agreeing on
  everything else is the signal that the corpus is sound.

## KJV 1769 (NT) and cross-edition numbering

`https://www.textusreceptusbibles.com/KJV1769/<book_num>/<chapter>`, book numbers 40..66, 260
chapter pages — the landing page defaults to Genesis, so read the chapter count off the nav for
the book you asked for rather than the page you landed on.

- **The KJV pages carry no text-cell class**: rows are `<td class="ref">1:1</td><td>text</td>`,
  not `td.greek`/`td.hebrew`. Extracting "the ref cell plus every other cell" covers all three
  editions with one extractor.
- **Numbering is the edition's own and differs from the Greek TR**: KJV 2 Corinthians 257,
  3 John 14, Revelation 404 — the same site's `/Stephanus` gives 256, 15 and 405 (the TR keeps
  3 John's closing greeting as a verse and carries Revelation 12:18). Never "correct" one export
  toward the other; record the delta in each `VERIFICATION.txt` so the two NT exports can be
  joined knowingly.
- **Its section title says Oxford 1769 but it keeps some pre-1769 forms** (`ax`, `lowring`,
  "an heathen", `Bar-jona`, `instructers`). Treat both a PCE file and this page as editions with
  their own spelling, and hand over the adjustment list rather than declaring a winner.
- **Epistle subscriptions are printed inside the closing verse** of every epistle (14 verses,
  Romans 16:27 .. Hebrews 13:25); the bulk dataset drops them, so they land in the residual.
- Smoke-test books for this edition: Matthew 1071, 2 Corinthians 257, 3 John 14, Revelation 404.

## Canonical totals (hard assertions)

| Corpus | Verses | Books |
|--------|--------|-------|
| Old Testament | 23,145 | 39 |
| New Testament | 7,957 | 27 |
| Whole KJV | 31,102 | 66 |

Per-book values worth asserting in a smoke test: Genesis 1533, Psalms 2461, Isaiah 1292,
Jeremiah 1364, Ezekiel 1273, Matthew 1071, Luke 1151, Acts 1007.

## Online edition URLs (Stephanus / Textus Receptus)

`https://www.textusreceptusbibles.com/<Edition>/<book_num>/<chapter>`, book numbers
40 (Matthew) .. 66 (Revelation). The landing page's `#BibleBookSelect` lists every book, and
each chapter page's nav lists that book's chapter count. Verse rows are
`table.bibletable tr > td.ref` ("1:1") and `td.greek`. Editions on the same site:
`Stephanus`, `Beza`, `Elzevir`, `Scrivener`, `KJV1611`, `KJV1769`, `Masoretic`, …

## Hebrew (Masoretic) reference — Sefaria

```
https://www.sefaria.org/api/v3/texts/<Ref>?version=hebrew     # whole book, one request
```

- `<Ref>` uses Roman numerals for the numbered books (`I Samuel`, `II Kings`, `I Chronicles`);
  the Arabic form does not resolve. Build the name map once and reuse it.
- Shape: `{"versions": [{"versionTitle": "Miqra according to the Masorah", "text": [chapter, …]}]}`
  with each chapter a list of verse strings — guard for a bare string where a list is expected.
- It follows **Hebrew versification**, so its chapter counts differ from an English-numbered
  edition (Joel 4 vs 3, Malachi 3 vs 4). Its own numbers are the reason to compare sequences.
- The text is markup-heavy: HTML spans (`<span class="mam-kq">`), entities (`&thinsp;`), the
  ketiv in parentheses and the qere in brackets *both present*, and Masorah section markers
  printed as isolated `ס` (setumah) / `פ` (petuhah). All of it inflates the reference's word
  count under naive normalisation.

## Hebrew normalisation recipe (word sequences, not verses)

```python
def words(s, drop_ketiv_qere=False):
    s = re.sub(r"<[^>]+>", " ", s); s = html.unescape(s)        # markup FIRST
    if drop_ketiv_qere:
        s = re.sub(r"\([^)]*\)", " ", s)                        # ketiv
        s = s.replace("[", " ").replace("]", " ")               # qere brackets
    s = unicodedata.normalize("NFKC", s).replace("\u05be", " ")  # maqaf -> space
    s = re.sub(r"[\u0591-\u05c7\u05f3\u05f4]", "", s)          # points: DELETE, never a space
    s = re.sub(r"[^\u05d0-\u05ea\s]", " ", s)
    return [w for w in s.split() if w and w not in ("\u05e1", "\u05e4")]  # minus ס/פ markers
```

- **Delete combining marks; never substitute a space.** `re.sub(marks, " ", s)` splits
  `אֵיכָ֣ה` into three tokens and roughly doubles the reference's word count — the symptom is a
  large uniform mismatch that reads like a corpus defect.
- **Strip HTML/entities first**, or `span`/`class` text and `&thinsp;` leak into the tokens.
- **NFKC is mandatory**: the site prints presentation forms (`שׁ` U+FB2A), the reference prints
  base letter + point.
- **Compare sequences per book**: concatenate each side's normalized words in order and use
  `difflib.SequenceMatcher(None, mine, ref).ratio()` plus `get_opcodes()` for the first few
  blocks. Versification-agnostic, and it catches a dropped word anywhere in the book.
- **Triage by direction**: an even shortfall across *every* book is a normalizer bug; a shortfall
  concentrated in one or two books is a content question — re-read that verse's raw HTML on the
  source page before blaming the extraction. Expected residual classes: ketiv/qere and
  plene/defective spelling (`ירושלם`/`ירושלים`, `פתבג`/`פת בג`, `ומשכילים`/`ומשכלים`),
  reference-only ketiv/qere duplicates and section markers, and a few genuine source readings
  (e.g. Psalms 2:4 printed without `למו`) — the last kind is the edition reading from raw HTML,
  not extraction loss.
- Per-book alignment should land in the 96–99.9 % range; below that, suspect the normalizer.
