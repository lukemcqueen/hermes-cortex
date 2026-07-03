# Known Issues — Offline Bible Prep

Found while syncing hermes-cortex `d185ea1` (June 5, 2026). Both issues below exist in the repo and need upstream fixes from Moses.

## prep-bible.sh

### Unbound variable `$tmp_txt`

**Location:** `offline/prep-bible.sh` line 189 (inside function `download_pg()`)

**Symptom:** Script crashes immediately on first download:
```
offline/prep-bible.sh: line 189: tmp_txt: unbound variable
```

**Root cause:** The function uses `$tmp_txt` on line 189 but the variable is never assigned anywhere in the function or script scope. `set -euo pipefail` at the top makes this fatal.

**Fix:** Add `local tmp_txt=$(mktemp)` before line 189, inside `download_pg()`:

```bash
local tmp_txt=$(mktemp)
if curl -sL --max-time 30 "$url" -o "$tmp_txt" 2>/dev/null; then
```

## bible-parse.py

Three format-matching issues cause KJV and WEB texts to parse incompletely or produce 0 books.

### 1. KJV book headers use colons (not commas)

**Pattern:** `THE FIRST BOOK OF MOSES,?\s*(?:CALLED\s+)?GENESIS` — expects comma or nothing before "Called"
**Actual KJV text:** `The First Book of Moses: Called Genesis` — colon, not comma

**Fix:** Change `,?\s*` to `[,:]?\s*` in all 5 Pentateuch patterns (Genesis through Deuteronomy).

```python
# Before
(r"THE FIRST BOOK OF MOSES,?\s*(?:CALLED\s+)?GENESIS", "GEN"),
# After
(r"THE FIRST BOOK OF MOSES[,:]?\s*(?:CALLED\s+)?GENESIS", "GEN"),
```

### 2. KJV NT headers use "Saint" not "St."

**Pattern:** `(?:THE\s+)?GOSPEL\s+ACCORDING\s+TO\s+(?:ST\.?\s*)?MATTHEW` — expects "St." abbreviation
**Actual KJV text:** `The Gospel According to Saint Matthew` — full word "Saint"

Affects: MAT, MRK, LUK, JHN, and REV.

**Fix:** Broaden the optional marker to accept both forms:

```python
# Before for MAT:
(r"(?:THE\s+)?GOSPEL\s+ACCORDING\s+TO\s+(?:ST\.?\s*)?MATTHEW", "MAT"),
# After:
(r"(?:THE\s+)?GOSPEL\s+ACCORDING\s+TO\s+(?:SAINT|ST\.?)?\s*MATTHEW", "MAT"),
# Same for MRK, LUK, JHN.

# Before for REV:
(r"THE REVELATION OF (?:ST\.?\s*)?JOHN(?: THE DIVINE)?", "REV"),
# After:
(r"THE REVELATION OF (?:SAINT|ST\.?)?\s*JOHN(?: THE DIVINE)?", "REV"),
```

### 3. KJV epistles use "General" prefix

**Pattern:** `THE EPISTLE OF JAMES` — expects direct "Epistle"
**Actual KJV text:** `The General Epistle of James` — has "General" before "Epistle"

Affects: James, 1/2 Peter, 1/2/3 John, Jude. Also note 1 Peter / 1 John use "Epistle General" (word order varies):
- `The General Epistle of James`
- `The First Epistle General of Peter`
- `The Second General Epistle of Peter`
- `The First Epistle General of John`
- `The Second Epistle General of John`
- `The Third Epistle General of John`
- `The General Epistle of Jude`

**Fix:** Make "General" optional in the affected patterns. Use `(?:GENERAL\s+)?` before `EPISTLE`:

```python
# Before:
(r"THE EPISTLE OF JAMES", "JAS"),
# After:
(r"THE (?:GENERAL\s+)?EPISTLE(?: GENERAL)? OF JAMES", "JAS"),
# (?:GENERAL\s+)? handles "General Epistle"
# (?: GENERAL)? handles "Epistle General"
```

For 1/2 Peter and 1/2/3 John which have both "Epistle General" and "General Epistle" word orders, a combined pattern like `(?:GENERAL\s+)?EPISTLE(?: GENERAL)?` covers both.

### 4. WEB format "Book NN Name" not recognized

**Format:** `Book 01 Genesis` followed by `001:001 In the beginning...` (3-digit chapter:verse)

No parser strategy handles this format. The `parse_pg_format` strategy doesn't match the book header, `parse_ebible_format` expects all-caps, and `parse_raw_verses` has no book detection.

**Options:**
- Add a `parse_web_format` strategy that matches `Book \d+ (\w+)` headers and `\d{3}:\d{3}` verse references
- Or add `Book \d+ GENESIS$` etc. patterns to `BOOK_PATTERNS`
- Or add an entry to `SIMPLE_BOOK_NAMES` like `r"Book \d+ (\w+)"` that captures the name

## Test files used

KJV: https://www.gutenberg.org/cache/epub/10/pg10.txt (4.4 MB after header stripping)
WEB: https://www.gutenberg.org/cache/epub/8294/pg8294.txt (4.8 MB)
ASV: https://www.gutenberg.org/cache/epub/30/pg30.txt (4.6 MB)
YLT: https://www.gutenberg.org/cache/epub/7183/pg7183.txt (547 KB)
