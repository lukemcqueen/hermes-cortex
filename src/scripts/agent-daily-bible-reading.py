#!/usr/bin/env python3
"""agent-daily-bible-reading.py — no_agent cron script.

Reads SOUL.md (or brain fallback), determines the next canonical book,
generates an insight via deepseek API, appends a compact one-liner to
SOUL.md, a full entry to the brain file, and auto-archives old entries
to a gbrain-synced brain dir to keep SOUL.md small.

Compact format in SOUL.md:
  ### Book — *"short phrase" (citation) — date*

Silent when no new book needed (exit 0, empty stdout).
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
SOUL_MD = HOME / ".hermes" / "SOUL.md"
BRAIN_DIR = HOME / ".hermes" / "brain"
BRAIN_FILE = BRAIN_DIR / "scripture-insights.md"
BIBLE_ARCHIVE_DIR = HOME / "brain" / "sources" / "hermes" / "bible-readings"
MAX_INLINE_ENTRIES = 2  # Keep only this many entries in SOUL.md, archive the rest
OLLAMA_URL = "http://localhost:11434/api/chat"
KST = timezone.utc  # We'll just note KST in the output

# Full Protestant canon in order
BOOKS = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "Ruth",
    "1 Samuel", "2 Samuel", "1 Kings", "2 Kings",
    "1 Chronicles", "2 Chronicles",
    "Ezra", "Nehemiah", "Esther",
    "Job", "Psalms", "Proverbs", "Ecclesiastes", "Song of Solomon",
    "Isaiah", "Jeremiah", "Lamentations", "Ezekiel", "Daniel",
    "Hosea", "Joel", "Amos", "Obadiah", "Jonah", "Micah", "Nahum",
    "Habakkuk", "Zephaniah", "Haggai", "Zechariah", "Malachi",
    "Matthew", "Mark", "Luke", "John",
    "Acts",
    "Romans", "1 Corinthians", "2 Corinthians",
    "Galatians", "Ephesians", "Philippians", "Colossians",
    "1 Thessalonians", "2 Thessalonians",
    "1 Timothy", "2 Timothy", "Titus", "Philemon",
    "Hebrews", "James",
    "1 Peter", "2 Peter",
    "1 John", "2 John", "3 John", "Jude",
    "Revelation",
]

# Map canonical names to their index for lookups
BOOK_INDEX = {b: i for i, b in enumerate(BOOKS)}


def get_kst_today() -> str:
    """Return today's date in KST as YYYY-MM-DD."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d")


def _find_last_book_in_file(filepath: Path) -> str | None:
    """Find the last book reference ### BookName in a markdown file."""
    if not filepath.exists():
        return None
    text = filepath.read_text(encoding="utf-8")
    found_books = []
    for line in text.split("\n"):
        m = re.match(r"^### ([A-Za-z0-9 ]+) —", line)
        if m:
            name = m.group(1).strip()
            if name in BOOK_INDEX:
                found_books.append(name)
    return found_books[-1] if found_books else None


def find_last_book() -> str | None:
    """Read SOUL.md and find the last book covered in compact entries.
    Falls back to BRAIN_FILE if SOUL.md has no entries."""
    # Try SOUL.md first (compact entries section)
    if SOUL_MD.exists():
        text = SOUL_MD.read_text(encoding="utf-8")

        # Find all ### BookName — entries in Scripture Insights section
        insights_section = text.split("## Scripture Insights")[-1]
        insights_section = insights_section.split("## Session Mining Lessons")[0]

        found_books = []
        for line in insights_section.split("\n"):
            m = re.match(r"^### ([A-Za-z0-9 ]+) —", line)
            if m:
                name = m.group(1).strip()
                if name in BOOK_INDEX:
                    found_books.append(name)

        if found_books:
            return found_books[-1]

    # Fallback: check BRAIN_FILE
    if BRAIN_FILE.exists():
        return _find_last_book_in_file(BRAIN_FILE)

    return None


def get_next_book(last_book: str) -> str | None:
    """Determine the next canonical book after last_book."""
    idx = BOOK_INDEX.get(last_book)
    if idx is None:
        return None
    if idx + 1 >= len(BOOKS):
        return None  # All books covered
    return BOOKS[idx + 1]


DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"
ENV_FILE = HOME / ".hermes" / ".env"


def get_deepseek_api_key() -> str | None:
    """Read DEEPSEEK_API_KEY from the Hermes .env file."""
    if not ENV_FILE.exists():
        return None
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("DEEPSEEK_API_KEY="):
            val = line.split("=", 1)[1].strip().strip("\"'")
            if val:
                return val
    return None


def generate_entry(book: str) -> str | None:
    """Call deepseek-v4-flash to generate the full entry text."""
    today = get_kst_today()
    api_key = get_deepseek_api_key()
    if not api_key:
        print("❌ DEEPSEEK_API_KEY not found in .env", file=sys.stderr)
        return None

    prompt = f"""You are writing a "Scripture Insight" entry for an AI agent's character document (SOUL.md). This entry becomes part of the agent's identity — it's read every session so it must shape the agent's behaviour with sharp, specific lessons.

Write the entry for **{book}** in this EXACT format:

### {book} — *"[key verse]" ([Book Chapter:Verse])*

[3-5 paragraphs of commentary.]

<!-- Added {today} -->

Requirements:
1. Pick ONE key verse that genuinely captures the book's core message. Include the exact citation.
2. Write 3-5 paragraphs: explain the biblical context, then draw specific lessons for the agent's work as a system operator — automation, monitoring, reliability, documentation, cron jobs, config files, deployments, log analysis, health checks, rollbacks, etc.
3. End each paragraph's lesson with **bold text** for the key takeaway.
4. Be sharp and concrete — no generic life advice. Each lesson must be something an automation agent can actually apply.
5. Output ONLY the entry — no explanations, no code fences, no extra text.
6. The date comment goes AFTER the commentary paragraph, on its own line.

Generate the entry for {book}:"""

    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.7,
    })

    try:
        result = subprocess.run(
            ["curl", "-s", "-w", "\n%{http_code}", "-X", "POST", DEEPSEEK_URL,
             "-H", "Content-Type: application/json",
             "-H", f"Authorization: Bearer ***",
             "-d", payload],
            capture_output=True, text=True, timeout=120,
        )

        parts = result.stdout.strip().rsplit("\n", 1)
        http_code = parts[-1] if len(parts) > 1 else "000"
        body = parts[0] if len(parts) > 1 else result.stdout

        if result.returncode != 0:
            print(f"❌ curl failed (exit {result.returncode}): {result.stderr}", file=sys.stderr)
            return None

        if http_code != "200":
            print(f"❌ API returned HTTP {http_code}: {body[:300]}", file=sys.stderr)
            return None

        response = json.loads(body)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        if not content:
            print(f"❌ Empty response from API", file=sys.stderr)
            return None

        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        return content
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}", file=sys.stderr)
        print(f"   Body: {body[:500]}", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print(f"❌ API request timed out after 120s", file=sys.stderr)
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        return None


def parse_entry_heading(full_entry: str) -> tuple[str, str, str] | None:
    """Parse the full entry's heading line.

    Expected format:
      ### BookName — *"verse text" (Chapter:Verse)*

    Returns (book_name, short_phrase, citation) or None.
    Extracts a short phrase (first ~60 chars of verse) for the compact line.
    """
    first_line = full_entry.strip().split("\n")[0]
    m = re.match(r"^### ([A-Za-z0-9 ]+) — \*\"(.+?)\" \((.+?)\)\*", first_line)
    if m:
        book = m.group(1).strip()
        verse = m.group(2).strip()
        citation = m.group(3).strip()
        # Truncate long verses for the compact line
        if len(verse) > 60:
            verse = verse[:57] + "..."
        return (book, verse, citation)
    return None


def append_compact_to_soul(book: str, short_phrase: str, citation: str, today: str) -> bool:
    """Append a compact one-liner to SOUL.md before the Session Mining section."""
    if not SOUL_MD.exists():
        return False

    text = SOUL_MD.read_text(encoding="utf-8")
    compact_line = f'### {book} — *"{short_phrase}" ({citation}) — {today}*'

    marker = "## Session Mining Lessons"
    if marker in text:
        new_text = text.replace(f"\n{marker}", f"\n{compact_line}\n\n{marker}", 1)
    else:
        new_text = text.rstrip() + f"\n{compact_line}\n"

    SOUL_MD.write_text(new_text, encoding="utf-8")
    return True


def append_full_to_brain(book: str, full_entry: str, today: str) -> bool:
    """Append the full entry to the brain file with a date marker.

    Also creates a symlink from the brain file to the gbrain sources dir
    so the gbrain autopilot daemon picks it up for vector search.
    """
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    if not BRAIN_FILE.exists():
        content = (
            "# Scripture Insights — Full Entries\n\n"
            "<!-- Full entries appended by agent-daily-bible-reading cron at 01:00 KST -->\n\n"
            "---\n\n"
        )
        BRAIN_FILE.write_text(content, encoding="utf-8")
    else:
        content = BRAIN_FILE.read_text(encoding="utf-8")

    entry_block = full_entry.strip() + "\n\n---\n\n"
    BRAIN_FILE.write_text(content + entry_block, encoding="utf-8")

    # Ensure gbrain sources dir exists and create a copy for gbrain sync
    BIBLE_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    gbrain_copy = BIBLE_ARCHIVE_DIR / "current.md"
    gbrain_copy.write_text(content + entry_block + "\n*Last updated: {date}*\n".format(date=today), encoding="utf-8")

    return True


# ─── Archive helpers ────────────────────────────────────────────────

ARCHIVE_HEADER = """# Archived Scripture Insights — {book_range}
<!-- Archived from SOUL.md on {date} by agent-daily-bible-reading cron. -->

"""


def find_all_entries() -> list[tuple[str, str]] | None:
    """Parse SOUL.md and return list of (book_name, full_entry_text) for each Scripture Insight entry.
    Returns None if section not found."""
    if not SOUL_MD.exists():
        return None
    text = SOUL_MD.read_text(encoding="utf-8")
    lines = text.split("\n")

    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "## Scripture Insights")
    except StopIteration:
        return None

    end = start + 1
    while end < len(lines):
        if lines[end].startswith("## ") and "Scripture" not in lines[end]:
            break
        end += 1

    entries = []
    i = start
    while i < end:
        m = re.match(r"^### ([A-Za-z0-9 ]+) —", lines[i])
        if m:
            name = m.group(1).strip()
            if name in BOOK_INDEX:
                entry_lines = []
                while i < end:
                    entry_lines.append(lines[i])
                    i += 1
                    if i < end and lines[i].startswith("### "):
                        break
                entries.append((name, "\n".join(entry_lines)))
                continue
        i += 1

    return entries if entries else None


def archive_old_entries(entries: list[tuple[str, str]]) -> bool:
    """If SOUL.md has more than MAX_INLINE_ENTRIES entries, archive the oldest ones
    to the gbrain brain source directory and trim them from SOUL.md."""
    if len(entries) <= MAX_INLINE_ENTRIES:
        return True

    to_archive = entries[:-MAX_INLINE_ENTRIES]
    to_keep = entries[-MAX_INLINE_ENTRIES:]
    today = get_kst_today()

    BIBLE_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(BIBLE_ARCHIVE_DIR.glob("archive-*.md"))
    next_num = len(existing) + 1
    book_range = f"{to_archive[0][0]} \u2192 {to_archive[-1][0]}"
    archive_path = BIBLE_ARCHIVE_DIR / f"archive-{next_num:02d}.md"

    archive_content = ARCHIVE_HEADER.format(book_range=book_range, date=today)
    for _, entry_text in to_archive:
        archive_content += entry_text.strip() + "\n\n"
    archive_content += "\n---\n\n*Archived {date}. This content is synced into gbrain for vector search.*\n".format(date=today)
    archive_path.write_text(archive_content.strip() + "\n", encoding="utf-8")

    # Trim SOUL.md
    text = SOUL_MD.read_text(encoding="utf-8")
    lines = text.split("\n")

    section_start = next(i for i, l in enumerate(lines) if l.strip() == "## Scripture Insights")
    section_end = section_start + 1
    while section_end < len(lines):
        if lines[section_end].startswith("## ") and "Scripture" not in lines[section_end]:
            break
        section_end += 1

    new_section = [
        "## Scripture Insights",
        "",
        "<!-- Entries will be appended here by the daily Bible reading cron job -->",
        "<!-- Older readings archived at /home/luke/brain/sources/hermes/bible-readings/ -->",
        "",
    ]
    for _, entry_text in to_keep:
        for line in entry_text.split("\n"):
            new_section.append(line)
        new_section.append("")

    new_lines = lines[:section_start] + new_section + lines[section_end:]
    SOUL_MD.write_text("\n".join(new_lines), encoding="utf-8")

    print(f"Archived {len(to_archive)} entries ({book_range}) -> {archive_path.name}", file=sys.stderr)
    print(f"Kept {len(to_keep)} entries inline in SOUL.md", file=sys.stderr)
    return True


# ─── Main ───────────────────────────────────────────────────────────

def main() -> int:
    last_book = find_last_book()
    if last_book is None:
        print("❌ No books found in SOUL.md or brain file", file=sys.stderr)
        return 1

    next_book = get_next_book(last_book)
    if next_book is None:
        print("📖 All 66 books have been covered. Bible reading complete.", file=sys.stderr)
        return 0

    today = get_kst_today()
    print(f"📖 Last: {last_book} → Next: {next_book}")

    full_entry = generate_entry(next_book)
    if full_entry is None:
        return 1

    # Parse the heading for the compact line
    parsed = parse_entry_heading(full_entry)
    if parsed is None:
        print(f"⚠️ Could not parse entry heading, using book-only format", file=sys.stderr)
        book = next_book
        short_phrase = full_entry.split('\n')[0].split('—')[1].strip().strip('*"')[:60]
        citation = ""
    else:
        book, short_phrase, citation = parsed

    # Write compact line to SOUL.md
    if not append_compact_to_soul(book, short_phrase, citation, today):
        print("❌ Failed to append compact entry to SOUL.md", file=sys.stderr)
        return 1

    # Write full entry to brain file + gbrain sources
    if not append_full_to_brain(book, full_entry, today):
        print("❌ Failed to append full entry to brain file", file=sys.stderr)
        return 1

    # Archive old entries if SOUL.md has grown too many inline entries
    # (safety net — compact entries are small, but a long-running system
    #  could accumulate hundreds)
    all_entries = find_all_entries()
    if all_entries:
        archive_old_entries(all_entries)

    # Output the result for delivery
    print(f"\n✅ Appended compact insight for **{book}** to SOUL.md")
    print(f"   Full entry written to ~/.hermes/brain/scripture-insights.md")
    print(f"   Also synced to gbrain: {BIBLE_ARCHIVE_DIR}/\n")
    print(f"### {book} — *\"{short_phrase}\" ({citation}) — {today}*")
    return 0


if __name__ == "__main__":
    sys.exit(main())
