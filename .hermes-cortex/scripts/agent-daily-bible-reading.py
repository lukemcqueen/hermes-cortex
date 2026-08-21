#!/usr/bin/env python3
"""agent-daily-bible-reading.py — no_agent cron script.

Reads SOUL.md, determines the next canonical book to cover,
generates two artifacts via deepseek API:
  1. A SOUL.md entry (concise, lesson-focused)
  2. A rich brain page at ~/brain/<agent>/bible/<book>.md

Fleet-wide principles (Luke directive 2026-08-14):
  • EVERY reading is saved — a dated per-reading file
    (<book>-<YYYY-MM-DD>.md) is written each time, so repeated books
    accumulate their full studies instead of overwriting. The canonical
    <book>.md holds the latest reading.
  • EVERY reading includes the Ten Commandments (Ex 20:1–17) and Jesus'
    two commandments (Matt 22:37–40) — a deterministic block is appended
    to the brain page and a compact foundations reference is injected into
    the SOUL.md entry, never left to the LLM.

Silent when no new book needed (exit 0, empty stdout).
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
SOUL_MD = HOME / ".hermes" / "SOUL.md"
BRAIN_BIBLE = lambda agent: HOME / "brain" / agent / "bible"
OLLAMA_URL = "http://localhost:11434/api/chat"
KST = timezone.utc  # DEPRECATED — unused; dates use system local / HERMES_TIMEZONE

# ── Cycle tracking ─────────────────────────────────────────────
CYCLE_RE = re.compile(r"<!-- Bible Cycle:\s*(\d+)\s*-->")

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

# ── Foundations — every reading includes the commandments ──────────
# Fleet-wide principle (Luke directive 2026-08-14): EVERY saved bible
# reading must include the Ten Commandments and Jesus' two commandments.
# The block is added DETERMINISTICALLY script-side — never left to the LLM,
# so a model drift can never drop the foundations from a reading.
TEN_COMMANDMENTS = [
    "1. You shall have no other gods before Me.",
    "2. You shall not make for yourself a carved image — no idols.",
    "3. You shall not take the name of the LORD your God in vain.",
    "4. Remember the Sabbath day, to keep it holy.",
    "5. Honor your father and your mother.",
    "6. You shall not murder.",
    "7. You shall not commit adultery.",
    "8. You shall not steal.",
    "9. You shall not bear false witness against your neighbor.",
    "10. You shall not covet anything that is your neighbor's.",
]

JESUS_TWO_COMMANDMENTS = [
    "Love the Lord your God with all your heart, with all your soul, and with all your mind.",
    "Love your neighbor as yourself.",
]

COMMANDMENTS_REFERENCE = (
    "**Foundations:** 10 Commandments (Ex 20:1–17) · "
    "Jesus' two (Matt 22:37–40)"
)


def commandments_section(book: str) -> str:
    """Deterministic 'The Commandments' block appended to every brain page.

    Guarantees the fleet principle: no saved reading is ever without the
    Ten Commandments and Jesus' two commandments (Matt 22:37–40).
    """
    return "\n".join([
        "",
        "## The Commandments — Every Reading",
        "",
        f"*This reading of **{book}** is grounded in God's commandments (fleet principle).*",
        "",
        "**The Ten Commandments** (Exodus 20:1–17)",
        "",
        *TEN_COMMANDMENTS,
        "",
        "**Jesus' Two Commandments** (Matthew 22:37–40)",
        "",
        *[f"- {c}" for c in JESUS_TWO_COMMANDMENTS],
        "",
        "> \"On these two commandments hang all the Law and the Prophets.\" — Matthew 22:40",
        "",
        f"May {book} deepen obedience to God and love of neighbor.",
        "",
    ])

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
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

    # 1c. agent.env — canonical per-host identity written by cortex-update.sh
    agent_env = HOME / ".hermes-cortex" / "agent.env"
    if agent_env.exists():
        for line in agent_env.read_text().splitlines():
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
            except Exception as e:
                print(
                    f"⚠️  Could not read agent_name from {cp}: {e}",
                    file=sys.stderr,
                )

    # 3. SOUL.md first line: "# SOUL.md — AgentName"
    if SOUL_MD.exists():
        first_line = SOUL_MD.read_text(encoding="utf-8").split("\n", 1)[0]
        m = re.match(r"^#\s*SOUL\.md\s*[-–—]\s*(.+)", first_line)
        if m:
            name = m.group(1).strip()
            if name:
                return name

    # 4. Fallback — NEVER silently impersonate another agent (2026-08-06
    #    directive: tooling identity is host-derived; `hc` fell back to moses
    #    on every host until fixed). Derive from hostname and warn loudly.
    host_default = os.uname().nodename.split(".")[0] or "agent"
    print(
        f"⚠️  AGENT_NAME not found anywhere — using hostname-derived '{host_default}'. "
        f"Set AGENT_NAME in ~/.hermes-cortex/agent.env to fix.",
        file=sys.stderr,
    )
    return host_default


# ── Book tracking from SOUL.md ────────────────────────────────

def get_kst_today() -> str:
    """Return today's date in KST as YYYY-MM-DD."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d")


def find_last_book() -> str | None:
    """Determine the last book covered from the AUTHORITATIVE reading log:
    the dated brain files (<book>-<YYYY-MM-DD>.md), which are append-only,
    date-ordered, and never archived. This replaces the fragile SOUL.md-tail
    anchor (2026-08-18): archive_old_entries() kept only the last 2 entries,
    and the LLM-driven era (Jul 26–Aug 8 2026) corrupted the section with
    non-book headers, so get_next_book() returned None → false "all covered"
    → premature cycle reset → 26 books silently skipped (incl. all 4 Gospels).

    Falls back to SOUL.md's Scripture Insights tail ONLY when no dated files
    exist yet (fresh install / pre-dated-file era).
    """
    agent = detect_agent_name()
    brain_dir = BRAIN_BIBLE(agent)
    if brain_dir.is_dir():
        date_re = re.compile(r"^([a-z0-9-]+)-(\d{4}-\d{2}-\d{2})\.md$")
        best: tuple[str, str] | None = None  # (date, canonical book)
        for f in brain_dir.glob("*-????-??-??.md"):
            m = date_re.match(f.name)
            if not m:
                continue
            safe_name, date_str = m.group(1), m.group(2)
            for book in BOOKS:
                if book.lower().replace(" ", "-") == safe_name:
                    if best is None or date_str > best[0]:
                        best = (date_str, book)
                    break
        if best is not None:
            return best[1]

    # Fallback: SOUL.md Scripture Insights tail (pre-dated-file installs).
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


def _call_ollama(prompt: str, max_tokens: int = 4096) -> str | None:
    """Call local Ollama (qwen2.5:3b) and return the cleaned response content.
    Used as fallback when no DEEPSEEK_API_KEY is available."""
    payload = json.dumps({
        "model": "qwen2.5:3b",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": 0.7},
    })
    body = ""
    try:
        result = subprocess.run(
            ["curl", "-s", "-w", "\n%{http_code}", "-X", "POST", OLLAMA_URL,
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=300,
        )
        parts = result.stdout.strip().rsplit("\n", 1)
        http_code = parts[-1] if len(parts) > 1 else "000"
        body = parts[0] if len(parts) > 1 else result.stdout

        if result.returncode != 0:
            print(f"❌ curl failed (exit {result.returncode}): {result.stderr}", file=sys.stderr)
            return None
        if http_code != "200":
            print(f"❌ Ollama returned HTTP {http_code}: {body[:300]}", file=sys.stderr)
            return None

        response = json.loads(body)
        content = response.get("message", {}).get("content", "")

        if not content:
            print(f"❌ Empty response from Ollama", file=sys.stderr)
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
        print(f"❌ Ollama request timed out after 300s", file=sys.stderr)
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        return None


def _call_deepseek(prompt: str, max_tokens: int = 4096, temperature: float = 0.7, _retried: bool = False) -> str | None:
    """Make a deepseek API call and return the cleaned response content.
    Falls back to local Ollama if DEEPSEEK_API_KEY is not available."""
    api_key = get_deepseek_api_key()
    if not api_key:
        print("⚠️  DEEPSEEK_API_KEY not found — falling back to local Ollama (qwen2.5:3b)", file=sys.stderr)
        return _call_ollama(prompt, max_tokens)

    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
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
            print(f"⚠️  DeepSeek API returned HTTP {http_code} — falling back to local Ollama (qwen2.5:3b)", file=sys.stderr)
            if body:
                print(f"   Error body: {body[:300]}", file=sys.stderr)
            return _call_ollama(prompt, max_tokens)

        response = json.loads(body)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        if not content:
            # Empty content is not transient here: deepseek reasoning models
            # (deepseek-v4-flash) burn the whole token budget on
            # reasoning_content and return content="" with finish=length.
            # Bounded retry ONCE (was unbounded recursion — a persistent empty
            # response looped until the cron timeout, then silently dropped
            # the brain page while SOUL.md kept the entry → inconsistent state,
            # 2026-08-10). Use deepseek-chat (non-reasoning) to avoid the issue.
            print(f"⚠️  Empty response from API — retrying once", file=sys.stderr)
            time.sleep(5)
            if _retried:
                print(f"❌ Still empty after retry — giving up", file=sys.stderr)
                return None
            return _call_deepseek(prompt, max_tokens, temperature=temperature, _retried=True)

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
        if not _retried:
            print("⚠️  API request timed out after 180s — retrying once", file=sys.stderr)
            time.sleep(5)
            return _call_deepseek(prompt, max_tokens, temperature=temperature, _retried=True)
        print("❌ API request timed out after 180s (retry also timed out) — giving up", file=sys.stderr)
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        return None


# ── Verse selection styles — creative rotation ────────────────
# Luke directive 2026-08-21: don't default to each book's famous
# "memory verse" every run. Rotate among styles seeded by
# book + date + agent so (a) a single agent sees variety across
# days, (b) different agents diverge on the same day, and (c)
# repeat readings of the same book yield different verses.
VERSE_STYLES: dict[str, str] = {
    "anchor": (
        "Pick ONE key verse that genuinely captures the book's core message. "
        "Include the exact citation."
    ),
    "hidden-gem": (
        "Pick ONE verse that captures the book's message — but it must NOT be "
        "the book's most famous, most-quoted verse, and NOT the verse a memory "
        "app or commentary would lead with. Test your pick: if it is the verse "
        "that first comes to mind for this book, discard it and choose a "
        "different one. The pick should surprise a reader who only knows the "
        "book's highlights while still being faithful. Include the exact "
        "citation."
    ),
    "fresh-angle": (
        "Pick ONE verse from a surprising angle — it must NOT be the verse most "
        "commonly quoted from this book, the one that appears in every "
        "overview. Before finalizing, test your pick: if a casual reader would "
        "guess it as 'the famous one from this book', discard it. Choose from "
        "the book's overlooked corners: a minor character, a quiet moment, an "
        "unusual promise, a striking image. The verse must genuinely be in the "
        "book and fairly represent it. Include the exact citation."
    ),
}


def pick_verse_style(book: str, agent_name: str) -> str:
    """Deterministic style per (book, agent) with a day counter.

    style = (stable_hash(book|agent) + days_since_epoch) % len(styles):
    - consecutive days ALWAYS land on different styles (day counter +1),
    - different agents start at different offsets → diverge on the same day,
    - repeat readings of a book later in the cycle land elsewhere.
    Never use built-in hash() — its seed is randomized per process.
    """
    day_offset = (datetime.strptime(get_kst_today(), "%Y-%m-%d") - datetime(2026, 1, 1)).days
    seed = f"{book}|{agent_name}"
    base = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16) % len(VERSE_STYLES)
    return list(VERSE_STYLES)[(base + day_offset) % len(VERSE_STYLES)]


def _famous_verses(book: str) -> list[str]:
    """Ask the model for the book's famous verses (two probes, union).

    Creative styles forbid these exact citations. Two kinds of verse anchor
    the model: classic memory verses AND recognizable story icons (e.g. the
    fish verse, Jonah 1:17, which is no memory verse but is the first verse
    that comes to mind). One probe misses one kind (live test 2026-08-21:
    memory-verse probe returned Jonah 2:9/1:3/4:2 while the generator's
    anchor was Jonah 1:17). Union of both probes, deduped, up to 6 verses.
    Returns [] on API failure — the caller degrades gracefully.
    """
    questions = [
        f"List the 3 most-quoted, most famous 'memory verses' of the book of "
        f"{book}, in order of fame.",
        f"List the 3 verses from the book of {book} that a casual reader "
        f"would MOST expect to see quoted — the recognizable story verses — "
        f"in order.",
    ]
    found: list[str] = []
    for q in questions:
        prompt = (
            q + " Reply with ONLY the citations, one per line, in this exact "
            "format: Book Chapter:Verse (e.g. 'John 3:16'). No explanations, "
            "no verse text."
        )
        resp = _call_deepseek(prompt, max_tokens=64, temperature=0.0)
        if not resp:
            continue
        for m in re.finditer(r"([A-Za-z0-9 ]+?)\s+(\d+):(\d+)", resp):
            name = m.group(1).strip()
            cit = f"{name} {m.group(2)}:{m.group(3)}"
            if cit not in found:
                found.append(cit)
            if len(found) >= 6:
                break
    return found[:6]


def _extract_citation(entry: str) -> str | None:
    """Pull the (Book Chapter:Verse) citation out of a SOUL entry header."""
    m = re.search(r"\(([^()]*\d+:\d+[^()]*)\)", entry)
    return m.group(1) if m else None


def _cites_forbidden(entry: str, forbidden: str) -> bool:
    """True if the entry's citation starts at the forbidden chapter:verse.

    Compares only the Chapter:Verse token so abbreviated book names
    ('Hab 2:14' vs 'Habakkuk 2:14') and verse ranges ('2:14–15') both
    resolve correctly.
    """
    cit = _extract_citation(entry)
    if not cit:
        return False
    fv = re.search(r"(\d+:\d+)", forbidden)
    cv = re.search(r"(\d+:\d+)", cit)
    return bool(fv and cv and fv.group(1) == cv.group(1))


def _prior_verses(book: str, agent_name: str) -> list[str]:
    """Citations used by THIS book in earlier cycles (repeat readings).

    Sources, most-durable first (Luke directive 2026-08-21: a repeat reading
    must produce a NEW verse and NEW insights — the ban covers ALL prior
    cycles):
    1. Dated per-reading brain files (`<book>-YYYY-MM-DD.md`) — the
       append-only, never-archived record; every reading since 2026-08-21
       carries a structured `*Key verse:*` marker (stamped script-side from
       the accepted SOUL entry). This is the complete verse history.
    2. Legacy SOUL-entry sources for pre-marker readings: SOUL.md tail,
       `archive/SOUL-archive.md`, and `cycle-*-completed.md`.
    Returns [] on a book's first cycle — fine the first time.
    """
    found: list[str] = []
    brain_dir = BRAIN_BIBLE(agent_name)
    safe = book.lower().replace(" ", "-")
    marker_re = re.compile(r"^\*Key verse:\s*\*?(.+?)\*?\s*$")

    # 1. Dated per-reading files — the durable marker record (all cycles)
    for f in sorted(brain_dir.glob(f"{safe}-????-??-??.md")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            mm = marker_re.match(line.strip())
            if mm:
                cit = mm.group(1).strip()
                if cit not in found:
                    found.append(cit)

    # 2. Legacy SOUL-entry sources (pre-marker history)
    header_re = re.compile(rf"^### {re.escape(book)} — ", re.IGNORECASE)
    sources: list[Path] = []
    if SOUL_MD.exists():
        sources.append(SOUL_MD)
    archive_file = brain_dir / "archive" / "SOUL-archive.md"
    if archive_file.exists():
        sources.append(archive_file)
    sources.extend(sorted(brain_dir.glob("cycle-*-completed.md")))

    for src in sources:
        try:
            text = src.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            if header_re.match(line):
                cit = _extract_citation(line)
                if cit and cit not in found:
                    found.append(cit)
    return found


def generate_soul_entry(book: str, agent_name: str | None = None) -> str | None:
    """Generate the concise SOUL.md entry (short format — verse + one-line commitment)."""
    today = get_kst_today()
    if agent_name is None:
        agent_name = detect_agent_name()
    style = pick_verse_style(book, agent_name)
    verse_instruction = VERSE_STYLES[style]
    # Creative styles get more temperature — the famous-verse anchor is hard
    # to break at 0.7 (live test 2026-08-21: fresh-angle still returned the
    # book's most-quoted verse at 0.7).
    temperature = 0.7 if style == "anchor" else 1.1

    # Forbidden verses: prior-cycle picks for this book are ALWAYS forbidden
    # — a repeat reading (next pass through the canon, ~66 days later) must
    # not duplicate earlier picks (Luke directive 2026-08-21: fine the first
    # time). Creative styles additionally forbid the book's famous verses.
    forbidden = _prior_verses(book, agent_name)
    if style != "anchor":
        for fv in _famous_verses(book):
            if fv not in forbidden:
                forbidden.append(fv)
    if forbidden:
        banned = ", ".join(forbidden)
        verse_instruction += (
            f" It must NOT be any of: {banned} — those exact verses are "
            "forbidden for this entry."
        )

    prompt = f"""You are writing a "Scripture Insight" entry for an AI agent's character document (SOUL.md). SOUL.md is now a compressed document (~5KB) — each scripture entry is just a few lines.

Write the entry for **{book}** in this EXACT format:

### {book} — *"[key verse]" ([Book Chapter:Verse])*

I will [one-line behavioral commitment for a system operator — automation, monitoring, reliability, documentation, cron jobs, config files, deployments, log analysis, health checks, rollbacks, etc.].

**Foundations:** 10 Commandments (Ex 20:1–17) · Jesus' two (Matt 22:37–40)

<!-- Added {today} -->

Requirements:
1. {verse_instruction}
2. The "I will" line must be a single, concrete behavioral commitment. Start with "I will" and make it something an automation agent can actually do. No metaphors, no generic life advice.
3. The "**Foundations:**" line is MANDATORY — it must appear verbatim (fleet principle: every reading is grounded in the 10 Commandments and Jesus' two commandments).
4. Output ONLY these lines — no explanations, no code fences, no extra text.
5. The date comment goes on its own line at the end.

Generate the entry for {book}:"""

    # Hard-guarantee forbidden verses never land: re-roll with REJECTION
    # FEEDBACK (name the banned pick — the model otherwise never learns its
    # attempt was refused; live test 2026-08-21: Jonah 1:17 returned on all
    # 3 attempts at fixed temperature) plus slight temperature escalation,
    # up to 4 attempts total. Anchor has no famous-verse ban but still
    # honors prior-cycle bans.
    entry = None
    for _ in range(4):
        entry = _call_deepseek(prompt, max_tokens=1024, temperature=temperature)
        if not entry or not any(_cites_forbidden(entry, f) for f in forbidden):
            break
        cit = _extract_citation(entry) or "the verse you chose"
        prompt = prompt.rstrip() + (
            f"\n\nYour previous attempt chose {cit}, which is explicitly "
            "forbidden for this entry. Choose a different verse. Output ONLY "
            "the corrected entry in the exact same format."
        )
        temperature += 0.2
    return entry


def ensure_foundations_line(entry: str) -> str:
    """Deterministically guarantee the commandments reference in a SOUL entry.

    The fleet principle says EVERY reading includes the 10 Commandments and
    Jesus' two commandments — so even if the LLM omits the foundations line,
    it is injected before the date comment (Luke directive 2026-08-14).
    """
    if COMMANDMENTS_REFERENCE in entry:
        return entry
    # Insert before the trailing <!-- Added ... --> comment, or append.
    lines = entry.rstrip().split("\n")
    date_idx = next((i for i, l in enumerate(lines) if l.startswith("<!-- Added")), None)
    if date_idx is not None:
        lines.insert(date_idx, COMMANDMENTS_REFERENCE)
    else:
        lines.append(COMMANDMENTS_REFERENCE)
    return "\n".join(lines) + "\n"


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

## Behavioral Commitment

[Write the one-line "I will" behavioral commitment for a system operator — same line that goes into SOUL.md. Be specific and concrete: "I will [action] so that [outcome]."]

## Insight for {agent_name}

[A single paragraph connecting the book's core message to practical application for {agent_name}, a system operator and automation agent. Be specific and concrete, relating to monitoring, infrastructure, documentation, reliability, delegation, or leadership.]

## Connection to the Commandments

[One short paragraph: how this book's message connects to the Ten Commandments (Ex 20:1-17) and Jesus' two commandments — love God with all your heart/soul/mind and love your neighbor as yourself (Matt 22:37-40). The commandments section is appended deterministically after your output — this paragraph should make the connection explicit so the reading is grounded in God's foundations.]

Requirements:
1. Be factually accurate — cite real archaeological finds, real scholars, real textual evidence.
2. Include the Hebrew or Greek script for original language insights.
3. The Jewish & Messianic Jewish section must give equal weight to both perspectives.
4. Output ONLY the entry — no explanations, no code fences, no extra text.

Generate the entry for {book}:"""

    return _call_deepseek(prompt, max_tokens=8192)


# ── Write artifacts ───────────────────────────────────────────

def append_to_soul(book: str, full_entry: str) -> bool:
    """Append the full entry to SOUL.md before the Session Mining Lessons section."""
    if not SOUL_MD.exists():
        return False

    text = SOUL_MD.read_text(encoding="utf-8")

    # Insert before "## Final Directive" if present
    marker = "## Final Directive"
    if marker in text:
        full_block = f"\n{full_entry}\n\n"
        new_text = text.replace(f"\n{marker}", f"{full_block}{marker}", 1)
    else:
        full_block = f"\n{full_entry}\n"
        new_text = text + full_block

    SOUL_MD.write_text(new_text, encoding="utf-8")
    return True


def write_brain_page(book: str, content: str, agent_name: str) -> bool:
    """Write a brain page to ~/brain/<agent>/bible/.

    EVERY reading is saved (Luke directive 2026-08-14): a dated per-reading
    file (<book>-<YYYY-MM-DD>.md) is written each time so repeated books
    accumulate their full studies instead of overwriting. The canonical
    <book>.md is refreshed with the latest reading for continuity and any
    existing links.
    """
    safe_name = book.lower().replace(" ", "-")
    today = get_kst_today()
    brain_dir = HOME / "brain" / agent_name / "bible"
    brain_dir.mkdir(parents=True, exist_ok=True)

    # Migration guard (2026-08-14): a canonical <book>.md written BEFORE this
    # feature has no dated twin — preserve it with its mtime date so a repeat
    # reading never silently destroys the prior study. Runs once per book
    # (after the first new-code read the dated twin exists → no re-snapshot).
    canonical_file = brain_dir / f"{safe_name}.md"
    if canonical_file.exists() and not list(brain_dir.glob(f"{safe_name}-????-??-??.md")):
        try:
            mt = datetime.fromtimestamp(canonical_file.stat().st_mtime).strftime("%Y-%m-%d")
        except OSError:
            mt = today
        snap = brain_dir / f"{safe_name}-{mt}.md"
        if not snap.exists():
            snap.write_text(canonical_file.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"  📦 Preserved pre-feature reading -> {snap.name}", file=sys.stderr)

    # Per-reading file — multiples preserved, never overwritten
    dated_file = brain_dir / f"{safe_name}-{today}.md"
    dated_file.write_text(content.strip() + "\n", encoding="utf-8")
    # Canonical latest — refreshed each reading
    canonical_file.write_text(content.strip() + "\n", encoding="utf-8")
    return True


def update_brain_index(agent_name: str) -> bool:
    """Create or update INDEX.md — one row per READING (multiples listed).

    Each dated reading file (<book>-<YYYY-MM-DD>.md) becomes its own row so
    repeated books are all visible with their dates. Books read before this
    feature (canonical file only) get a single row with '—'.
    """
    brain_dir = HOME / "brain" / agent_name / "bible"
    index_file = brain_dir / "INDEX.md"
    if not brain_dir.is_dir():
        return False

    date_re = re.compile(r"^([a-z0-9-]+)-(\d{4}-\d{2}-\d{2})\.md$")
    rows: list[tuple[int, str, str]] = []
    for i, canonical_book in enumerate(BOOKS, 1):
        safe = canonical_book.lower().replace(" ", "-")
        dated = sorted(brain_dir.glob(f"{safe}-????-??-??.md"))
        if dated:
            for df in dated:
                m = date_re.match(df.name)
                rows.append((i, canonical_book, m.group(2) if m else "—"))
        elif (brain_dir / f"{safe}.md").exists():
            rows.append((i, canonical_book, "—"))  # pre-feature read

    lines = [
        "# 📖 Scripture Insights — Index",
        "",
        "Daily wisdom from the Biblical canon — every reading saved, one file per reading.",
        "",
        "| # | Book | Read |",
        "|---|------|------|",
    ]
    for num, bname, date_str in rows:
        lines.append(f"| {num} | {bname} | {date_str} |")
    lines.append("")
    index_file.write_text("\n".join(lines), encoding="utf-8")
    return True


# ── Main ──────────────────────────────────────────────────────

def get_cycle() -> int:
    """Read the current bible cycle from SOUL.md comment."""
    if not SOUL_MD.exists():
        return 1
    text = SOUL_MD.read_text(encoding="utf-8")
    m = CYCLE_RE.search(text)
    return int(m.group(1)) if m else 1


def set_cycle(cycle: int) -> None:
    """Set the bible cycle number in SOUL.md. Creates or replaces the comment."""
    if not SOUL_MD.exists():
        return
    text = SOUL_MD.read_text(encoding="utf-8")
    comment = f"<!-- Bible Cycle: {cycle} -->"
    if CYCLE_RE.search(text):
        text = CYCLE_RE.sub(comment, text)
    else:
        text = text + f"\n{comment}\n"
    SOUL_MD.write_text(text, encoding="utf-8")


def archive_and_reset(agent_name: str) -> None:
    """Archive current Scripture Insights to brain/, clear from SOUL.md, increment cycle."""
    if not SOUL_MD.exists():
        return
    text = SOUL_MD.read_text(encoding="utf-8")
    cycle = get_cycle()

    # Extract current entries for archive
    insights_section = text.split("## Scripture Insights")[-1]
    insights_section = insights_section.split("## Final Directive")[0]

    # Archive the completed cycle's scripture insights
    brain_dir = BRAIN_BIBLE(agent_name)
    brain_dir.mkdir(parents=True, exist_ok=True)
    archive_file = brain_dir / f"cycle-{cycle}-completed.md"
    archive_file.write_text(
        f"# Bible Cycle {cycle} — Completed\n\n"
        f"*Archived: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
        f"{insights_section.strip()}\n",
        encoding="utf-8",
    )

    # Clear Scripture Insights section between the headers
    new_cycle = cycle + 1
    new_text = text.replace(
        f"## Scripture Insights{insights_section}## Final Directive",
        f"## Scripture Insights\n\n## Final Directive",
    )
    # Also ensure the cycle comment is updated
    new_text = CYCLE_RE.sub(f"<!-- Bible Cycle: {new_cycle} -->", new_text)
    SOUL_MD.write_text(new_text, encoding="utf-8")
    print(f"♻️  Bible Cycle {cycle} complete! Archived to brain/. Starting Cycle {new_cycle}.", file=sys.stderr)


def archive_old_entries(agent_name: str, max_before_archive: int = 3, max_kept: int = 2) -> int:
    """Move old book entries from SOUL.md Scripture Insights to the archive.

    Keeps the section bounded (doctor check_soul_sync FAILs SOUL.md > 20K).
    Each book entry is treated as a BLOCK: the '### Book —' header plus all
    following lines (commitment text, date comment) until the next '### '
    header or the section end — whole blocks are moved so no orphaned text
    is left behind. Everything outside the Scripture Insights section
    (Final Directive, agent docs, etc.) is preserved verbatim. Returns the
    number archived (0 = nothing to archive).
    """
    if not SOUL_MD.exists():
        return 0
    text = SOUL_MD.read_text(encoding="utf-8")
    marker = "## Scripture Insights"
    if marker not in text:
        return 0
    marker_end = text.index(marker) + len(marker)

    # Section body = everything after the marker up to the next top-level '## ' header
    rest = text[marker_end:]
    m = re.search(r"\n## ", rest)
    section_end = m.start() if m else len(rest)
    section = rest[:section_end]
    tail = rest[section_end:]  # Final Directive + everything after — MUST be preserved

    # Split the section into blocks: each '### Book —' header starts a block
    # that runs until the next '### ' header or the section end. Lines before
    # the first book header (the intro paragraph) form the preamble, kept as-is.
    lines = section.split("\n")
    preamble = []
    blocks = []  # (is_book, [lines])
    current = None
    for line in lines:
        bm = re.match(r"^### ([A-Za-z0-9 ]+) —", line.strip())
        if bm:
            if current is not None:
                blocks.append(current)
            current = [bm.group(1).strip() in BOOK_INDEX, [line]]
        elif current is None:
            preamble.append(line)  # everything before the first book header
        else:
            current[1].append(line)
    if current is not None:
        blocks.append(current)

    book_blocks = [b for b in blocks if b[0]]
    if len(book_blocks) <= max_before_archive:
        return 0

    archive = book_blocks[:-max_kept]  # oldest blocks
    keep = book_blocks[-max_kept:]     # newest blocks
    kept_set = {id(b) for b in keep}

    brain_dir = BRAIN_BIBLE(agent_name)
    archive_file = brain_dir / "archive" / "SOUL-archive.md"
    archive_file.parent.mkdir(parents=True, exist_ok=True)
    with archive_file.open("a", encoding="utf-8") as f:
        f.write(f"\n## Cycle {get_cycle()} archive ({len(archive)} entries)\n\n")
        for b in archive:
            f.write("\n".join(b[1]).strip() + "\n\n")

    new_section = "\n".join(preamble) + "\n" if preamble else ""
    for b in blocks:
        if b[0] and id(b) not in kept_set:
            continue  # archived blocks removed
        new_section += "\n".join(b[1]) + "\n"

    new_text = text[:marker_end] + new_section + tail
    SOUL_MD.write_text(new_text, encoding="utf-8")
    print(f"  📦 Archived {len(archive)} old entries to {archive_file}", file=sys.stderr)
    return len(archive)


def _enforce_short_gleaning(entry: str, book: str, max_chars: int = 800) -> str:
    """Enforce the short-gleaning rule (user directive 2026-08-03).

    SOUL.md scripture entries must be BRIEF — the full study lives in
    ~/brain/<agent>/bible/<book>.md (mybrain). If the generated entry
    exceeds max_chars, reduce it to the canonical 3-line shape:
    header, a ONE-SENTENCE "I will" commitment line, date comment.
    """
    if len(entry) <= max_chars:
        return entry

    lines = [l.strip() for l in entry.splitlines() if l.strip()]
    header = next((l for l in lines if l.startswith("### ")), f"### {book}")
    commitment = next((l for l in lines if l.startswith("I will")), "")
    foundations = next((l for l in lines if l.startswith("**Foundations:**")), "")
    date_comment = next((l for l in lines if l.startswith("<!-- Added")), "")

    # Truncate the commitment to its first sentence if it is a run-on.
    if len(commitment) > 220:
        for sep in (". ", "! ", "? "):
            if sep in commitment:
                commitment = commitment.split(sep, 1)[0] + sep.strip()
                break

    kept = [header]
    if commitment:
        kept.append(commitment)
    if foundations:
        kept.append(foundations)
    if date_comment:
        kept.append(date_comment)

    trimmed = "\n\n".join(kept) + "\n"
    print(
        f"  ✂️  Entry was {len(entry)} chars (> {max_chars}) — trimmed to short gleaning "
        f"({len(trimmed)} chars); full study stays in brain page.",
        file=sys.stderr,
    )
    return trimmed


def main() -> int:
    agent_name = detect_agent_name()
    print(f"🤖 Agent: {agent_name}", file=sys.stderr)
    cycle = get_cycle()
    print(f"🔄 Bible Cycle: {cycle}", file=sys.stderr)

    last_book = find_last_book()

    # Edge case 1: No books in SOUL.md — start from Genesis
    if last_book is None:
        next_book = BOOKS[0]  # Genesis
        print(f"📖 No books found — starting from Genesis (Cycle {cycle})", file=sys.stderr)

    else:
        next_book = get_next_book(last_book)

        # Edge case 2: All 66 books covered — archive, reset, restart from Genesis
        # Guard: only Revelation (last canonical book) legitimately triggers the
        # reset. A None from get_next_book() on any OTHER book means a corrupted
        # anchor, NOT completion — treat it as "start from Genesis" without
        # archiving (2026-08-18: a false reset here silently skipped 26 books).
        if next_book is None:
            if last_book == BOOKS[-1]:
                print(f"📖 All 66 books covered in Cycle {cycle}. Resetting...", file=sys.stderr)
                archive_and_reset(agent_name)
                next_book = BOOKS[0]
                print(f"♻️  Restarting from Genesis (Cycle {cycle + 1})", file=sys.stderr)
            else:
                print(f"⚠️  Anchor corruption: last_book={last_book!r} has no successor — restarting from Genesis without archiving", file=sys.stderr)
                next_book = BOOKS[0]

    print(f"📖 Last book: {last_book} → Next: {next_book}", file=sys.stderr)

    # ── Step 1: Generate SOUL.md entry ──────────────────────
    print("📝 Generating SOUL.md entry...", file=sys.stderr)
    soul_entry = generate_soul_entry(next_book, agent_name)
    if soul_entry is None:
        return 1

    # Short-gleaning guard: SOUL.md entries must be brief (~2-3 lines);
    # the full study lives in the brain page (mybrain).
    soul_entry = _enforce_short_gleaning(soul_entry, next_book)

    # Fleet principle (2026-08-14): every reading includes the commandments
    # reference — inject deterministically if the LLM omitted it.
    soul_entry = ensure_foundations_line(soul_entry)

    if not append_to_soul(next_book, soul_entry):
        print("❌ Failed to append to SOUL.md", file=sys.stderr)
        return 1
    print("✅ Appended to SOUL.md", file=sys.stderr)

    # Keep the Scripture Insights section bounded: archive entries beyond
    # the last 2 book entries so SOUL.md stays under the doctor's 20K bound.
    archived = archive_old_entries(agent_name)

    # ── Step 2: Generate brain page ──────────────────────────
    print("📝 Generating brain page...", file=sys.stderr)
    brain_content = generate_brain_page(next_book, agent_name)
    if brain_content is None:
        # Non-fatal — the SOUL.md entry was already written
        print("⚠️  Brain page generation failed (SOUL.md entry was written)", file=sys.stderr)
        brain_ok = False
    else:
        # Fleet principle (2026-08-14): append the deterministic
        # commandments block so EVERY saved reading carries the Ten
        # Commandments and Jesus' two commandments (Matt 22:37–40).
        brain_content = brain_content.rstrip() + "\n" + commandments_section(next_book)
        # Durable verse record (Luke directive 2026-08-21): stamp the
        # accepted key verse into the brain page. The dated per-reading
        # files are append-only and never archived — with this marker they
        # become the complete per-book verse history across ALL cycles, so
        # repeat readings always get a NEW verse and NEW insights.
        today = get_kst_today()
        cit = _extract_citation(soul_entry)
        if cit:
            read_line = f"*Read: {today}*"
            marker = f"\n*Key verse: {cit}*"
            if read_line in brain_content:
                brain_content = brain_content.replace(read_line, read_line + marker, 1)
            else:
                brain_content = brain_content.rstrip() + marker + "\n"
        brain_ok = write_brain_page(next_book, brain_content, agent_name)
        if brain_ok:
            update_brain_index(agent_name)
            print("✅ Written to brain bible dir (dated + canonical)", file=sys.stderr)
        else:
            print("⚠️  Failed to write brain page", file=sys.stderr)

    # ── Step 3: Output summary for delivery ──────────────────
    brain_status = "✅" if brain_ok else "⚠️"
    print(f"\n✅📖 Insight for **{next_book}** — SOUL.md ✅ | Brain {brain_status} | ⛪ Commandments ✅\n")
    print(soul_entry)

    if brain_ok:
        today = get_kst_today()
        safe_name = next_book.lower().replace(" ", "-")
        print(f"\n📄 Brain page: `~/brain/{agent_name}/bible/{safe_name}-{today}.md` (+ canonical `{safe_name}.md`)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
