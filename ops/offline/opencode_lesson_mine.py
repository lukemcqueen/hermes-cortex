#!/usr/bin/env python3
"""
Hermes Cortex — OpenCode Session Lesson Miner
─────────────────────────────────────────────
Mines OpenCode session history for bug-fix lessons.
Seeds the ~/brain/lessons/ database from OpenCode's rich history.

Usage:
  opencode-mine                          # Interactive: review suggestions
  opencode-mine --auto --limit 20        # Auto-save top 20 by confidence
  opencode-mine --dry-run --days 30      # Preview only
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

HOME = Path.home()
OPENCODE_DB = HOME / ".local" / "share" / "opencode" / "opencode.db"
LESSONS = HOME / "brain" / "lessons"

# Error/fix patterns
ERROR_PATTERNS = [
    r"(?:Error|Exception|Traceback|Failed|fatal):?\s*([^\n]{10,200})",
    r"(?:sqlite3|psycopg2|requests|docker|fastapi|pydantic)\.\w*Error:\s*([^\n]{10,200})",
    r"(?:HTTP|status)\s+\d{3}\s+[^\n]{10,200}",
    r"(?:returning|returned|getting|throws?)\s+.{10,200}(?:error|exception|fail)",
    r"(?:failed to|unable to|couldn't|cannot)\s+.{10,200}",
]

CAUSE_PATTERNS = [
    (r"(?:root cause|caused by|because|due to|reason)[:\s]+(.{10,200}?)(?:\.|$)", 1),
    (r"(?:the issue was|the problem was|turns? out)\s+(.{10,200}?)(?:\.|$)", 1),
    (r"(?:missing|forgot|forgotten|wasn't|weren't|didn't)\s+(.{10,200}?)(?:\.|$)", 1),
]

SOLUTION_PATTERNS = [
    (r"(?:fixed|fix|solution|resolved|solved)\s+(?:by|with|using):?\s*(.{10,200}?)(?:\.|$)", 1),
    (r"(?:added|changed|updated|modified|replaced|removed|set|enabled|disabled)\s+(.{10,200}?)(?:\.|$)", 1),
    (r"(?:workaround|fix):?\s*(.{10,200}?)(?:\.|$)", 1),
]

LANG_PATTERNS = {
    "python": [r"import\s+\w+", r"def\s+\w+\s*\(", r"class\s+\w+.*:"],
    "javascript": [r"const\s+\w+\s*=", r"function\s+\w+\s*\(", r"=>\s*{"],
    "typescript": [r"interface\s+\w+", r":\s*(string|number|boolean)\b"],
    "go": [r"func\s+\w+\s*\(", r"package\s+\w+"],
    "rust": [r"fn\s+\w+\s*\(", r"let\s+mut\s+\w+"],
    "shell": [r"#!/bin/", r"\$\(.*\)"],
    "sql": [r"SELECT\s+.*\s+FROM", r"CREATE\s+TABLE"],
    "yaml": [r"^\s*\w+:", r"^\s*-\s+\w+:"],
}

FRAMEWORK_PATTERNS = {
    "fastapi": [r"FastAPI", r"fastapi"],
    "flask": [r"Flask\b", r"flask"],
    "django": [r"django"],
    "react": [r"React", r"react", r"jsx"],
    "docker": [r"Docker|docker compose|dockerfile"],
    "pydantic": [r"pydantic|BaseModel", r"ConfigDict"],
    "nextjs": [r"Next\.js|nextjs|next\.js"],
}

TAG_KEYWORDS = {
    "validation", "authentication", "authorization", "database",
    "deployment", "networking", "performance", "security",
    "migration", "testing", "docker", "configuration",
    "serialization", "concurrency", "error-handling", "api",
    "frontend", "backend", "cli", "monitoring",
}


def get_recent_sessions(days: int = 30) -> list:
    """Get sessions from the last N days with their full message text."""
    if not OPENCODE_DB.exists():
        print(f"❌ OpenCode DB not found at {OPENCODE_DB}")
        return []

    cutoff = int((datetime.now().timestamp() * 1000) - (days * 86400 * 1000))

    conn = sqlite3.connect(str(OPENCODE_DB))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    sessions = cur.execute("""
        SELECT s.id, s.title, s.time_created, s.time_updated
        FROM session s
        WHERE s.time_updated > ?
          AND s.title != 'New session - 2026-05-22T00:29:34.680Z'
          AND s.title NOT LIKE 'New session%'
        ORDER BY s.time_updated DESC
        LIMIT 100
    """, (cutoff,)).fetchall()

    results = []
    for s in sessions:
        # Get all parts with text content — user prompts, assistant reasoning, tool output
        parts = cur.execute("""
            SELECT p.data, json_extract(m.data, '$.role') as role
            FROM part p
            JOIN message m ON p.message_id = m.id
            WHERE m.session_id = ?
              AND json_extract(p.data, '$.type') IN ('text', 'reasoning', 'tool')
              AND json_extract(p.data, '$.type') != 'step-start'
              AND json_extract(p.data, '$.type') != 'step-finish'
            ORDER BY m.time_created ASC
        """, (s["id"],)).fetchall()

        text_parts = []
        for p, role in parts:
            try:
                data = json.loads(p)
                ptype = data.get("type", "")
                if ptype == "reasoning":
                    t = data.get("text", "")
                elif ptype == "tool":
                    inp = data.get("state", {}).get("input", {})
                    if isinstance(inp, dict):
                        t = inp.get("content", "") or json.dumps(inp)
                    else:
                        t = str(inp)
                    out = data.get("state", {}).get("output", "")
                    if out:
                        t = f"{t}\n{out}"[:3000]
                else:
                    t = data.get("text", "")

                if t and len(t) > 30:
                    text_parts.append(t)
            except (json.JSONDecodeError, TypeError):
                continue

        if text_parts:
            results.append({
                "id": s["id"],
                "title": s["title"],
                "time_created": s["time_created"],
                "time_updated": s["time_updated"],
                "text": "\n\n".join(text_parts),
            })

    conn.close()
    return results


def extract_fix(text: str) -> Optional[dict]:
    """Extract problem → cause → solution from text."""
    if not text or len(text) < 60:
        return None

    result = {"problem": "", "cause": "", "solution": ""}

    # Problem: look for error messages
    for pat in ERROR_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                val = (m.group(1) or m.group(0)).strip()[:200]
            except IndexError:
                val = m.group(0).strip()[:200]
            if len(val) > 10:
                result["problem"] = val
                break

    # Cause
    for pat, group in CAUSE_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(group).strip()[:200]
            if len(val) > 10:
                result["cause"] = val
                break

    # Solution
    for pat, group in SOLUTION_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(group).strip()[:200]
            if len(val) > 10:
                result["solution"] = val
                break

    if result["problem"] and (result["cause"] or result["solution"]):
        return result
    return None


def detect_language(text: str) -> str:
    scores = {}
    for lang, pats in LANG_PATTERNS.items():
        count = sum(1 for p in pats if re.search(p, text, re.MULTILINE))
        if count > 0:
            scores[lang] = count
    return max(scores, key=scores.get) if scores else ""


def detect_framework(text: str) -> str:
    for fw, pats in FRAMEWORK_PATTERNS.items():
        if any(re.search(p, text, re.IGNORECASE) for p in pats):
            return fw
    return ""


def extract_tags(text: str) -> list:
    found = set()
    for tag in TAG_KEYWORDS:
        if tag in text.lower():
            found.add(tag)
    return sorted(found) if found else ["bug-fix"]


def save_lesson(title: str, problem: str, cause: str, solution: str,
                evidence: str = "", language: str = "", framework: str = "",
                tags: list = None, source: str = "opencode-mine") -> dict:
    LESSONS.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).isoformat()
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:80]
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_prefix}_{slug}.md"
    filepath = LESSONS / filename

    tags_str = ", ".join(tags) if tags else ""

    content = f"""---
title: "{title}"
created: "{timestamp}"
updated: "{timestamp}"
language: {language}
framework: {framework}
tags: [{tags_str}]
project: ""
success_count: 1
source: {source}
---

## Problem

{problem}

## Root Cause

{cause}

## Solution

{solution}

## Evidence

{evidence}
"""

    filepath.write_text(content.strip() + "\n", encoding="utf-8")
    return {"path": str(filepath), "filename": filename}


def mine_opencode(days: int = 30, auto: bool = False, dry_run: bool = False,
                  limit: int = 50) -> dict:
    """Mine OpenCode sessions for bug-fix lessons."""
    print(f"🔍 Mining OpenCode sessions (last {days} days)...\n")

    sessions = get_recent_sessions(days)
    if not sessions:
        print("📭 No recent OpenCode sessions found.")
        return {"found": 0, "saved": 0}

    print(f"   Found {len(sessions)} sessions with text content\n")

    candidates = []
    for s in sessions:
        fix = extract_fix(s["text"])
        if fix:
            title = s["title"][:80]
            language = detect_language(s["text"])
            framework = detect_framework(s["text"])
            tags = extract_tags(s["text"])
            candidates.append({**fix, "title": title, "language": language,
                              "framework": framework, "tags": tags,
                              "evidence": s["text"][:500]})

    if not candidates:
        print("📭 No fix patterns found in OpenCode sessions.")
        return {"found": 0, "saved": 0}

    # Sort by confidence
    for c in candidates:
        has_p = len(c["problem"]) > 15
        has_c = len(c["cause"]) > 10
        has_s = len(c["solution"]) > 10
        c["confidence"] = round(has_p * 0.3 + has_c * 0.3 + has_s * 0.4, 2)

    candidates.sort(key=lambda x: x["confidence"], reverse=True)

    if limit and len(candidates) > limit:
        candidates = candidates[:limit]

    print(f"📋 Found {len(candidates)} potential fix patterns\n")

    saved = 0
    for c in candidates:
        if auto and c["confidence"] >= 0.6:
            save_lesson(
                title=c["title"], problem=c["problem"],
                cause=c["cause"] or "Not explicitly stated",
                solution=c["solution"] or "See evidence",
                evidence=c["evidence"], language=c["language"],
                framework=c["framework"], tags=c["tags"],
                source="opencode-mine",
            )
            saved += 1
            print(f"  ✅ Saved: {c['title'][:60]}")
        elif dry_run:
            print(f"  📄 Candidate (confidence: {c['confidence']})")
            print(f"     Title:   {c['title'][:60]}")
            print(f"     Problem: {c['problem'][:80]}")
            print(f"     Cause:   {c['cause'][:80] or '(not found)'}")
            print(f"     Solution: {c['solution'][:80] or '(not found)'}")
            print(f"     Lang: {c['language'] or '?'}  FW: {c['framework'] or '?'}")
            print()

    print(f"\n📊 Results:")
    print(f"   Sessions scanned: {len(sessions)}")
    print(f"   Candidates:       {len(candidates)}")
    print(f"   Saved:            {saved}")

    return {"found": len(candidates), "saved": saved, "scanned": len(sessions)}


def main():
    parser = argparse.ArgumentParser(
        prog="opencode-mine",
        description="Mine OpenCode session history for bug-fix lessons",
    )

    mine = parser.add_argument_group("mine options")
    mine.add_argument("--days", type=int, default=30, help="Look back N days (default: 30)")
    mine.add_argument("--auto", action="store_true", help="Auto-save (no review)")
    mine.add_argument("--dry-run", action="store_true", help="Preview only, don't save")
    mine.add_argument("--limit", type=int, default=50, help="Max candidates (default: 50)")

    args = parser.parse_args()

    if not OPENCODE_DB.exists():
        print(f"❌ OpenCode DB not found at {OPENCODE_DB}")
        print("   OpenCode may not be installed or has never been used.")
        sys.exit(1)

    mine_opencode(
        days=args.days,
        auto=args.auto,
        dry_run=args.dry_run,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
