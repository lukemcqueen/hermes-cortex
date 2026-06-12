#!/usr/bin/env python3
"""
Lesson DB — Retrieval Benchmark
────────────────────────────────
Tests whether the lesson DB helps an agent recover from known errors faster.

For each scenario:
  1. Present the error context (simulated)
  2. Agent searches lessons (if enabled)
  3. Measure: time-to-fix, solution quality, correctness

Usage:
  python3 lesson_benchmark.py                # Full benchmark with lessons
  python3 lesson_benchmark.py --no-lessons    # Benchmark without lesson access
  python3 lesson_benchmark.py --scenario 1    # Single scenario

Returns JSON results for comparison.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
PARENT = Path(__file__).resolve().parent
LESSONS_DIR = HOME / "brain" / "lessons"
OFFLINE_KNOWLEDGE = PARENT / "offline_knowledge.py"
SESSION_MINE = PARENT / "session_mine.py"

# ── Test Scenarios ──────────────────────────────────────────────
# Each scenario: error_context (what the agent sees), expected_lesson_slug, tags

SCENARIOS = [
    {
        "id": 1,
        "name": "Docker port already allocated",
        "error_context": (
            "I ran `docker compose up` after a container crash and got:\n"
            'Error response from daemon: driver failed programming external connectivity '
            'on endpoint myapp (abc123): Bind for 0.0.0.0:3000 failed: port is already allocated\n\n'
            "The container exited with code 137 and now docker compose up won't start."
        ),
        "expected_titles": ["docker port", "port is already allocated"],
        "expected_solution_keywords": ["docker compose down", "docker rm", "force release"],
    },
    {
        "id": 2,
        "name": "SQLite database is locked",
        "error_context": (
            "I'm running a Python script with multiple ThreadPoolExecutor workers "
            "and getting:\n"
            'sqlite3.OperationalError: database is locked\n\n'
            "Each worker opens its own SQLite connection and writes to the same database file. "
            "It works fine with 1 worker but fails with 4+."
        ),
        "expected_titles": ["sqlite", "database is locked"],
        "expected_solution_keywords": ["WAL", "journal_mode", "PRAGMA", "timeout", "connection pool"],
    },
    {
        "id": 3,
        "name": "FastAPI 422 with alias_generator",
        "error_context": (
            "I have a FastAPI endpoint that returns 422 Unprocessable Entity:\n\n"
            'POST /api/users\n'
            '{\n'
            '  "user_name": "john",\n'
            '  "email_address": "john@example.com"\n'
            '}\n\n'
            'Response: 422\n'
            '{"detail": [{"type": "missing", "loc": ["body", "userName"], ...}]}\n\n'
            "My Pydantic model uses alias_generator = to_camel but the client sends snake_case. "
            "The endpoint works if the client sends camelCase."
        ),
        "expected_titles": ["fastapi 422", "pydantic", "alias_generator"],
        "expected_solution_keywords": ["populate_by_name", "ConfigDict", "alias"],
    },
]


def search_lessons(query: str) -> list:
    """Search lesson DB and return results."""
    try:
        result = subprocess.run(
            ["python3", str(OFFLINE_KNOWLEDGE), "lesson", "search", query, "--limit", "5"],
            capture_output=True, text=True, timeout=30,
        )
        output = result.stdout
        # Parse results
        lessons = []
        current = {}
        for line in output.split("\n"):
            m = re.match(r"  📖 (.+)", line)
            if m:
                if current:
                    lessons.append(current)
                current = {"title": m.group(1).strip()}
            m = re.match(r"\s+Similarity:\s*([\d.]+)", line)
            if m and current:
                current["similarity"] = float(m.group(1))
            m = re.match(r"\s+Tags:\s*(.+)", line)
            if m and current:
                current["tags"] = m.group(1).strip()
        if current:
            lessons.append(current)
        return lessons
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def score_solution(agent_solution: str, expected_keywords: list) -> dict:
    """Score how well an agent's solution matches expected keywords."""
    text = agent_solution.lower()
    found = [kw for kw in expected_keywords if kw.lower() in text]
    score = len(found) / len(expected_keywords) if expected_keywords else 0
    return {
        "keywords_found": found,
        "keywords_missed": [kw for kw in expected_keywords if kw.lower() not in text],
        "score": round(score, 2),
    }


def run_scenario(scenario: dict, use_lessons: bool) -> dict:
    """Run a single test scenario and return results."""
    print(f"\n  ── Scenario {scenario['id']}: {scenario['name']} ──")
    print(f"     Lessons enabled: {use_lessons}")

    result = {
        "scenario_id": scenario["id"],
        "scenario_name": scenario["name"],
        "lessons_enabled": use_lessons,
        "lessons_found": [],
        "solution_quality": {},
        "time_taken": 0,
    }

    # Phase 1: Search for relevant lessons
    if use_lessons:
        t0 = time.time()
        # Try multiple search queries to find the right lesson
        queries = [scenario["name"][:30], scenario["expected_titles"][0]]
        all_found = []
        for q in queries:
            results = search_lessons(q)
            for r in results:
                if r not in all_found:
                    all_found.append(r)
        t1 = time.time()
        result["lessons_found"] = all_found
        result["time_taken"] = round(t1 - t0, 2)

        # Check if expected lesson was found
        titles_lower = [r["title"].lower() for r in all_found]
        found_expected = any(
            any(et.lower() in t for et in scenario["expected_titles"])
            for t in titles_lower
        )
        result["found_expected"] = found_expected
        result["best_similarity"] = max(
            (r.get("similarity", 0) for r in all_found),
            default=0,
        )

        print(f"     Search time: {result['time_taken']}s")
        print(f"     Found expected lesson: {found_expected}")
        for r in all_found[:3]:
            sim = r.get("similarity", 0)
            print(f"       → {r['title']} (sim: {sim})")

    # Phase 2: Evaluate solution quality (from the lesson DB itself)
    # Read the actual lesson to evaluate what the lesson DB provides
    for f in sorted(LESSONS_DIR.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        title = ""
        m = re.search(r'title:\s*"(.+)"', text)
        if m:
            title = m.group(1)

        if any(et.lower() in title.lower() for et in scenario["expected_titles"]):
            # Extract solution from lesson
            solution_m = re.search(r"## Solution\n\n(.+?)(?:\n##|\Z)", text, re.DOTALL)
            solution = solution_m.group(1).strip() if solution_m else ""
            quality = score_solution(solution, scenario["expected_solution_keywords"])
            result["solution_quality"] = quality
            print(f"     Solution keywords: {quality['keywords_found']}")
            print(f"     Solution score: {quality['score']}")
            break

    return result


def main():
    parser = argparse.ArgumentParser(description="Lesson DB retrieval benchmark")
    parser.add_argument("--no-lessons", action="store_true", help="Run without lesson DB")
    parser.add_argument("--scenario", type=int, help="Run single scenario by ID")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    use_lessons = not args.no_lessons

    print(f"📍 Lesson DB Benchmark")
    print(f"   Model: current (deepseek-v4-flash)")
    print(f"   Lessons enabled: {use_lessons}")
    print(f"   Lessons in DB: {len(list(LESSONS_DIR.glob('*.md')))}")
    print()

    scenarios = SCENARIOS
    if args.scenario:
        scenarios = [s for s in scenarios if s["id"] == args.scenario]
        if not scenarios:
            print(f"❌ Scenario {args.scenario} not found")
            sys.exit(1)

    results = []
    for s in scenarios:
        r = run_scenario(s, use_lessons)
        results.append(r)
        print()

    # Summary
    if use_lessons:
        found_count = sum(1 for r in results if r.get("found_expected"))
        avg_sim = sum(r.get("best_similarity", 0) for r in results) / len(results) if results else 0
        avg_time = sum(r.get("time_taken", 0) for r in results) / len(results) if results else 0
        avg_score = sum(r.get("solution_quality", {}).get("score", 0) for r in results) / len(results) if results else 0

        print(f"  ── Summary ──")
        print(f"  Scenarios:     {len(results)}")
        print(f"  Retrieved:     {found_count}/{len(results)}")
        print(f"  Avg similarity: {avg_sim:.2f}")
        print(f"  Avg search:    {avg_time:.1f}s")
        print(f"  Avg solution:  {avg_score:.2f}")
    else:
        print(f"  ── Summary (no lessons) ──")
        print(f"  Agent must resolve from scratch. No lesson DB available.")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": "deepseek-v4-flash",
        "lessons_enabled": use_lessons,
        "lesson_count": len(list(LESSONS_DIR.glob("*.md"))),
        "results": results,
    }

    if args.json:
        print(json.dumps(report, indent=2))

    # Save report
    report_dir = HOME / "offline"
    report_dir.mkdir(parents=True, exist_ok=True)
    tag = "with-lessons" if use_lessons else "no-lessons"
    report_path = report_dir / f"lesson-benchmark-{tag}.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\n  Report saved: {report_path}")


if __name__ == "__main__":
    main()
