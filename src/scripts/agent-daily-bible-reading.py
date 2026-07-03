#!/opt/homebrew/bin/python3.12
"""agent-daily-bible-reading.py — no_agent cron script.

Reads SOUL.md, determines the next canonical book to cover,
generates an insight via local Ollama qwen2.5-coder:3b, and appends it.

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
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "mannix/qwen2.5-coder:7b-iq3_xs"
KST = timezone.utc

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
    now = datetime.now()
    return now.strftime("%Y-%m-%d")


def find_last_book() -> str | None:
    if not SOUL_MD.exists():
        return None
    text = SOUL_MD.read_text(encoding="utf-8")
    for section_header in ["## Daily Scripture", "## Scripture Insights", "## Biblical Principles"]:
        if section_header in text:
            insights_section = text.split(section_header)[-1]
            break
    else:
        insights_section = text
    insights_section = insights_section.split("## Session Mining Lessons")[0]
    def normalize_name(name: str) -> str | None:
        name = name.strip()
        import re as re2
        # Strip "📖 Book:" prefix if present
        m_pre = re2.match(r"^📖 Book:\s*(.*)", name)
        if m_pre:
            name = m_pre.group(1)
        # Strip parenthetical content like "(all 3 chapters)" or "(13 chapters)"
        name = re2.sub(r"\s*\([^)]*\)\s*", "", name).strip()
        if name in BOOK_INDEX:
            return name
        m2 = re2.match(r'^(\d+)([A-Z]\S+)', name)
        if m2:
            with_space = f"{m2.group(1)} {m2.group(2)}"
            if with_space in BOOK_INDEX:
                return with_space
        return None
    found_books = []
    for line in insights_section.split("\n"):
        m = re.match(r"^### 📖 Book:\s*([A-Za-z0-9 ]+)\s*\(.*?\)\s*—", line) or re.match(r"^### ([A-Za-z0-9 ]+) —", line) or re.match(r"^### ([A-Za-z0-9 ]+) \([0-9]{4}-[0-9]{2}-[0-9]{2}\)", line)
        if m:
            name = normalize_name(m.group(1))
            if name:
                found_books.append(name)
    if not found_books:
        return None
    return found_books[-1]


def get_next_book(last_book: str) -> str | None:
    idx = BOOK_INDEX.get(last_book)
    if idx is None:
        return None
    if idx + 1 >= len(BOOKS):
        return None
    return BOOKS[idx + 1]


def generate_entry(book: str) -> str | None:
    today = get_kst_today()
    prompt = f"""You are writing a "Scripture Insight" entry for an AI agent's character document (SOUL.md).
Write the entry for **{book}** in this EXACT format:
### {book} — *"[key verse]" ([Book Chapter:Verse])*
[3-5 paragraphs of commentary.]
<!-- Added {today} -->
Requirements:
1. Pick ONE key verse that genuinely captures the book's core message.
2. Write 3-5 paragraphs with specific lessons for system operations.
3. End each paragraph's lesson with **bold text** for the key takeaway.
4. Output ONLY the entry — no explanations, no code fences, no extra text.
Generate the entry for {book}:"""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "num_predict": 4096,
            "temperature": 0.7,
        },
    })
    try:
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", OLLAMA_URL,
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            print(f"curl to ollama failed (exit {result.returncode}): {result.stderr}", file=sys.stderr)
            return None
        response = json.loads(result.stdout)
        content = response.get("message", {}).get("content", "")
        if not content:
            print("Empty response from Ollama", file=sys.stderr)
            return None
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
        return content
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}", file=sys.stderr)
        print(f"   Body: {getattr(result, 'stdout', '')[:500]}", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print("Ollama request timed out after 300s", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return None


def append_to_soul(book: str, full_entry: str) -> bool:
    if not SOUL_MD.exists():
        return False
    text = SOUL_MD.read_text(encoding="utf-8")
    # Insert before the cron marker comment if it exists
    cron_marker = "<!-- Entries appended here by daily cron -->"
    if cron_marker in text:
        full_block = f"\n{full_entry}\n\n"
        new_text = text.replace(f"\n{cron_marker}", f"{full_block}{cron_marker}", 1)
    elif "## Final Directive" in text:
        full_block = f"\n{full_entry}\n\n"
        new_text = text.replace(f"\n## Final Directive", f"{full_block}## Final Directive", 1)
    elif "## Session Mining Lessons" in text:
        full_block = f"\n{full_entry}\n\n"
        new_text = text.replace(f"\n## Session Mining Lessons", f"{full_block}## Session Mining Lessons", 1)
    else:
        full_block = f"\n{full_entry}\n"
        new_text = text + full_block
    SOUL_MD.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    last_book = find_last_book()
    if last_book is None:
        print("Could not find any books in SOUL.md", file=sys.stderr)
        return 1
    next_book = get_next_book(last_book)
    if next_book is None:
        print("All 66 books covered. Bible reading complete.")
        return 0
    print(f"Last book: {last_book} -> Next: {next_book}")
    full_entry = generate_entry(next_book)
    if full_entry is None:
        return 1
    if not append_to_soul(next_book, full_entry):
        print("Failed to append to SOUL.md", file=sys.stderr)
        return 1
    print(f"Appended insight for {next_book} to SOUL.md")
    print(full_entry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
