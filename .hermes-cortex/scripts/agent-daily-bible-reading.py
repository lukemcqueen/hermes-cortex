#!/usr/bin/env python3
"""agent-daily-bible-reading.py — no_agent cron script.

Reads SOUL.md, determines the next canonical book to cover,
generates an insight via Ollama (qwen2.5-coder:3b), and appends it.

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
    for section_header in ["## Scripture Insights", "## Biblical Principles"]:
        if section_header in text:
            insights_section = text.split(section_header)[-1]
            break
    else:
        insights_section = text
    insights_section = insights_section.split("## Session Mining Lessons")[0]
    def normalize_name(name: str) -> str | None:
        name = name.strip()
        if name in BOOK_INDEX:
            return name
        import re as re2
        m2 = re2.match(r'^(\d+)([A-Z]\S+)', name)
        if m2:
            with_space = f"{m2.group(1)} {m2.group(2)}"
            if with_space in BOOK_INDEX:
                return with_space
        return None
    found_books = []
    for line in insights_section.split("\n"):
        m = re.match(r"^### ([A-Za-z0-9 ]+) —", line) or re.match(r"^### ([A-Za-z0-9 ]+) \([0-9]{4}-[0-9]{2}-[0-9]{2}\)", line)
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

DEEPSEEK_URL = "https://opencode.ai/zen/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"
ENV_FILE = HOME / ".hermes" / ".env"

def get_deepseek_api_key() -> str | None:
    if not ENV_FILE.exists():
        return None
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("OPENCODE_ZEN_API_KEY="):
            val = line.split("=", 1)[1].strip().strip("\"'")
            if val:
                return val
    return None

def generate_entry(book: str) -> str | None:
    today = get_kst_today()
    api_key = get_deepseek_api_key()
    if not api_key:
        print("❌ OPENCODE_ZEN_API_KEY not found in .env", file=sys.stderr)
        return None
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
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.7,
    })
    try:
        result = subprocess.run(
            ["curl", "-s", "-w", "\n%{http_code}", "-X", "POST", DEEPSEEK_URL,
             "-H", "Content-Type: application/json",
             "-H", "Authorization: Bearer " + api_key,
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

def append_to_soul(book: str, full_entry: str) -> bool:
    if not SOUL_MD.exists():
        return False
    text = SOUL_MD.read_text(encoding="utf-8")
    marker = "## Session Mining Lessons"
    if marker in text:
        full_block = f"\n{full_entry}\n\n"
        new_text = text.replace(f"\n{marker}", f"{full_block}{marker}", 1)
    else:
        full_block = f"\n{full_entry}\n"
        new_text = text + full_block
    SOUL_MD.write_text(new_text, encoding="utf-8")
    return True

def main() -> int:
    last_book = find_last_book()
    if last_book is None:
        print("❌ Could not find any books in SOUL.md", file=sys.stderr)
        return 1
    next_book = get_next_book(last_book)
    if next_book is None:
        print("📖 All 66 books have been covered. Bible reading complete.", file=sys.stderr)
        return 0
    print(f"📖 Last book: {last_book} → Next: {next_book}")
    full_entry = generate_entry(next_book)
    if full_entry is None:
        return 1
    if not append_to_soul(next_book, full_entry):
        print("❌ Failed to append to SOUL.md", file=sys.stderr)
        return 1
    print(f"\n✅ Appended insight for **{next_book}** to SOUL.md\n")
    print(full_entry)
    return 0

if __name__ == "__main__":
    sys.exit(main())
