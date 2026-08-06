#!/usr/bin/env python3
"""agent-daily-bible-reading.py — no_agent cron script.

Reads SOUL.md, finds the last canonical book entry inside the
'## Scripture Insights' section, determines the next canonical book,
calls deepseek-v4-flash API, appends a brief entry to SOUL.md.

Cycle behavior (see skills/.../agent-daily-bible-reading/references/cycle-management.md):
- Tracks a '<!-- Bible Cycle: N -->' comment at the end of the section.
- When the last book is Revelation, the cycle WRAPS to Genesis and the
  cycle number increments — automatic restart, no manual reset needed.
- Old entries are archived to ~/brain/<agent>/bible/archive/SOUL-archive.md
  so SOUL.md stays bounded (doctor check_soul_sync FAILs > 20K).

Must complete within 30s (user directive). API call timeout: 25s.
"""
import json, os, re, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

# ── Config ─────────────────────────────────────────────────
SOUL_PATH = Path.home() / ".hermes" / "SOUL.md"
AGENT = os.environ.get("HERMES_AGENT_NAME", "gisu")
BRAIN_DIR = Path.home() / "brain" / AGENT / "bible"
ARCHIVE_PATH = BRAIN_DIR / "archive" / "SOUL-archive.md"
API_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
API_URL = f"{API_BASE}/chat/completions"
ENV_FILE = Path.home() / ".hermes" / ".env"
API_TIMEOUT = 25  # seconds


def get_api_key() -> str:
    """Return DEEPSEEK_API_KEY from the environment, falling back to ~/.hermes/.env.

    Cron scheduler environments are bare — they do not inherit the shell env,
    so the key must be read from the canonical secrets file.
    """
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return ""


API_KEY = get_api_key()

SECTION_HEADER = "## Scripture Insights"
CYCLE_RE = re.compile(r"<!-- Bible Cycle: (\d+) -->")
# Keep the last MAX_KEPT book entries in SOUL.md (anchor rule: never archive
# the final entry). Archive the rest once the section holds more than MAX_BEFORE_ARCHIVE.
MAX_BEFORE_ARCHIVE = 3
MAX_KEPT = 2

# Protestant canon (66 books)
CANON = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel", "1 Kings",
    "2 Kings", "1 Chronicles", "2 Chronicles", "Ezra", "Nehemiah",
    "Esther", "Job", "Psalms", "Proverbs", "Ecclesiastes",
    "Song of Solomon", "Isaiah", "Jeremiah", "Lamentations", "Ezekiel",
    "Daniel", "Hosea", "Joel", "Amos", "Obadiah", "Jonah", "Micah",
    "Nahum", "Habakkuk", "Zephaniah", "Haggai", "Zechariah", "Malachi",
    "Matthew", "Mark", "Luke", "John", "Acts", "Romans", "1 Corinthians",
    "2 Corinthians", "Galatians", "Ephesians", "Philippians", "Colossians",
    "1 Thessalonians", "2 Thessalonians", "1 Timothy", "2 Timothy",
    "Titus", "Philemon", "Hebrews", "James", "1 Peter", "2 Peter",
    "1 John", "2 John", "3 John", "Jude", "Revelation",
]


def _section_body(text: str) -> str:
    """Return everything from the Scripture Insights header onward."""
    if SECTION_HEADER not in text:
        return ""
    return text.split(SECTION_HEADER, 1)[1]


def _normalize_book(name: str) -> str | None:
    """Map a header name to a canonical book name, or None if not a book."""
    name = name.strip()
    if name in CANON:
        return name
    m = re.match(r"^(\d+)([A-Za-z]\S*)", name)
    if m:
        candidate = f"{m.group(1)} {m.group(2)}"
        if candidate in CANON:
            return candidate
    return None


def find_last_book() -> str | None:
    """Return the last canonical '### Book —' entry inside the Scripture
    Insights section only. Non-book headers elsewhere in SOUL.md (e.g.
    '### Tier 3 — ...') can never be misread as a book."""
    if not SOUL_PATH.exists():
        return None
    text = SOUL_PATH.read_text()
    last = None
    for line in _section_body(text).splitlines():
        m = re.match(r"^### ([A-Za-z0-9 ]+) —", line.strip())
        if not m:
            continue
        book = _normalize_book(m.group(1))
        if book:
            last = book
    return last


def next_book(current: str) -> str | None:
    """Return the book after current in canon; None if all done."""
    try:
        idx = CANON.index(current.strip())
        return CANON[idx + 1] if idx + 1 < len(CANON) else None
    except ValueError:
        return None


def read_cycle() -> int:
    """Read the current cycle number from the tracking comment (default 1)."""
    if not SOUL_PATH.exists():
        return 1
    m = CYCLE_RE.search(SOUL_PATH.read_text())
    return int(m.group(1)) if m else 1


def append_to_soul(entry: str, cycle: int) -> bool:
    """Append a bible entry INSIDE the Scripture Insights section, just before
    the next top-level '## ' header (or at EOF). Also writes the cycle comment
    at the end of the section so find_last_book() can see both."""
    text = SOUL_PATH.read_text() if SOUL_PATH.exists() else ""
    if SECTION_HEADER not in text:
        text = text.rstrip() + f"\n\n{SECTION_HEADER}\n\n"
    body = _section_body(text)
    # Find the end of the section: next '## ' header or EOF
    m = re.search(r"\n## ", body)
    section_end = m.start() if m else len(body)
    entry_block = f"\n\n{entry}\n\n<!-- Bible Cycle: {cycle} -->"
    new_text = text[: text.index(SECTION_HEADER) + len(SECTION_HEADER)] + body[:section_end] + entry_block + body[section_end:]
    SOUL_PATH.write_text(new_text)
    return True


def archive_old_entries(cycle: int) -> int:
    """Move book entries (except the last MAX_KEPT) from SOUL.md to the
    archive file. Returns the number archived (0 = nothing to archive).
    Only canonical book entries are moved; other lines stay."""
    if not SOUL_PATH.exists():
        return 0
    text = SOUL_PATH.read_text()
    if SECTION_HEADER not in text:
        return 0
    body = _section_body(text)
    m = re.search(r"\n## ", body)
    section_end = m.start() if m else len(body)
    section = body[:section_end]
    lines = section.split("\n")
    kept, books = [], []
    for line in lines:
        bm = re.match(r"^### ([A-Za-z0-9 ]+) —", line.strip())
        if bm and _normalize_book(bm.group(1)):
            books.append(line)
        else:
            kept.append(line)
    if len(books) <= MAX_BEFORE_ARCHIVE:
        return 0
    archive = books[:-MAX_KEPT]
    keep = books[-MAX_KEPT:]
    ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ARCHIVE_PATH.open("a") as f:
        f.write(f"\n## Cycle {cycle} archive ({len(archive)} entries)\n\n")
        f.write("\n".join(archive) + "\n")
    new_section = "\n".join(kept + keep)
    new_text = text[: text.index(SECTION_HEADER) + len(SECTION_HEADER)] + new_section + body[section_end:]
    SOUL_PATH.write_text(new_text)
    return len(archive)


def call_api(prompt: str, max_tokens: int = 600) -> str | None:
    """Call deepseek-v4-flash. Returns content string or None."""
    if not API_KEY:
        print("DEEPSEEK_API_KEY not set")
        return None
    payload = json.dumps({
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }).encode()
    req = Request(API_URL, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    })
    try:
        resp = urlopen(req, timeout=API_TIMEOUT)
        data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except URLError as e:
        print(f"API error: {e}")
        return None
    except (KeyError, json.JSONDecodeError) as e:
        print(f"API parse error: {e}")
        return None


def update_index(book: str) -> None:
    """Add book to brain INDEX.md if not present."""
    index_path = BRAIN_DIR / "INDEX.md"
    if index_path.exists() and book in index_path.read_text():
        return
    if not index_path.exists():
        index_path.write_text("# Bible Study Index\n\n| Book | Status |\n|------|--------|\n")
    with index_path.open("a") as f:
        f.write(f"| {book} |  |\n")


# ── Main ───────────────────────────────────────────────────
def main() -> int:
    start = time.time()

    cycle = read_cycle()
    last = find_last_book()

    if last is None:
        book, note = "Genesis", "no prior book found — starting fresh"
    elif last == "Revelation":
        cycle += 1
        book, note = "Genesis", f"cycle {cycle - 1} complete — cycle {cycle} starts"
    else:
        book = next_book(last)
        note = f"after {last}"
        if book is None:  # last not in canon — treat as fresh start
            book, note = "Genesis", "prior book not in canon — starting fresh"

    print(f"Reading: {book} ({note})")

    # Generate SOUL entry (single API call)
    prompt = (
        f"You are a Bible study assistant. For the book of {book}, "
        f"produce a SHORT entry (max 3 lines, ~400 chars):\n\n"
        f"### {book} — *\"[key verse]\"* ([book] [ch]:[v])\n"
        f"I will [one-sentence commitment from {book}'s lessons].\n"
        f"<!-- {datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d')} -->\n"
    )
    entry = call_api(prompt, max_tokens=500)
    if not entry:
        return 1

    append_to_soul(entry, cycle)
    archived = archive_old_entries(cycle)
    print(f"SOUL.md updated ({time.time() - start:.1f}s, archived={archived})")

    # Brain page (best-effort)
    slug = book.replace(" ", "-")
    brain_path = BRAIN_DIR / f"{slug}.md"
    if not brain_path.exists():
        b_prompt = (
            f"Write a Bible study note for {book}:\n1. Summary\n"
            f"2. Archaeology & Scholarship\n3. Jewish & Messianic Perspective\n"
            f"4. Original Language Insights\n5. Insight for {AGENT}"
        )
        page = call_api(b_prompt, max_tokens=1500)
        if page:
            BRAIN_DIR.mkdir(parents=True, exist_ok=True)
            brain_path.write_text(page + "\n")
            update_index(book)
            print(f"Brain page: {slug}.md")

    elapsed = time.time() - start
    print(f"\n=== Daily Bible Reading: {book} (cycle {cycle}, {elapsed:.1f}s) ===")
    print(entry)
    print("====================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
