#!/usr/bin/env python3
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
from datetime import datetime, timezone, timedelta
from pathlib import Path

HOME = Path.home()
SOUL_MD = HOME / ".hermes" / "SOUL.md"
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5-coder:3b"
KST = timezone(timedelta(hours=9))

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

# Build a mapping that also matches without spaces (e.g. "1Thessalonians" -> "1 Thessalonians")
_BOOK_INDEX_FUZZY = {}
for name in BOOKS:
    _BOOK_INDEX_FUZZY[name] = name
    compact = re.sub(r"(\d) ", r"\1", name)  # "1 Thessalonians" -> "1Thessalonians"
    _BOOK_INDEX_FUZZY[compact] = name


def get_kst_today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def find_all_books() -> list[str]:
    """Find ALL book references across the entire SOUL.md, ordered by appearance."""
    if not SOUL_MD.exists():
        return []
    text = SOUL_MD.read_text(encoding="utf-8")
    found = []
    seen = set()
    for line in text.split("\n"):
        # Match: ### BookName (YYYY-MM-DD) or ### BookName — text
        m = re.match(r"^### ([A-Za-z0-9 ]+)\s*[(\u2014-]", line)
        if not m:
            continue
        raw = m.group(1).strip()
        # Try exact match first, then fuzzy
        name = _BOOK_INDEX_FUZZY.get(raw)
        if name is None:
            continue
        if name not in seen:
            seen.add(name)
            found.append(name)
    return found


def get_last_uncovered_book(found: list[str]) -> str | None:
    """Find the first book in the canonical list not yet found in SOUL.md."""
    covered = set(found)
    for book in BOOKS:
        if book not in covered:
            return book
    return None


def query_ollama(prompt: str) -> str | None:
    """Send a prompt to Ollama chat and return the response content."""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": 4096, "temperature": 0.7},
    })
    try:
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", OLLAMA_URL,
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            print(f"curl failed: {result.stderr.strip()}", file=sys.stderr)
            return None
        resp = json.loads(result.stdout)
        content = resp.get("message", {}).get("content", "")
        if not content:
            print("Ollama returned empty content", file=sys.stderr)
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
        print(f"   Response: {result.stdout[:500]}", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print("Ollama request timed out after 300s", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return None


def generate_entry(book: str) -> str | None:
    today = get_kst_today()
    prompt = f"""You are writing a "Scripture Insight" entry for an AI agent's character document (SOUL.md).
Write the entry for **{book}** in this EXACT format:

### {book} — *"[key verse]" ([Book Chapter:Verse])*
[3-5 paragraphs of commentary about operations/security lessons from this book.]
<!-- Added {today} -->

Requirements:
1. Pick ONE key verse that genuinely captures the book's core message.
2. Write 3-5 paragraphs with specific lessons for system operations.
3. End each paragraph's lesson with **bold text** for the key takeaway.
4. Output ONLY the entry — no explanations, no code fences, no extra text.

Generate the entry for {book}:"""
    return query_ollama(prompt)


def append_to_soul(book: str, entry: str) -> bool:
    if not SOUL_MD.exists():
        return False
    text = SOUL_MD.read_text(encoding="utf-8")
    # Insert before the Final Directive section
    if "\n## Final Directive\n" in text:
        full_block = f"\n{entry}\n\n"
        new_text = text.replace("\n## Final Directive\n", f"{full_block}## Final Directive\n", 1)
    elif "\n## Scripture Insights\n" in text:
        full_block = f"\n{entry}\n\n"
        new_text = text.replace("\n## Scripture Insights\n", f"{full_block}## Scripture Insights\n", 1)
    else:
        full_block = f"\n{entry}\n"
        new_text = text + full_block
    SOUL_MD.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    found = find_all_books()
    print(f"Books covered in SOUL.md: {len(found)}", file=sys.stderr)
    for b in found:
        print(f"  - {b}", file=sys.stderr)
    next_book = get_last_uncovered_book(found)
    if next_book is None:
        print("All books covered. Nothing to generate.")
        return 0
    print(f"Generating entry for {next_book}")
    entry = generate_entry(next_book)
    if entry is None:
        return 1
    print(entry)
    if not append_to_soul(next_book, entry):
        print("Failed to append to SOUL.md", file=sys.stderr)
        return 1
    print(f"Appended insight for {next_book} to SOUL.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
