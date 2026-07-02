#!/usr/bin/env python3
"""
Hermes Cortex — Lesson Database
─────────────────────────────────
A personal bug-fix memory that grows with every session.
Each lesson captures: error → root cause → fix → tags.
Queried by semantic similarity before the model attempts to debug.

Storage: Markdown files in ~/brain/lessons/ (gbrain-indexed for persistence)
Index:   ~/offline/lessons-index.json (embedding index for instant semantic search)

Usage (via offline_knowledge):
  offline_knowledge lesson create [--interactive]
  offline_knowledge lesson search "error message"
  offline_knowledge lesson list [--language python] [--tag fastapi]
  offline_knowledge lesson stats
"""

import argparse
import json
import os
import re
import subprocess
import sys
import json, os, re, sys, textwrap, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

from hermes_paths import ensure_scripts_path
ensure_scripts_path()
from hermes_models import get_model
from typing import Optional

# ── Config ──────────────────────────────────────────────────
HOME = Path.home()
LESSONS_DIR = HOME / "brain" / "lessons"
INDEX_FILE = HOME / "offline" / "lessons-index.json"

# Embedding config (same as offline_code)
EMBED_MODEL = get_model("EMBEDDING_MODEL", "nomic-embed-text")
SIMILARITY_THRESHOLD = 0.55  # broader match for natural language bug descriptions


# ── Helpers ──────────────────────────────────────────────────

def _ensure_dir():
    """Create lessons directory if it doesn't exist."""
    LESSONS_DIR.mkdir(parents=True, exist_ok=True)


def _slugify(title: str) -> str:
    """Convert a title to a URL-safe filename slug."""
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug[:80]


def _now() -> str:
    """ISO 8601 timestamp."""
    return datetime.now(timezone.utc).isoformat()


OLLAMA_URL = "http://localhost:11434"


def _embed_text(text: str) -> Optional[list]:
    """Embed text via Ollama API. Returns vector or None."""
    import urllib.request
    try:
        body = json.dumps({"model": EMBED_MODEL, "input": text}).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/embed",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            embeddings = data.get("embeddings", [])
            return embeddings[0] if embeddings else None
    except Exception:
        return None


def _cosine_similarity(a: list, b: list) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Lesson CRUD ──────────────────────────────────────────────

def _parse_lesson(path: Path) -> Optional[dict]:
    """Parse a markdown lesson file into a structured dict."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None

    # Parse YAML frontmatter
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', text, re.DOTALL)
    if not m:
        return None

    frontmatter = m.group(1)
    body = m.group(2).strip()

    # Parse frontmatter into dict (simple line-by-line)
    meta = {}
    current_key = None
    current_list = None
    for line in frontmatter.split('\n'):
        # List items
        if line.startswith('- ') and current_key:
            if current_list is not None:
                current_list.append(line[2:].strip())
            continue
        # Key: value
        kv = re.match(r'^(\w+):\s*(.*)', line)
        if kv:
            current_key = kv.group(1)
            val = kv.group(2).strip()
            # Remove quotes
            val = re.sub(r'^["\'](.*)["\']$', r'\1', val)
            if val.startswith('['):
                # Parse inline list like [tag1, tag2]
                current_list = [t.strip().strip('"\'') for t in val.strip('[]').split(',') if t.strip()]
                meta[current_key] = current_list
            elif val.lower() == 'true':
                meta[current_key] = True
            elif val.lower() == 'false':
                meta[current_key] = False
            elif val.isdigit():
                meta[current_key] = int(val)
            else:
                meta[current_key] = val

    return {
        "path": str(path),
        "filename": path.name,
        "title": meta.get("title", path.stem),
        "created": meta.get("created", ""),
        "updated": meta.get("updated", ""),
        "language": meta.get("language", ""),
        "framework": meta.get("framework", ""),
        "tags": meta.get("tags", []),
        "project": meta.get("project", ""),
        "success_count": meta.get("success_count", 1),
        "source": meta.get("source", ""),
        "body": body,
        "full_text": text,
    }


def _build_search_text(lesson: dict) -> str:
    """Build the text that gets embedded for search. Includes title, tags, and full body."""
    parts = [
        lesson.get("title", ""),
    ]
    language = lesson.get("language", "")
    framework = lesson.get("framework", "")
    if language or framework:
        parts.append(f"{language} {framework}")
    tags = lesson.get("tags", [])
    if tags:
        parts.append(" ".join(tags))
    # Include the full body (problem + root cause + solution + evidence)
    body = lesson.get("body", "")
    # Strip markdown formatting for cleaner embedding
    clean = re.sub(r'[#*`>]', '', body)
    clean = re.sub(r'\n{3,}', '\n\n', clean)
    parts.append(clean)
    return "\n".join(p for p in parts if p)


def get_all_lessons() -> list:
    """Load all lesson files from disk."""
    _ensure_dir()
    lessons = []
    for f in sorted(LESSONS_DIR.glob("*.md")):
        lesson = _parse_lesson(f)
        if lesson:
            lessons.append(lesson)
    return lessons


def rebuild_index():
    """Rebuild the embedding index for all lessons."""
    lessons = get_all_lessons()
    if not lessons:
        # Write empty index
        _write_index([])
        return {"count": 0, "status": "empty"}

    entries = []
    for i, lesson in enumerate(lessons):
        search_text = _build_search_text(lesson)
        embedding = _embed_text(search_text)
        if embedding:
            entries.append({
                "id": i,
                "path": lesson["path"],
                "filename": lesson["filename"],
                "title": lesson["title"],
                "language": lesson["language"],
                "framework": lesson["framework"],
                "tags": lesson["tags"],
                "project": lesson["project"],
                "embedding": embedding,
            })
        print(f"  [{i+1}/{len(lessons)}] {lesson['title'][:60]}", file=sys.stderr)

    _write_index(entries)
    return {"count": len(entries), "total_lessons": len(lessons), "status": "ok"}


def _write_index(entries: list):
    """Write the index file."""
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "count": len(entries),
        "dim": len(entries[0]["embedding"]) if entries else 0,
        "model": EMBED_MODEL,
        "entries": entries,
    }
    INDEX_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _load_index() -> dict:
    """Load the index file."""
    if not INDEX_FILE.exists():
        return {"count": 0, "entries": []}
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception):
        return {"count": 0, "entries": []}


def search_lessons(query: str, limit: int = 5, language: str = None, tag: str = None) -> dict:
    """Semantic search across all lessons."""
    # Embed the query
    query_embed = _embed_text(query)
    if not query_embed:
        return {"status": "error", "message": "Failed to embed query (Ollama running?)", "results": []}

    index = _load_index()
    if index["count"] == 0:
        return {"status": "empty", "message": "No lessons indexed. Run: offline_knowledge lesson index", "results": []}

    dim = index.get("dim", 0)
    if len(query_embed) != dim:
        return {"status": "error", "message": f"Embedding dimension mismatch (query={len(query_embed)}, index={dim})", "results": []}

    # Score all entries
    scored = []
    for entry in index["entries"]:
        # Apply filters
        if language and entry.get("language", "").lower() != language.lower():
            continue
        if tag:
            entry_tags = [t.lower() for t in entry.get("tags", [])]
            if tag.lower() not in entry_tags:
                continue

        sim = _cosine_similarity(query_embed, entry["embedding"])
        if sim >= SIMILARITY_THRESHOLD:
            scored.append((sim, entry))

    scored.sort(key=lambda x: -x[0])

    # Load full lesson bodies for results
    results = []
    for sim, entry in scored[:limit]:
        lesson = _parse_lesson(Path(entry["path"]))
        if lesson:
            results.append({
                "title": entry["title"],
                "language": entry.get("language", ""),
                "framework": entry.get("framework", ""),
                "tags": entry.get("tags", []),
                "project": entry.get("project", ""),
                "similarity": round(sim, 4),
                "body": lesson["body"],
            })

    return {
        "status": "ok",
        "query": query,
        "count": len(results),
        "total_scored": len(scored),
        "results": results,
    }


def create_lesson(title: str, problem: str, root_cause: str, solution: str,
                  evidence: str = "", language: str = "", framework: str = "",
                  tags: list = None, project: str = "", source: str = "agent",
                  interactive: bool = False) -> dict:
    """Create a new lesson file."""
    _ensure_dir()

    if not title:
        return {"status": "error", "message": "Title is required"}

    if interactive:
        return {"status": "error", "message": "Interactive mode not implemented for CLI. Use args."}

    timestamp = _now()
    slug = _slugify(title)
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_prefix}_{slug}.md"
    filepath = LESSONS_DIR / filename

    tags_str = ", ".join(tags) if tags else ""

    # Build lesson content
    content = f"""---
title: "{title}"
created: "{timestamp}"
updated: "{timestamp}"
language: {language}
framework: {framework}
tags: [{tags_str}]
project: {project}
success_count: 1
source: {source}
---

## Problem

{problem}

## Root Cause

{root_cause}

## Solution

{solution}

## Evidence

{evidence}
"""

    filepath.write_text(content.strip() + "\n", encoding="utf-8")

    return {
        "status": "ok",
        "message": f"Lesson saved: {filepath}",
        "path": str(filepath),
        "filename": filename,
    }


def list_lessons(language: str = None, tag: str = None, project: str = None) -> dict:
    """List all lessons, optionally filtered."""
    lessons = get_all_lessons()
    if not lessons:
        return {"status": "empty", "count": 0, "lessons": []}

    filtered = []
    for lesson in lessons:
        if language and lesson.get("language", "").lower() != language.lower():
            continue
        if tag and tag.lower() not in [t.lower() for t in lesson.get("tags", [])]:
            continue
        if project and lesson.get("project", "").lower() != project.lower():
            continue
        filtered.append(lesson)

    return {
        "status": "ok",
        "count": len(filtered),
        "total": len(lessons),
        "lessons": filtered,
    }


def get_stats() -> dict:
    """Get statistics about the lesson database."""
    lessons = get_all_lessons()
    if not lessons:
        return {"total": 0, "total_successes": 0, "languages": {}, "frameworks": {}, "tags": {}, "projects": {}}

    languages = {}
    frameworks = {}
    tags = {}
    projects = {}
    total_successes = 0

    for lesson in lessons:
        lang = lesson.get("language", "unknown") or "unknown"
        languages[lang] = languages.get(lang, 0) + 1

        fw = lesson.get("framework", "unknown") or "unknown"
        frameworks[fw] = frameworks.get(fw, 0) + 1

        for t in lesson.get("tags", []):
            t = t.strip()
            if t:
                tags[t] = tags.get(t, 0) + 1

        proj = lesson.get("project", "unknown") or "unknown"
        projects[proj] = projects.get(proj, 0) + 1

        total_successes += lesson.get("success_count", 1)

    return {
        "total": len(lessons),
        "total_successes": total_successes,
        "languages": dict(sorted(languages.items(), key=lambda x: -x[1])),
        "frameworks": dict(sorted(frameworks.items(), key=lambda x: -x[1])),
        "tags": dict(sorted(tags.items(), key=lambda x: -x[1])),
        "projects": dict(sorted(projects.items(), key=lambda x: -x[1])),
    }


# ── CLI ──────────────────────────────────────────────────────

def main(args: Optional[list] = None):
    """Entry point for offline_knowledge lesson subcommand."""
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(prog="offline_knowledge lesson",
        description="Personal bug-fix lesson database. Offline, semantic-searchable, auto-indexed by gbrain.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="lesson_command")

    # lesson create
    create_p = sub.add_parser("create", help="Create a new lesson")
    create_p.add_argument("--title", "-t", help="Lesson title (descriptive, e.g. 'FastAPI 422 on Pydantic alias model')")
    create_p.add_argument("--problem", "-p", help="What went wrong")
    create_p.add_argument("--cause", "-c", help="Root cause")
    create_p.add_argument("--solution", "-s", help="How it was fixed (mandatory)")
    create_p.add_argument("--evidence", "-e", help="Supporting details (optional)")
    create_p.add_argument("--language", "-l", help="Programming language")
    create_p.add_argument("--framework", "-f", help="Framework (fastapi, react, etc.)")
    create_p.add_argument("--tags", nargs="+", help="Tags for filtering (e.g. pydantic validation error-handling)")
    create_p.add_argument("--project", help="Project name")
    create_p.add_argument("--interactive", action="store_true", help="Interactive prompt (if no args provided)")

    # lesson search
    search_p = sub.add_parser("search", help="Semantic search across lessons")
    search_p.add_argument("query", nargs="+", help="Search query (error message, problem description)")
    search_p.add_argument("--limit", type=int, default=5, help="Max results (default: 5)")
    search_p.add_argument("--language", help="Filter by language")
    search_p.add_argument("--tag", help="Filter by tag")

    # lesson list
    list_p = sub.add_parser("list", help="List all lessons")
    list_p.add_argument("--language", help="Filter by language")
    list_p.add_argument("--tag", help="Filter by tag")
    list_p.add_argument("--project", help="Filter by project")

    # lesson index
    sub.add_parser("index", help="Rebuild the embedding index")

    # lesson stats
    sub.add_parser("stats", help="Lesson database statistics")

    parsed = parser.parse_args(args)

    if parsed.lesson_command == "create":
        if parsed.interactive or not parsed.title:
            # Interactive mode (inputs via stdin prompt)
            print("📝 Creating a new lesson (press Ctrl+D to finish multi-line inputs)")
            title = parsed.title or input("Title: ").strip()
            problem = parsed.problem or input("Problem (what went wrong):\n").strip()
            cause = parsed.cause or input("Root cause:\n").strip()
            solution = parsed.solution or input("Solution (how it was fixed):\n").strip()
            evidence = parsed.evidence or input("Evidence / details (optional):\n").strip()
            language = parsed.language or input("Language (optional): ").strip()
            framework = parsed.framework or input("Framework (optional): ").strip()
            tags_input = parsed.tags
            if not tags_input:
                tags_raw = input("Tags (space-separated, optional): ").strip()
                tags_input = tags_raw.split() if tags_raw else []
            project = parsed.project or input("Project (optional): ").strip()
        else:
            title = parsed.title
            problem = parsed.problem or ""
            cause = parsed.cause or ""
            solution = parsed.solution or ""
            evidence = parsed.evidence or ""
            language = parsed.language or ""
            framework = parsed.framework or ""
            tags_input = parsed.tags or []
            project = parsed.project or ""

        result = create_lesson(
            title=title,
            problem=problem,
            root_cause=cause,
            solution=solution,
            evidence=evidence,
            language=language,
            framework=framework,
            tags=tags_input,
            project=project,
            source="agent",
        )
        print(result["message"])
        if result["status"] == "error":
            sys.exit(1)

    elif parsed.lesson_command == "search":
        query = " ".join(parsed.query)
        result = search_lessons(query, limit=parsed.limit,
                                language=parsed.language, tag=parsed.tag)

        if result["status"] == "error":
            print(f"❌ {result['message']}")
            sys.exit(1)
        elif result["status"] == "empty":
            print(f"📭 {result['message']}")
            return

        print(f"\n🔍 Lesson Search: \"{result['query']}\"")
        print(f"   {result['count']} matches (threshold: {SIMILARITY_THRESHOLD})\n")
        if result["count"] == 0:
            index_path = Path(HOME / "offline" / "lessons-index.json")
            has_lessons = index_path.exists() and _load_index().get("count", 0) > 0
            if has_lessons:
                print("   💡 Try broader terms or use --language/--tag to filter.")
                print()
        for r in result["results"]:
            tags_str = ", ".join(r["tags"]) if r["tags"] else ""
            print(f"  📖 {r['title']}")
            print(f"     Lang: {r['language']:12s}  Framework: {r['framework']:12s}  Similarity: {r['similarity']:.2f}")
            if tags_str:
                print(f"     Tags: {tags_str}")
            # Show first 3 lines of the problem/solution
            body_parts = r["body"].split("\n\n")
            snippet = body_parts[0] if body_parts else r["body"]
            # Clean markdown from snippet
            snippet = re.sub(r'[#*`>]', '', snippet).strip()
            print(f"     → {snippet[:150]}")
            print()

    elif parsed.lesson_command == "list":
        result = list_lessons(language=parsed.language, tag=parsed.tag, project=parsed.project)
        if result["status"] == "empty":
            print("📭 No lessons yet. Create one with: offline_knowledge lesson create")
            return

        filters = []
        if parsed.language:
            filters.append(f"language={parsed.language}")
        if parsed.tag:
            filters.append(f"tag={parsed.tag}")
        if parsed.project:
            filters.append(f"project={parsed.project}")
        filter_str = f" ({', '.join(filters)})" if filters else ""

        print(f"\n📚 Lessons ({result['count']}/{result['total']}){filter_str}\n")
        for lesson in result["lessons"]:
            tags_str = ", ".join(lesson.get("tags", []))
            print(f"  📄 {lesson['title']}")
            info = []
            if lesson.get("language"):
                info.append(lesson["language"])
            if lesson.get("framework"):
                info.append(lesson["framework"])
            if lesson.get("project"):
                info.append(lesson["project"])
            if info:
                print(f"     {' · '.join(info)}")
            if tags_str:
                print(f"     Tags: {tags_str}")
            print(f"     File: {lesson['filename']}")
            print()

    elif parsed.lesson_command == "index":
        print("🔄 Rebuilding lesson index...")
        result = rebuild_index()
        print(f"   {result['count']} lessons indexed ({result.get('total_lessons', result['count'])} total files)")
        INDEX_FILE_SZ = INDEX_FILE.stat().st_size / 1024 if INDEX_FILE.exists() else 0
        print(f"   Index file: {INDEX_FILE} ({INDEX_FILE_SZ:.1f} KB)")

    elif parsed.lesson_command == "stats":
        stats = get_stats()
        print(f"\n📊 Lesson Database Stats")
        print(f"   Total lessons: {stats['total']}")
        print(f"   Total uses:    {stats['total_successes']}")
        if stats["languages"]:
            print(f"\n   Languages:")
            for lang, count in list(stats["languages"].items())[:10]:
                print(f"     {lang:15s} {count}")
        if stats["frameworks"]:
            print(f"\n   Frameworks:")
            for fw, count in list(stats["frameworks"].items())[:10]:
                print(f"     {fw:15s} {count}")
        if stats["tags"]:
            print(f"\n   Top Tags:")
            for tag, count in list(stats["tags"].items())[:10]:
                print(f"     {tag:15s} {count}")
        if stats["total"] == 0:
            print("\n   📭 No lessons yet. Each bug fix is a lesson waiting to be saved!")
        print()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
