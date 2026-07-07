#!/usr/bin/env python3
"""agent-daily-bible-reading.py — no_agent cron script.

Reads SOUL.md, determines the next canonical book to cover,
generates two artifacts via deepseek API:
  1. A SOUL.md entry (concise, lesson-focused)
  2. A rich brain page at ~/brain/<agent>/bible/<book>.md

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

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"
ENV_FILE = HOME / ".hermes" / ".env"


# ── Agent name detection ─────────────────────────────────────

def detect_agent_name() -> str:
    """Detect the agent's name from env var, config, .env, or SOUL.md header."""
    # 1. Env var override
    env_name = os.environ.get("HERMES_AGENT_NAME") or os.environ.get("AGENT_NAME")
    if env_name:
        return env_name

    # 1b. .env file (loaded by no_agent cron scripts)
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("AGENT_NAME="):
                val = line.split("=", 1)[1].strip().strip("\"'")
                if val:
                    return val

    # 2. Hermes config.yaml
    config_paths = [
        HOME / ".hermes" / "config.yaml",
        HOME / ".hermes" / "config.json",
    ]
    for cp in config_paths:
        if cp.exists():
            try:
                text = cp.read_text(encoding="utf-8")
                m = re.search(r'agent_name["\s:=]+["\']?([a-zA-Z0-9_-]+)', text)
                if m:
                    return m.group(1)
            except Exception:
                pass

    # 3. SOUL.md first line: "# SOUL.md — AgentName"
    if SOUL_MD.exists():
        first_line = SOUL_MD.read_text(encoding="utf-8").split("\n", 1)[0]
        m = re.match(r"^#\s*SOUL\.md\s*[-–—]\s*(.+)", first_line)
        if m:
            name = m.group(1).strip()
            if name:
                return name

    # 4. Fallback
    return "moses"


# ── Book tracking from SOUL.md ────────────────────────────────

def get_kst_today() -> str:
    """Return today's date in KST as YYYY-MM-DD."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d")


def find_last_book() -> str | None:
    """Read SOUL.md and find the last book covered in Scripture Insights."""
    if not SOUL_MD.exists():
        return None

    text = SOUL_MD.read_text(encoding="utf-8")

    # Find all ### BookName — entries in Scripture Insights section
    # Look after the "## Scripture Insights" section header
    insights_section = text.split("## Scripture Insights")[-1]
    # Stop at the next ## section (Final Directive)
    insights_section = insights_section.split("## Final Directive")[0]
    
    found_books = []
    for line in insights_section.split("\n"):
        m = re.match(r"^### ([A-Za-z0-9 ]+) —", line)
        if m:
            name = m.group(1).strip()
            if name in BOOK_INDEX:
                found_books.append(name)

    if not found_books:
        return None

    return found_books[-1]


def get_next_book(last_book: str) -> str | None:
    """Determine the next canonical book after last_book."""
    idx = BOOK_INDEX.get(last_book)
    if idx is None:
        return None
    if idx + 1 >= len(BOOKS):
        return None  # All books covered
    return BOOKS[idx + 1]


# ── Deepseek API call ─────────────────────────────────────────

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


def _call_deepseek(prompt: str, max_tokens: int = 4096) -> str | None:
    """Make a deepseek API call and return the cleaned response content."""
    api_key = get_deepseek_api_key()
    if not api_key:
        print("❌ DEEPSEEK_API_KEY not found in .env", file=sys.stderr)
        return None

    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    })

    body = ""
    try:
        result = subprocess.run(
            ["curl", "-s", "-w", "\n%{http_code}", "-X", "POST", DEEPSEEK_URL,
             "-H", "Content-Type: application/json",
             "-H", f"Authorization: Bearer {api_key}",
             "-d", payload],
            capture_output=True, text=True, timeout=180,
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
        print(f"❌ API request timed out after 180s", file=sys.stderr)
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        return None


def generate_soul_entry(book: str) -> str | None:
    """Generate a SHORT SOUL.md entry (verse + one-line commitment only)."""
    today = get_kst_today()

    prompt = f"""You are writing a "Scripture Insight" entry for an AI agent's character document (SOUL.md). This is read every session so it must be compact and sharp — a single verse and a one-line commitment.

Write the entry for **{book}** in this EXACT format — nothing more, nothing less:

### {book} — *"[key verse]" ([Book Chapter:Verse])*
I will [one-line behavioral commitment for a system operator].

Requirements:
1. Pick ONE key verse that captures the book's core message. Exact citation.
2. Write exactly ONE sentence after "I will" — a concrete, actionable commitment for an automation agent.
3. Output ONLY the two-line entry — no explanations, no code fences, no extra text.

Generate the entry for {book}:"""

    return _call_deepseek(prompt, max_tokens=1024)


def generate_brain_page(book: str, agent_name: str) -> str | None:
    """Generate the rich brain page for ~/brain/<agent>/bible/<book>.md."""
    today = get_kst_today()

    prompt = f"""You are writing a detailed Bible study note for a knowledge brain directory. This is a reference document that will be stored permanently as a knowledge source, so it needs depth: historical context, archaeological evidence, textual scholarship, Jewish interpretive tradition, and original language analysis.

Write the entry for **{book}** in this EXACT markdown format:

# {book}

*Read: {today}*

## Summary

[2-3 paragraphs: narrative overview of the book — plot, key characters, theological themes, and its place in the biblical canon.]

## Archaeology & Scholarship

[2-3 paragraphs covering: archaeological discoveries that illuminate the book (sites, inscriptions, artifacts), textual criticism insights (Dead Sea Scrolls variants, Septuagint differences, Masoretic tradition), scholarly dating debates, and how the evidence supports or challenges traditional views. Reference specific digs, finds, and scholars where possible.]

## Jewish & Messianic Jewish Perspective

[2-3 paragraphs covering: how the book is read in traditional Jewish interpretation (Talmud, Midrash, Rashi, Maimonides), its liturgical use (haftarah readings, festivals), and how Messianic Jewish teachers (FFOZ, ONE FOR ISRAEL, Rabbi Jason Sobel, Dr. Eitan Bar, etc.) see the book pointing toward or prefiguring Yeshua the Messiah. Include specific typology or prophecy connections.]

## Original Language Insights

[Analyze 3-4 key Hebrew (OT) or Greek (NT) words from this book. For each: the word in its original script, transliteration, literal meaning, semantic range, how it's used in context, and any wordplay or textual significance. Format each as a bolded word heading.]

## Insight for {agent_name}

[A single paragraph connecting the book's core message to practical application for {agent_name}, a system operator and automation agent. Be specific and concrete, relating to monitoring, infrastructure, documentation, reliability, delegation, or leadership.]

Requirements:
1. Be factually accurate — cite real archaeological finds, real scholars, real textual evidence.
2. Include the Hebrew or Greek script for original language insights.
3. The Jewish & Messianic Jewish section must give equal weight to both perspectives.
4. Output ONLY the entry — no explanations, no code fences, no extra text.

Generate the entry for {book}:"""

    return _call_deepseek(prompt, max_tokens=8192)


# ── Write artifacts ───────────────────────────────────────────

def append_to_soul(book: str, full_entry: str) -> bool:
    """Append the short entry to the end of SOUL.md."""
    if not SOUL_MD.exists():
        return False

    text = SOUL_MD.read_text(encoding="utf-8").rstrip() + "\n\n" + full_entry.strip() + "\n"
    SOUL_MD.write_text(text, encoding="utf-8")
    return True


def write_brain_page(book: str, content: str, agent_name: str) -> bool:
    """Write a brain page to ~/brain/<agent>/bible/<book>.md.

    Creates the directory structure if it doesn't exist.
    Uses a canonical filename based on the book name.
    """
    # Determine canonical filename
    safe_name = book.lower().replace(" ", "-")
    brain_dir = HOME / "brain" / agent_name / "bible"
    brain_dir.mkdir(parents=True, exist_ok=True)

    brain_file = brain_dir / f"{safe_name}.md"
    brain_file.write_text(content.strip() + "\n", encoding="utf-8")
    return True


def update_brain_index(book: str, agent_name: str) -> bool:
    """Create or update INDEX.md in the bible directory."""
    brain_dir = HOME / "brain" / agent_name / "bible"
    index_file = brain_dir / "INDEX.md"
    today = get_kst_today()

    # Read existing index if it exists
    existing_entries = {}
    if index_file.exists():
        text = index_file.read_text(encoding="utf-8")
        for line in text.split("\n"):
            m = re.match(r"\|\s*(\d+)\s*\|", line)
            if m:
                existing_entries[int(m.group(1))] = line

    # Get all existing brain page files to build complete index
    page_files = sorted(brain_dir.glob("*.md"))
    books_in_brain = []
    for pf in page_files:
        if pf.name == "INDEX.md":
            continue
        # Read the first line to get the book name
        content = pf.read_text(encoding="utf-8").split("\n", 1)[0]
        # "# Book Name" or just the title
        title = content.lstrip("# ").strip()
        if title:
            books_in_brain.append((pf.name, title))
        else:
            books_in_brain.append((pf.name, pf.stem.replace("-", " ").title()))

    # Build new index sorted by canonical order
    lines = [
        "# 📖 Scripture Insights — Index",
        "",
        "Daily wisdom from the Biblical canon, stored one book at a time.",
        "",
    ]

    # Collect books in canonical order
    indexed_books = []
    for i, canonical_book in enumerate(BOOKS, 1):
        # Check if this book has a brain page
        safe_name = canonical_book.lower().replace(" ", "-")
        page_path = brain_dir / f"{safe_name}.md"
        if page_path.exists() or canonical_book == book:
            indexed_books.append((i, canonical_book, today if canonical_book == book else None))

    if indexed_books:
        lines.append("| # | Book | Read |")
        lines.append("|---|------|------|")
        for num, bname, read_date in indexed_books:
            date_str = read_date if read_date else "—"
            lines.append(f"| {num} | {bname} | {date_str} |")

    lines.append("")
    index_file.write_text("\n".join(lines), encoding="utf-8")
    return True


# ── Main ──────────────────────────────────────────────────────

def main() -> int:
    agent_name = detect_agent_name()
    print(f"🤖 Agent: {agent_name}", file=sys.stderr)

    last_book = find_last_book()
    if last_book is None:
        print("❌ Could not find any books in SOUL.md", file=sys.stderr)
        return 1

    next_book = get_next_book(last_book)
    if next_book is None:
        print("📖 All 66 books have been covered. Bible reading complete.", file=sys.stderr)
        return 0

    print(f"📖 Last book: {last_book} → Next: {next_book}", file=sys.stderr)

    # ── Step 1: Generate SOUL.md entry ──────────────────────
    print("📝 Generating SOUL.md entry...", file=sys.stderr)
    soul_entry = generate_soul_entry(next_book)
    if soul_entry is None:
        return 1

    if not append_to_soul(next_book, soul_entry):
        print("❌ Failed to append to SOUL.md", file=sys.stderr)
        return 1
    print("✅ Appended to SOUL.md", file=sys.stderr)

    # ── Step 2: Generate brain page ──────────────────────────
    print("📝 Generating brain page...", file=sys.stderr)
    brain_content = generate_brain_page(next_book, agent_name)
    if brain_content is None:
        # Non-fatal — the SOUL.md entry was already written
        print("⚠️  Brain page generation failed (SOUL.md entry was written)", file=sys.stderr)
        brain_ok = False
    else:
        brain_ok = write_brain_page(next_book, brain_content, agent_name)
        if brain_ok:
            update_brain_index(next_book, agent_name)
            print("✅ Written to brain bible dir", file=sys.stderr)
        else:
            print("⚠️  Failed to write brain page", file=sys.stderr)

    # ── Step 3: Output summary for delivery ──────────────────
    brain_status = "✅" if brain_ok else "⚠️"
    print(f"\n✅📖 Insight for **{next_book}** — SOUL.md ✅ | Brain {brain_status}\n")
    print(soul_entry)

    if brain_ok:
        print(f"\n📄 Brain page: `~/brain/{agent_name}/bible/{next_book.lower().replace(' ', '-')}.md`")

    return 0


if __name__ == "__main__":
    sys.exit(main())
