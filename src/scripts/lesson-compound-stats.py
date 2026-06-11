#!/usr/bin/env python3
"""Lesson Compound Stats — reports the compounding value of the lesson database.

Usage:
  python3 ~/.hermes/scripts/lesson-compound-stats.py          # full report
  python3 ~/.hermes/scripts/lesson-compound-stats.py --brief  # one-liner for cron
  python3 ~/.hermes/scripts/lesson-compound-stats.py --json   # machine-readable

Outputs the growth, usage, and estimated time saved from the lesson system.
"""

import glob
import json
import os
import sys
from datetime import datetime, timezone


def parse_lesson_metadata(filepath: str) -> dict:
    """Parse YAML frontmatter from a lesson markdown file."""
    meta = {
        "title": "",
        "language": "",
        "framework": "",
        "tags": [],
        "success_count": 0,
        "created": "",
        "updated": "",
    }
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except (IOError, UnicodeDecodeError):
        return meta

    # Extract YAML frontmatter (between --- delimiters)
    if not content.startswith("---"):
        return meta
    end_idx = content.find("---", 3)
    if end_idx == -1:
        return meta
    yaml_block = content[3:end_idx]

    for line in yaml_block.strip().split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip().lower()
        val = val.strip().strip('"').strip("'")

        if key == "title":
            meta["title"] = val
        elif key == "language":
            meta["language"] = val
        elif key == "framework":
            meta["framework"] = val
        elif key == "tags":
            meta["tags"] = [t.strip() for t in val.split() if t.strip()]
        elif key == "success_count":
            try:
                meta["success_count"] = int(val)
            except ValueError:
                meta["success_count"] = 0
        elif key == "created":
            meta["created"] = val
        elif key in ("updated", "modified"):
            meta["updated"] = val

    return meta


def scan_lessons(lessons_dir: str) -> list[dict]:
    """Scan all lesson markdown files and return metadata."""
    pattern = os.path.join(lessons_dir, "*.md")
    lessons = []
    for filepath in sorted(glob.glob(pattern)):
        meta = parse_lesson_metadata(filepath)
        if meta["title"]:
            meta["filepath"] = filepath
            lessons.append(meta)
    return lessons


def compute_stats(lessons: list[dict]) -> dict:
    """Compute compound statistics from lesson metadata."""
    total = len(lessons)
    total_applications = sum(l["success_count"] for l in lessons)
    est_minutes_saved = total_applications * 15  # 15 min avg per saved fix
    est_hours_saved = round(est_minutes_saved / 60, 1)

    # Language coverage
    languages = {}
    for l in lessons:
        lang = l["language"] or "unknown"
        languages[lang] = languages.get(lang, 0) + 1

    # Framework coverage
    frameworks = {}
    for l in lessons:
        fw = l["framework"] or "none"
        frameworks[fw] = frameworks.get(fw, 0) + 1

    # Tag cloud
    tag_counts = {}
    for l in lessons:
        for tag in l["tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # Top tags (sorted by count)
    top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:20]

    # Most applied lessons
    most_applied = sorted(lessons, key=lambda x: -x["success_count"])[:10]

    # Recent lessons
    recent = sorted(lessons, key=lambda x: x.get("updated", "") or x.get("created", ""), reverse=True)[:10]

    return {
        "total_lessons": total,
        "total_applications": total_applications,
        "estimated_minutes_saved": est_minutes_saved,
        "estimated_hours_saved": est_hours_saved,
        "languages": {
            "count": len(languages),
            "breakdown": dict(sorted(languages.items(), key=lambda x: -x[1])),
        },
        "frameworks": {
            "count": len(frameworks),
            "breakdown": dict(sorted(frameworks.items(), key=lambda x: -x[1])[:10]),
        },
        "top_tags": dict(top_tags),
        "most_applied": [
            {"title": l["title"], "count": l["success_count"], "language": l["language"]}
            for l in most_applied
        ],
        "recent_lessons": [
            {"title": l["title"], "language": l["language"], "updated": l.get("updated", l.get("created", ""))}
            for l in recent
        ],
    }


def main():
    lessons_dir = os.path.expanduser("~/brain/lessons")
    if not os.path.isdir(lessons_dir):
        print("❌ Lessons directory not found: ~/brain/lessons")
        sys.exit(1)

    lessons = scan_lessons(lessons_dir)
    stats = compute_stats(lessons)

    # ── Output modes ──────────────────────────────────────────────────
    if "--json" in sys.argv:
        print(json.dumps(stats, indent=2))
        return

    if "--brief" in sys.argv:
        print(
            f"📊 {stats['total_lessons']} lessons · "
            f"{stats['total_applications']} applications · "
            f"~{stats['estimated_hours_saved']}h saved · "
            f"{stats['languages']['count']} languages"
        )
        return

    # ── Full report ────────────────────────────────────────────────────
    print("╔══════════════════════════════════════════════╗")
    print("║     📚 Lesson Compound Score                ║")
    print("╚══════════════════════════════════════════════╝")
    print()
    print(f"  Total lessons:     {stats['total_lessons']}")
    print(f"  Times applied:     {stats['total_applications']}")
    print(f"  Est. time saved:   ~{stats['estimated_hours_saved']} hours")
    print(f"  Languages:         {stats['languages']['count']}")
    print(f"  Frameworks:        {stats['frameworks']['count']}")
    print()

    print("── Languages ──")
    for lang, count in list(stats["languages"]["breakdown"].items())[:10]:
        bar = "█" * min(count, 20)
        print(f"  {lang:12s} {bar} {count}")
    print()

    print("── Top Tags ──")
    for tag, count in stats["top_tags"][:10]:
        print(f"  #{tag:20s}  {count}")
    print()

    print("── Most Applied Lessons ──")
    for l in stats["most_applied"][:5]:
        print(f"  {l['count']:3d}x  {l['title'][:55]}")
    print()

    print("── Recent Lessons ──")
    for l in stats["recent_lessons"][:5]:
        updated = l["updated"][:10] if l["updated"] else "new"
        print(f"  {updated}  {l['language']:8s} {l['title'][:55]}")

    print()
    print(f"  💡 Every lesson compounds. "
          f"At ~{stats['estimated_hours_saved']}h saved, "
          f"the system has already paid for itself.")


if __name__ == "__main__":
    main()
