#!/usr/bin/env python3
"""
Hermes Cortex — Bible Text Parser
──────────────────────────────────
Converts raw Bible text files (Project Gutenberg, eBible.org, or other
plain-text formats) into structured JSON for the offline reader.

Multiple parsing strategies tried in order — the one that produces
the most valid output wins.

Usage:
    python3 bible-parse.py <input.txt> [--output <output.json>]
    python3 bible-parse.py <input.txt> --stats          # Show parse stats only
    python3 bible-parse.py <input.txt> --debug          # Verbose debug output

Output JSON format:
    {
      "meta": {"file": "...", "translation": "...", "lang": "...",
               "generated": "...", "parser": "strategy_name",
               "total_books": N, "total_chapters": N, "total_verses": N},
      "books": [
        {"abbr": "GEN", "name": "Genesis", "testament": "old",
         "chapters": [
           {"n": 1, "v": [{"n": 1, "t": "verse text"}, ...]},
           ...
         ]},
        ...
      ]
    }
"""
import json
import os
import re
import sys
import unicodedata
from datetime import datetime

# ── Canonical Book Data ────────────────────────────────────

# Standard Protestant canon: 66 books, 39 OT + 27 NT
CANON = {
    "OT": [
        ("GEN", "Genesis"), ("EXO", "Exodus"), ("LEV", "Leviticus"),
        ("NUM", "Numbers"), ("DEU", "Deuteronomy"), ("JOS", "Joshua"),
        ("JDG", "Judges"), ("RUT", "Ruth"), ("1SA", "1 Samuel"),
        ("2SA", "2 Samuel"), ("1KI", "1 Kings"), ("2KI", "2 Kings"),
        ("1CH", "1 Chronicles"), ("2CH", "2 Chronicles"), ("EZR", "Ezra"),
        ("NEH", "Nehemiah"), ("EST", "Esther"), ("JOB", "Job"),
        ("PSA", "Psalms"), ("PRO", "Proverbs"), ("ECC", "Ecclesiastes"),
        ("SON", "Song of Solomon"), ("ISA", "Isaiah"), ("JER", "Jeremiah"),
        ("LAM", "Lamentations"), ("EZK", "Ezekiel"), ("DAN", "Daniel"),
        ("HOS", "Hosea"), ("JOL", "Joel"), ("AMO", "Amos"),
        ("OBA", "Obadiah"), ("JON", "Jonah"), ("MIC", "Micah"),
        ("NAM", "Nahum"), ("HAB", "Habakkuk"), ("ZEP", "Zephaniah"),
        ("HAG", "Haggai"), ("ZEC", "Zechariah"), ("MAL", "Malachi"),
    ],
    "NT": [
        ("MAT", "Matthew"), ("MRK", "Mark"), ("LUK", "Luke"),
        ("JHN", "John"), ("ACT", "Acts"), ("ROM", "Romans"),
        ("1CO", "1 Corinthians"), ("2CO", "2 Corinthians"), ("GAL", "Galatians"),
        ("EPH", "Ephesians"), ("PHP", "Philippians"), ("COL", "Colossians"),
        ("1TH", "1 Thessalonians"), ("2TH", "2 Thessalonians"), ("1TI", "1 Timothy"),
        ("2TI", "2 Timothy"), ("TIT", "Titus"), ("PHM", "Philemon"),
        ("HEB", "Hebrews"), ("JAS", "James"), ("1PE", "1 Peter"),
        ("2PE", "2 Peter"), ("1JN", "1 John"), ("2JN", "2 John"),
        ("3JN", "3 John"), ("JUD", "Jude"), ("REV", "Revelation"),
    ],
}

# Build lookup maps
ABBR_TO_NAME = {}
NAME_TO_ABBR = {}
TESTAMENT_OF = {}
for testament, books in CANON.items():
    for abbr, name in books:
        ABBR_TO_NAME[abbr] = name
        NAME_TO_ABBR[name.lower()] = abbr
        TESTAMENT_OF[abbr] = testament.lower()

NT_ABBRS = set(a for a, _ in CANON["NT"])

# ── Book Header Patterns ───────────────────────────────────

BOOK_PATTERNS = [
    # OT Books — full header forms
    (r"THE FIRST BOOK OF MOSES[,:]?\s(?:CALLED\s+)?GENESIS", "GEN"),
    (r"THE SECOND BOOK OF MOSES[,:]?\s(?:CALLED\s+)?EXODUS", "EXO"),
    (r"THE THIRD BOOK OF MOSES[,:]?\s(?:CALLED\s+)?LEVITICUS", "LEV"),
    (r"THE FOURTH BOOK OF MOSES[,:]?\s(?:CALLED\s+)?NUMBERS", "NUM"),
    (r"THE FIFTH BOOK OF MOSES[,:]?\s(?:CALLED\s+)?DEUTERONOMY", "DEU"),
    (r"THE BOOK OF JOSHUA", "JOS"),
    (r"THE BOOK OF JUDGES", "JDG"),
    (r"THE BOOK OF RUTH", "RUT"),
    (r"THE FIRST BOOK OF SAMUEL", "1SA"),
    (r"THE SECOND BOOK OF SAMUEL", "2SA"),
    (r"THE FIRST BOOK OF THE KINGS", "1KI"),
    (r"THE SECOND BOOK OF THE KINGS", "2KI"),
    (r"THE FIRST BOOK OF THE CHRONICLES", "1CH"),
    (r"THE SECOND BOOK OF THE CHRONICLES", "2CH"),
    (r"THE BOOK OF EZRA", "EZR"),
    (r"THE BOOK OF NEHEMIAH", "NEH"),
    (r"THE BOOK OF ESTHER", "EST"),
    (r"THE BOOK OF JOB", "JOB"),
    (r"(?:THE\s+)?BOOK\s+OF\s+PSALMS?", "PSA"),
    (r"THE PSALMS?", "PSA"),
    (r"THE PROVERBS?", "PRO"),
    (r"ECCLESIASTES", "ECC"),
    (r"(?:THE\s+)?SONG\s+OF\s+SOLOMON", "SON"),
    (r"(?:THE\s+)?SONG\s+OF\s+SONGS", "SON"),
    (r"THE BOOK OF THE PROPHET ISAIAH", "ISA"),
    (r"THE BOOK OF ISAIAH", "ISA"),
    (r"THE BOOK OF THE PROPHET JEREMIAH", "JER"),
    (r"THE BOOK OF JEREMIAH", "JER"),
    (r"THE LAMENTATIONS OF JEREMIAH", "LAM"),
    (r"THE BOOK OF EZEKIEL", "EZK"),
    (r"THE BOOK OF THE PROPHET EZEKIEL", "EZK"),
    (r"THE BOOK OF DANIEL", "DAN"),
    (r"HOSEA", "HOS"),
    (r"THE BOOK OF HOSEA", "HOS"),
    (r"JOEL", "JOL"),
    (r"THE BOOK OF JOEL", "JOL"),
    (r"AMOS", "AMO"),
    (r"THE BOOK OF AMOS", "AMO"),
    (r"OBADIAH", "OBA"),
    (r"THE BOOK OF OBADIAH", "OBA"),
    (r"JONAH", "JON"),
    (r"THE BOOK OF JONAH", "JON"),
    (r"MICAH", "MIC"),
    (r"THE BOOK OF MICAH", "MIC"),
    (r"NAHUM", "NAM"),
    (r"THE BOOK OF NAHUM", "NAM"),
    (r"HABAKKUK", "HAB"),
    (r"THE BOOK OF HABAKKUK", "HAB"),
    (r"ZEPHANIAH", "ZEP"),
    (r"THE BOOK OF ZEPHANIAH", "ZEP"),
    (r"HAGGAI", "HAG"),
    (r"THE BOOK OF HAGGAI", "HAG"),
    (r"ZECHARIAH", "ZEC"),
    (r"THE BOOK OF ZECHARIAH", "ZEC"),
    (r"MALACHI", "MAL"),
    (r"THE BOOK OF MALACHI", "MAL"),
    # NT Books
    (r"(?:THE\s+)?GOSPEL\s+ACCORDING\s+TO\s+(?:SAINT|ST\.?)?\sMATTHEW", "MAT"),
    (r"(?:THE\s+)?GOSPEL\s+ACCORDING\s+TO\s+(?:SAINT|ST\.?)?\sMARK", "MRK"),
    (r"(?:THE\s+)?GOSPEL\s+ACCORDING\s+TO\s+(?:SAINT|ST\.?)?\sLUKE", "LUK"),
    (r"(?:THE\s+)?GOSPEL\s+ACCORDING\s+TO\s+(?:SAINT|ST\.?)?\sJOHN", "JHN"),
    (r"THE ACTS OF THE APOSTLES", "ACT"),
    (r"THE EPISTLE OF PAUL(?: THE APOSTLE)? TO THE ROMANS", "ROM"),
    (r"THE FIRST EPISTLE OF PAUL(?: THE APOSTLE)? TO THE CORINTHIANS", "1CO"),
    (r"THE SECOND EPISTLE OF PAUL(?: THE APOSTLE)? TO THE CORINTHIANS", "2CO"),
    (r"THE EPISTLE OF PAUL(?: THE APOSTLE)? TO THE GALATIANS", "GAL"),
    (r"THE EPISTLE OF PAUL(?: THE APOSTLE)? TO THE EPHESIANS", "EPH"),
    (r"THE EPISTLE OF PAUL(?: THE APOSTLE)? TO THE PHILIPPIANS", "PHP"),
    (r"THE EPISTLE OF PAUL(?: THE APOSTLE)? TO THE COLOSSIANS", "COL"),
    (r"THE FIRST EPISTLE OF PAUL(?: THE APOSTLE)? TO THE THESSALONIANS", "1TH"),
    (r"THE SECOND EPISTLE OF PAUL(?: THE APOSTLE)? TO THE THESSALONIANS", "2TH"),
    (r"THE FIRST EPISTLE OF PAUL(?: THE APOSTLE)? TO TIMOTHY", "1TI"),
    (r"THE SECOND EPISTLE OF PAUL(?: THE APOSTLE)? TO TIMOTHY", "2TI"),
    (r"THE EPISTLE OF PAUL(?: THE APOSTLE)? TO TITUS", "TIT"),
    (r"THE EPISTLE OF PAUL(?: THE APOSTLE)? TO PHILEMON", "PHM"),
    (r"THE EPISTLE OF PAUL(?: THE APOSTLE)? TO THE HEBREWS", "HEB"),
    (r"THE\s+(?:GENERAL\s+)?EPISTLE\s+OF\s+JAMES", "JAS"),
    (r"THE\s+FIRST\s+EPISTLE\s+(?:GENERAL\s+)?OF\s+PETER", "1PE"),
    (r"THE\s+SECOND\s+(?:GENERAL\s+)?EPISTLE\s+OF\s+PETER", "2PE"),
    (r"THE\s+FIRST\s+EPISTLE\s+(?:GENERAL\s+)?OF\s+JOHN", "1JN"),
    (r"THE\s+SECOND\s+EPISTLE\s+(?:GENERAL\s+)?OF\s+JOHN", "2JN"),
    (r"THE\s+THIRD\s+EPISTLE\s+(?:GENERAL\s+)?OF\s+JOHN", "3JN"),
    (r"THE\s+(?:GENERAL\s+)?EPISTLE\s+OF\s+JUDE", "JUD"),
    (r"THE REVELATION OF (?:SAINT|ST\.?)?\sJOHN(?: THE DIVINE)?", "REV"),
    (r"THE REVELATION OF JESUS CHRIST", "REV"),
    (r"THE REVELATION", "REV"),
]

# Compiled patterns
COMPILED_BOOK_PATTERNS = [(re.compile(p, re.IGNORECASE), a) for p, a in BOOK_PATTERNS]

# Compiled pattern for "Book NN Name" numbered headers (resolved via WEB_BOOK_NUMBERS)
BOOK_NUMBERED_RE = re.compile(r"^Book\s+(\d{1,2})\s+\w+", re.IGNORECASE)

# Simple book name matcher (for eBible format: all-caps book names)
SIMPLE_BOOK_NAMES = [
    (r"^GENESIS$", "GEN"), (r"^EXODUS$", "EXO"), (r"^LEVITICUS$", "LEV"),
    (r"^NUMBERS$", "NUM"), (r"^DEUTERONOMY$", "DEU"), (r"^JOSHUA$", "JOS"),
    (r"^JUDGES$", "JDG"), (r"^RUTH$", "RUT"),
    (r"^1\s*SAMUEL$", "1SA"), (r"^2\s*SAMUEL$", "2SA"),
    (r"^1\s*KINGS$", "1KI"), (r"^2\s*KINGS$", "2KI"),
    (r"^1\s*CHRONICLES$", "1CH"), (r"^2\s*CHRONICLES$", "2CH"),
    (r"^EZRA$", "EZR"), (r"^NEHEMIAH$", "NEH"), (r"^ESTHER$", "EST"),
    (r"^JOB$", "JOB"), (r"^PSALMS?$", "PSA"), (r"^PROVERBS?$", "PRO"),
    (r"^ECCLESIASTES$", "ECC"), (r"^SONG\s+OF\s+SOLOMON$", "SON"),
    (r"^SONG\s+OF\s+SONGS$", "SON"),
    (r"^ISAIAH$", "ISA"), (r"^JEREMIAH$", "JER"),
    (r"^LAMENTATIONS$", "LAM"), (r"^EZEKIEL$", "EZK"), (r"^DANIEL$", "DAN"),
    (r"^HOSEA$", "HOS"), (r"^JOEL$", "JOL"), (r"^AMOS$", "AMO"),
    (r"^OBADIAH$", "OBA"), (r"^JONAH$", "JON"), (r"^MICAH$", "MIC"),
    (r"^NAHUM$", "NAM"), (r"^HABAKKUK$", "HAB"), (r"^ZEPHANIAH$", "ZEP"),
    (r"^HAGGAI$", "HAG"), (r"^ZECHARIAH$", "ZEC"), (r"^MALACHI$", "MAL"),
    (r"^MATTHEW$", "MAT"), (r"^MARK$", "MRK"), (r"^LUKE$", "LUK"),
    (r"^JOHN$", "JHN"), (r"^ACTS$", "ACT"), (r"^ROMANS$", "ROM"),
    (r"^1\s*CORINTHIANS$", "1CO"), (r"^2\s*CORINTHIANS$", "2CO"),
    (r"^GALATIANS$", "GAL"), (r"^EPHESIANS$", "EPH"),
    (r"^PHILIPPIANS$", "PHP"), (r"^COLOSSIANS$", "COL"),
    (r"^1\s*THESSALONIANS$", "1TH"), (r"^2\s*THESSALONIANS$", "2TH"),
    (r"^1\s*TIMOTHY$", "1TI"), (r"^2\s*TIMOTHY$", "2TI"),
    (r"^TITUS$", "TIT"), (r"^PHILEMON$", "PHM"), (r"^HEBREWS$", "HEB"),
    (r"^JAMES$", "JAS"), (r"^1\s*PETER$", "1PE"), (r"^2\s*PETER$", "2PE"),
    (r"^1\s*JOHN$", "1JN"), (r"^2\s*JOHN$", "2JN"), (r"^3\s*JOHN$", "3JN"),
    (r"^JUDE$", "JUD"), (r"^REVELATION$", "REV"),
]

COMPILED_SIMPLE_BOOK = [(re.compile(p, re.IGNORECASE), a) for p, a in SIMPLE_BOOK_NAMES]

# WEB format book number mapping (PG #8294 World English Bible)
# Uses "Book NN Name" headers with 66-book Protestant canon order
WEB_BOOK_NUMBERS = {
    "01": "GEN", "02": "EXO", "03": "LEV", "04": "NUM", "05": "DEU",
    "06": "JOS", "07": "JDG", "08": "RUT", "09": "1SA", "10": "2SA",
    "11": "1KI", "12": "2KI", "13": "1CH", "14": "2CH", "15": "EZR",
    "16": "NEH", "17": "EST", "18": "JOB", "19": "PSA", "20": "PRO",
    "21": "ECC", "22": "SON", "23": "ISA", "24": "JER", "25": "LAM",
    "26": "EZK", "27": "DAN", "28": "HOS", "29": "JOL", "30": "AMO",
    "31": "OBA", "32": "JON", "33": "MIC", "34": "NAM", "35": "HAB",
    "36": "ZEP", "37": "HAG", "38": "ZEC", "39": "MAL",
    "40": "MAT", "41": "MRK", "42": "LUK", "43": "JHN", "44": "ACT",
    "45": "ROM", "46": "1CO", "47": "2CO", "48": "GAL", "49": "EPH",
    "50": "PHP", "51": "COL", "52": "1TH", "53": "2TH", "54": "1TI",
    "55": "2TI", "56": "TIT", "57": "PHM", "58": "HEB", "59": "JAS",
    "60": "1PE", "61": "2PE", "62": "1JN", "63": "2JN", "64": "3JN",
    "65": "JUD", "66": "REV",
}


# ── Text Cleaning ───────────────────────────────────────────

def safe_read(path):
    """Read file with encoding detection. Tries UTF-8, then Latin-1."""
    for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
        try:
            with open(path, "r", encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    # Last resort: read as bytes, replace errors
    with open(path, "rb") as f:
        raw = f.read()
    return raw.decode("utf-8", errors="replace")


def clean_text(text):
    """Normalize whitespace, remove header/footer garbage, return clean lines."""
    # Normalize unicode
    text = unicodedata.normalize("NFKC", text)

    # Remove PG headers
    text = re.sub(
        r"\*\*\* START OF (THE |THIS )?PROJECT GUTENBERG EBOOK.*?\*\*\*",
        "", text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(
        r"\*\*\* END OF (THE |THIS )?PROJECT GUTENBERG EBOOK.*",
        "", text, flags=re.DOTALL | re.IGNORECASE
    )

    # Remove common PG metadata lines
    text = re.sub(r"^Produced by .*$", "", text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r"^Transcriber'?s? Notes?:?.*$", "", text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r"^End of (the )?Project Gutenberg.*$", "", text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r"^\[Illustration:.*?\]$", "", text, flags=re.MULTILINE | re.IGNORECASE)

    lines = text.split("\n")
    cleaned = []
    for line in lines:
        # Strip and normalize spaces
        s = line.strip()
        s = re.sub(r'\s+', ' ', s)
        cleaned.append(s)

    return cleaned


def is_noise_line(line):
    """Check if a line is metadata noise that should be skipped."""
    upper = line.upper()
    noise_patterns = [
        r"^PRODUCED BY",
        r"^TRANSCRIBER'?S? NOTES?",
        r"^\[TRANSCRIBER",
        r"^\[PG",
        r"^\*\*\*",
        r"^End of (the )?(Project )?Gutenberg",
        r"^\[Illustration",
        r"^\[Picture",
        r"^\[Image",
        r"^Public Domain",
        r"^COPYRIGHT",
        r"^All rights reserved",
        r"^Language:",
        r"^Character set encoding:",
        r"^Release Date:",
        r"^\[EBook",
        r"^\[eBook",
        r"^\*\*\* START",
        r"^\*\*\* END",
    ]
    for p in noise_patterns:
        if re.match(p, upper):
            return True
    # Short lines that are just numbers or single words
    if len(line) < 4 and line.strip().isdigit():
        return True
    return False


# ── Parser Strategy 1: Full PG (+ chapter:verse) ──────────

def detect_book_header(line):
    """Check if a line is a book header. Returns abbr or None."""
    for pattern, abbr in COMPILED_BOOK_PATTERNS:
        if pattern.match(line.strip()):
            return abbr
    # Fallback: "Book NN Name" numbered header format
    bm = BOOK_NUMBERED_RE.match(line.strip())
    if bm:
        num = bm.group(1).zfill(2)
        return WEB_BOOK_NUMBERS.get(num)
    return None


def detect_simple_book(line):
    """Match simple all-caps book names (eBible format)."""
    for pattern, abbr in COMPILED_SIMPLE_BOOK:
        if pattern.match(line.strip()):
            return abbr
    return None


def parse_pg_format(text, debug=False):
    """
    Strategy 1: Full parser for Project Gutenberg style texts.
    Handles book headers, chapter markers, and verse references.
    """
    lines = clean_text(text)
    books = []
    current_book = None
    current_chapter = 0
    verses = []  # list of (book_abbr, chapter_num, verse_num, text)
    found_content = False
    skipped_to_genesis = False

    for line in lines:
        if not line:
            continue

        stripped = line.strip()
        if not stripped:
            continue

        # Skip noise
        if is_noise_line(stripped):
            continue

        # Testament headers (just markers, we track them)
        if re.match(r"THE\s+OLD\s+TESTAMENT", stripped, re.IGNORECASE):
            continue
        if re.match(r"THE\s+NEW\s+TESTAMENT", stripped, re.IGNORECASE):
            continue

        # Skip very short lines that are likely page numbers or section markers
        if len(stripped) < 3 and stripped.isdigit():
            continue

        # Book header
        abbr = detect_book_header(stripped)
        if abbr:
            if debug:
                print(f"  [PG] Book: {ABBR_TO_NAME.get(abbr, abbr)}", file=sys.stderr)
            current_book = abbr
            current_chapter = 0
            found_content = True
            continue

        # Chapter marker
        ch_match = re.match(r"(?:Chapter|Psalm)\s+(\d+)", stripped, re.IGNORECASE)
        if ch_match and current_book:
            current_chapter = int(ch_match.group(1))
            continue

        # Verse: "N:M text" or "N text" (within current chapter)
        if current_book and current_chapter > 0:
            vm = re.match(r"(\d+):(\d+)\s+(.*)", stripped)
            if vm:
                ch = int(vm.group(1))
                vs = int(vm.group(2))
                vtext = vm.group(3).strip()
                verses.append((current_book, ch, vs, vtext))
                found_content = True
                continue

        # Verse: just "N text" when we have an active chapter
        if current_book and current_chapter > 0:
            vm = re.match(r"(\d+)\s+(.*)", stripped)
            if vm:
                vs = int(vm.group(1))
                vtext = vm.group(2).strip()
                verses.append((current_book, current_chapter, vs, vtext))
                found_content = True
                continue

        # No chapter marker but "N:M" pattern — infer chapter
        if current_book and not current_chapter:
            vm = re.match(r"(\d+):(\d+)\s+(.*)", stripped)
            if vm:
                ch = int(vm.group(1))
                vs = int(vm.group(2))
                vtext = vm.group(3).strip()
                current_chapter = ch
                verses.append((current_book, ch, vs, vtext))
                found_content = True

    if not found_content or not verses:
        return None

    # Build book structures
    result = _organize_verses(verses)

    if debug:
        print(f"  [PG] Parsed: {len(result)} books, "
              f"{sum(len(b['chapters']) for b in result)} chapters, "
              f"{sum(sum(len(c['v']) for c in b['chapters']) for b in result)} verses",
              file=sys.stderr)

    return result if result else None


def parse_web_format(text, debug=False):
    """
    Strategy 2: For World English Bible (WEB) and similar PG texts
    using "Book NN Name" headers and NNN:NNN verse numbering.
    Also handles uppercase "BOOK NN NAME" variants seamlessly.
    """
    lines = clean_text(text)
    verses = []
    current_book = None
    found_book = False

    # Match "Book NN Name" (case-insensitive, captures book name)
    web_book_re = re.compile(r"^Book\s+(\d+)\s+(\w+)", re.IGNORECASE)
    # Match "NNN:NNN text" — exactly 3-digit chapter:verse, captures remaining text
    verse_re = re.compile(r"^(\d{3}):(\d{3})\s+(.*)")
    # Also accept 1–2 digit chapter:verse (e.g., 1:1 or 01:001)
    verse_re_fallback = re.compile(r"^(\d{1,2}):(\d{1,3})\s+(.*)")

    for line in lines:
        if not line:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if is_noise_line(stripped):
            continue

        # Book header: "Book NN Name"
        bm = web_book_re.match(stripped)
        if bm:
            num = bm.group(1).zfill(2)
            book_name = bm.group(2)
            if num in WEB_BOOK_NUMBERS:
                current_book = WEB_BOOK_NUMBERS[num]
                found_book = True
                if debug:
                    print(f"  [WEB] Book {num}: {ABBR_TO_NAME.get(current_book, current_book)}", file=sys.stderr)
            continue

        # Verse: try 3-digit NNN:NNN first, then fallback
        vm = verse_re.match(stripped)
        if not vm and current_book:
            vm = verse_re_fallback.match(stripped)
        if vm and current_book:
            ch = int(vm.group(1))
            vs = int(vm.group(2))
            vtext = vm.group(3).strip()
            if vtext:
                verses.append((current_book, ch, vs, vtext))
            continue

    if not found_book or not verses:
        return None

    result = _organize_verses(verses)

    if debug:
        print(f"  [WEB] Parsed: {len(result)} books, "
              f"{sum(len(b['chapters']) for b in result)} chapters, "
              f"{sum(sum(len(c['v']) for c in b['chapters']) for b in result)} verses",
              file=sys.stderr)

    return result if result else None


def parse_ebible_format(text, debug=False):
    """
    Strategy 2: For eBible.org and similar plain-text formats.
    Tries to find book names, then N:M verse patterns.
    Falls back to detecting the format by looking for all-caps book names.
    """
    lines = clean_text(text)
    books = []
    current_book = None
    verses = []
    found_book = False

    for line in lines:
        if not line:
            continue

        stripped = line.strip()
        if not stripped:
            continue

        if is_noise_line(stripped):
            continue

        # Try simple book name match (all-caps or title-case book names)
        abbr = detect_simple_book(stripped)
        if abbr:
            if debug:
                print(f"  [eBible] Book: {ABBR_TO_NAME.get(abbr, abbr)}", file=sys.stderr)
            current_book = abbr
            found_book = True
            continue

        # Try full book patterns
        abbr = detect_book_header(stripped)
        if abbr:
            if debug:
                print(f"  [eBible] Book (full): {ABBR_TO_NAME.get(abbr, abbr)}", file=sys.stderr)
            current_book = abbr
            found_book = True
            continue

        # Verse pattern
        if current_book:
            vm = re.match(r"(\d+):(\d+)\s+(.*)", stripped)
            if vm:
                ch = int(vm.group(1))
                vs = int(vm.group(2))
                vtext = vm.group(3).strip()
                verses.append((current_book, ch, vs, vtext))
                continue

            # "Chapter N" marker
            cm = re.match(r"(?:Chapter|Psalm)\s+(\d+)", stripped, re.IGNORECASE)
            if cm:
                continue  # handled by verse numbering

    if not found_book or not verses:
        return None

    result = _organize_verses(verses)

    if debug:
        print(f"  [eBible] Parsed: {len(result)} books, "
              f"{sum(len(b['chapters']) for b in result)} chapters, "
              f"{sum(sum(len(c['v']) for c in b['chapters']) for b in result)} verses",
              file=sys.stderr)

    return result if result else None


def parse_raw_verses(text, debug=False):
    """
    Strategy 3: Last resort for any text that has chapter:verse patterns
    but no book headers. Creates a single book "Scripture" with everything.
    """
    lines = clean_text(text)
    verses = []
    current_book = "GEN"
    current_chapter = 0

    for line in lines:
        if not line:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if is_noise_line(stripped):
            continue

        vm = re.match(r"(\d+):(\d+)\s+(.*)", stripped)
        if vm:
            ch = int(vm.group(1))
            vs = int(vm.group(2))
            vtext = vm.group(3).strip()
            verses.append((current_book, ch, vs, vtext))
            if ch > current_chapter:
                current_chapter = ch

    if not verses:
        return None

    result = _organize_verses(verses)

    if debug:
        print(f"  [Raw] Found {len(result)} books (all GEN), "
              f"{sum(len(b['chapters']) for b in result)} chapters, "
              f"{sum(sum(len(c['v']) for c in b['chapters']) for b in result)} verses",
              file=sys.stderr)

    return result if result else None


# ── Verse Organizer ─────────────────────────────────────────

def _organize_verses(verse_list):
    """Convert a flat list of (book_abbr, chapter, verse, text) tuples
    into the structured books/chapters/verses format."""
    if not verse_list:
        return []

    # Group by book (preserving order)
    book_order = []
    book_verses = {}  # abbr -> list of (chapter, verse, text)
    for abbr, ch, vs, vtext in verse_list:
        if abbr not in book_verses:
            book_verses[abbr] = []
            book_order.append(abbr)
        book_verses[abbr].append((ch, vs, vtext))

    result = []
    for abbr in book_order:
        name = ABBR_TO_NAME.get(abbr, abbr)
        testament = "new" if abbr in NT_ABBRS else "old"

        # Group by chapter
        chapter_data = {}
        for ch, vs, vtext in book_verses[abbr]:
            if ch not in chapter_data:
                chapter_data[ch] = []
            chapter_data[ch].append({"n": vs, "t": vtext})

        # Sort chapters by number
        chapters = []
        for ch_num in sorted(chapter_data.keys()):
            # Sort verses within chapter
            chapter_data[ch_num].sort(key=lambda x: x["n"])
            chapters.append({"n": ch_num, "v": chapter_data[ch_num]})

        result.append({
            "abbr": abbr,
            "name": name,
            "testament": testament,
            "chapters": chapters,
        })

    return result


# ── Validation ─────────────────────────────────────────────

def validate_parse(result, debug=False):
    """Validate parsed output against expected canon.
    Returns (is_valid, warnings) tuple."""
    if not result:
        return False, ["No books parsed"]

    warnings = []
    total_books = len(result)
    total_chapters = sum(len(b["chapters"]) for b in result)
    total_verses = sum(sum(len(c["v"]) for c in b["chapters"]) for b in result)

    # Check minimum viable output
    if total_books < 5:
        warnings.append(f"Only {total_books} books found (expected ~66) — likely incomplete parse")

    if total_chapters < 10:
        warnings.append(f"Only {total_chapters} chapters found — likely incomplete parse")

    if total_verses < 100:
        warnings.append(f"Only {total_verses} verses found — likely incomplete parse")

    # Check canon coverage
    parsed_abbrs = set(b["abbr"] for b in result)
    all_canon = set(a for _, a in CANON["OT"] + CANON["NT"])
    missing = all_canon - parsed_abbrs

    if missing and debug:
        warnings.append(f"Missing books: {', '.join(sorted(missing)[:10])}")
        if len(missing) > 10:
            warnings[-1] += f" (+{len(missing) - 10} more)"

    # Check for duplicates
    seen = set()
    for b in result:
        if b["abbr"] in seen:
            warnings.append(f"Duplicate book: {b['abbr']} ({b['name']})")
        seen.add(b["abbr"])

    is_valid = len(missing) < 60  # More than 60 missing means total failure
    if not is_valid:
        warnings.append("Parse fundamentally failed — too many books missing")

    return is_valid, warnings, {"books": total_books, "chapters": total_chapters, "verses": total_verses}


# ── Main ────────────────────────────────────────────────────

def detect_parser(text, debug=False):
    """Try each parser strategy in order, return the best result."""
    strategies = [
        ("pg", "Project Gutenberg format", parse_pg_format),
        ("web", "World English Bible format", parse_web_format),
        ("ebible", "eBible.org format", parse_ebible_format),
        ("raw", "Raw chapter:verse extraction", parse_raw_verses),
    ]

    results = []
    for name, desc, parser_fn in strategies:
        if debug:
            print(f"\n  Trying strategy: {name} ({desc})...", file=sys.stderr)
        try:
            result = parser_fn(text, debug=debug)
            if result:
                valid, warns, stats = validate_parse(result, debug=debug)
                if debug:
                    print(f"  Strategy '{name}': {'VALID' if valid else 'INVALID'} "
                          f"({stats['books']} books, {stats['chapters']} chapters, {stats['verses']} verses)",
                          file=sys.stderr)
                    if warns:
                        for w in warns:
                            print(f"    Warning: {w}", file=sys.stderr)
                results.append((name, result, valid, warns, stats))
            else:
                if debug:
                    print(f"  Strategy '{name}': no output", file=sys.stderr)
        except Exception as e:
            if debug:
                print(f"  Strategy '{name}': error — {e}", file=sys.stderr)

    if not results:
        return None, "none", ["No parser produced output"]

    # Score and choose best result
    # Prefer valid results with more books (closer to 66)
    valid_results = [r for r in results if r[2]]
    if valid_results:
        # Pick the one with the most books (closer to full canon)
        valid_results.sort(key=lambda r: r[4]["books"], reverse=True)
        chosen = valid_results[0]
    else:
        # Pick any result with the most verses
        results.sort(key=lambda r: r[4]["verses"], reverse=True)
        chosen = results[0]

    return chosen[1], chosen[0], chosen[3]


def parse_bible_file(input_path, debug=False):
    """Parse a Bible text file and return structured JSON data."""
    if debug:
        print(f"\nReading: {input_path}", file=sys.stderr)

    text = safe_read(input_path)
    size = len(text)
    if debug:
        print(f"  Size: {size:,} bytes ({size // 1024} KB)", file=sys.stderr)

    books, strategy, warnings = detect_parser(text, debug=debug)

    if not books:
        if debug:
            print("  ✗ All strategies failed", file=sys.stderr)
        return None

    # Compute stats
    total_books = len(books)
    total_chapters = sum(len(b["chapters"]) for b in books)
    total_verses = sum(sum(len(c["v"]) for c in b["chapters"]) for b in books)

    # Detect language from filename
    basename = os.path.basename(input_path)
    stem = os.path.splitext(basename)[0]
    lang = "en"
    parts = stem.split("_")
    if len(parts) > 1:
        code = parts[-1]
        if len(code) <= 5:
            lang = code

    # Check if it's a PG file for translation name
    translation = stem
    pg_match = re.match(r"pg(\d+)_?(.*)", stem)
    if pg_match:
        pg_id = pg_match.group(1)
        pg_labels = {"10": "King James Version (KJV)", "30": "American Standard Version (ASV)",
                     "8294": "World English Bible (WEB)", "7183": "Young's Literal Translation (YLT)"}
        translation = pg_labels.get(pg_id, f"PG #{pg_id}")

    result = {
        "meta": {
            "file": basename,
            "translation": translation,
            "lang": lang,
            "generated": datetime.now().strftime("%Y-%m-%d"),
            "parser": strategy,
            "warnings": warnings,
            "size_bytes": size,
            "total_books": total_books,
            "total_chapters": total_chapters,
            "total_verses": total_verses,
        },
        "books": books,
    }

    if debug:
        print(f"\n  ✓ Final: {strategy} — {total_books} books, "
              f"{total_chapters} chapters, {total_verses} verses", file=sys.stderr)
        if warnings:
            print(f"  ⚠ Warnings:", file=sys.stderr)
            for w in warnings:
                print(f"     · {w}", file=sys.stderr)

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Parse Bible text files into structured JSON"
    )
    parser.add_argument("input", help="Path to Bible text file")
    parser.add_argument("--output", "-o", help="Output JSON path (default: <input>.json)")
    parser.add_argument("--stats", action="store_true", help="Show parse stats only")
    parser.add_argument("--debug", "-d", action="store_true", help="Verbose debug output")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    result = parse_bible_file(args.input, debug=args.debug)
    if not result:
        print(f"Error: could not parse {args.input}", file=sys.stderr)
        sys.exit(1)

    if args.stats:
        meta = result["meta"]
        print(f"  Parser:    {meta['parser']}")
        print(f"  Books:     {meta['total_books']}")
        print(f"  Chapters:  {meta['total_chapters']}")
        print(f"  Verses:    {meta['total_verses']}")
        print(f"  Size:      {meta['size_bytes']:,} bytes")
        if meta['warnings']:
            print(f"  Warnings:  {len(meta['warnings'])}")
            for w in meta['warnings']:
                print(f"    · {w}")
        sys.exit(0)

    output = args.output or (os.path.splitext(args.input)[0] + ".json")
    with open(output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
        f.write("\n")

    meta = result["meta"]
    print(f"✓ {meta['translation']}: {meta['parser']} — {meta['total_books']} books, "
          f"{meta['total_chapters']} chapters, {meta['total_verses']} verses → {output}")
    if meta['warnings']:
        for w in meta['warnings']:
            print(f"  ⚠ {w}")


if __name__ == "__main__":
    main()
