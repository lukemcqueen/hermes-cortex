#!/usr/bin/env python3
"""agent-daily-bible-reading.py — no_agent cron script.

Reads SOUL.md (compact entries), determines the next canonical book,
generates an insight via deepseek API, appends a compact one-liner to
SOUL.md and a full entry to ~/.hermes/brain/scripture-insights.md.

The compact format preserves find_last_book() compatibility:
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

BOOK_INDEX = {b: i for i, b in enumerate(BOOKS)}


def get_kst_today() -> str:
    """Return today's date in KST as YYYY-MM-DD."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d")


def find_last_book() -> str | None:
    """Read SOUL.md and find the last book covered in compact entries."""
    if not SOUL_MD.exists():
        # Fallback to brain file
        if BRAIN_FILE.exists():
            return _find_last_book_in_file(BRAIN_FILE)
        return None

    last = _find_last_book_in_file(SOUL_MD)
    if last:
        return last
    # Fallback to brain file
    if BRAIN_FILE.exists():
        return _find_last_book_in_file(BRAIN_FILE)
    return None


def _find_last_book_in_file(path: Path) -> str | None:
    """Find the last book covered in a file with ### Book — entries."""
    text = path.read_text(encoding="utf-8")
    found_books = []
    for line in text.split("\n"):
        m = re.match(r"^### ([A-Za-z0-9 ]+) —", line)
        if m:
            name = m.group(1).strip()
            if name in BOOK_INDEX:
                found_books.append(name)
    return found_books[-1] if found_books else None


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
    """Call deepseek-v4-flash to generate the full entry text.
    Returns the raw model response — the model outputs the complete entry including
    verse, commentary, and date comment in the correct format.

    The generated format is:
      ### Book — *"verse" (citation)*
      [3-5 paragraphs commentary]
      <!-- Added YYYY-MM-DD -->
    """
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
7. Keep the verse text BRIEF — use a short key phrase (under 80 chars), not the full verse. For example: "For everything there is a season" instead of the full Ecclesiastes 3 passage.

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
             "-H", f"Authorization: Bearer {api_key}",
             "-d", payload],
            capture_output=True, text=True, timeout=120,
        )

        # Split response body from HTTP status code
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

        # Clean up any markdown code block wrapping
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
    """Parse the heading line from a full entry.

    Expected format:  ### Book — *"verse text" (citation)*

    Returns (book, short_phrase, citation) or None.
    Extracts a short phrase (first ~60 chars of verse) for the compact line.
    """
    first_line = full_entry.strip().split("\n")[0]
    m = re.match(r"^### ([A-Za-z0-9 ]+) — \*\"(.+?)\"\s*\(([^)]+)\)\*", first_line)
    if not m:
        return None
    book = m.group(1).strip()
    full_verse = m.group(2).strip()
    citation = m.group(3).strip()

    # Truncate to a short key phrase (max 60 chars, break at word boundary)
    if len(full_verse) > 60:
        truncated = full_verse[:60]
        # Break at last space
        last_space = truncated.rfind(" ")
        if last_space > 30:
            truncated = truncated[:last_space]
        short_phrase = truncated.rstrip(" ,.;:") + "…"
    else:
        short_phrase = full_verse

    return book, short_phrase, citation


def append_compact_to_soul(book: str, short_phrase: str, citation: str, today: str) -> bool:
    """Append a compact one-liner to SOUL.md before the Session Mining section.

    Format:
      ### Book — *"short phrase" (citation) — date*
    """
    if not SOUL_MD.exists():
        return False

    text = SOUL_MD.read_text(encoding="utf-8")
    compact_line = f'### {book} — *"{short_phrase}" ({citation}) — {today}*'

    # Insert before "## Session Mining Lessons" if present
    marker = "## Session Mining Lessons"
    if marker in text:
        new_text = text.replace(f"\n{marker}", f"\n{compact_line}\n{marker}", 1)
    else:
        # Append at the end (after the Scripture Insights section)
        new_text = text.rstrip() + f"\n{compact_line}\n"

    SOUL_MD.write_text(new_text, encoding="utf-8")
    return True


def append_full_to_brain(book: str, full_entry: str, today: str) -> bool:
    """Append the full entry to the brain file with a date marker."""
    BRAIN_DIR.mkdir(parents=True, exist_ok=True)
    if not BRAIN_FILE.exists():
        # Create header
        content = (
            "# Scripture Insights — Full Entries\n\n"
            "<!-- Full entries appended by agent-daily-bible-reading cron at 01:00 KST -->\n\n"
            "---\n\n"
        )
        BRAIN_FILE.write_text(content, encoding="utf-8")
    else:
        content = BRAIN_FILE.read_text(encoding="utf-8")

    # Append the full entry
    entry_block = full_entry.strip() + "\n\n---\n\n"
    BRAIN_FILE.write_text(content + entry_block, encoding="utf-8")
    return True


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
        # Fallback: just use the book name as the compact line
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

    # Write full entry to brain file
    if not append_full_to_brain(book, full_entry, today):
        print("❌ Failed to append full entry to brain file", file=sys.stderr)
        return 1

    # Output the result for delivery
    print(f"\n✅ Appended compact insight for **{book}** to SOUL.md")
    print(f"   Full entry written to ~/.hermes/brain/scripture-insights.md\n")
    print(f"### {book} — *\"{short_phrase}\" ({citation}) — {today}*")
    return 0


if __name__ == "__main__":
    sys.exit(main())
