#!/usr/bin/env python3
"""
Lesson DB — Model A/B Benchmark
─────────────────────────────────
Tests how well each model uses the lesson DB to resolve errors.

For each (model, with/without lessons) combination:
  1. Present error context
  2. Agent searches lessons (if enabled)
  3. Agent proposes a fix
  4. Score: does the fix match the known solution?

Usage:
  python3 benchmark_models.py             # Full 4-way comparison
  python3 benchmark_models.py --model qwen  # Qwen only
  python3 benchmark_models.py --model deepseek  # DeepSeek only
"""

import argparse
import json
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
LESSONS_DIR = HOME / "brain" / "kustos" / "lessons"
OFFLINE_KNOWLEDGE = HOME / "Developer" / "AI" / "hermes-cortex" / "src" / "offline" / "offline_knowledge.py"

# Ollama API for Qwen models
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3:4b"  # Override with --qwen-model

# ── Test Scenarios ──

SCENARIOS = [
    {
        "id": 1,
        "name": "Docker port already allocated",
        "error_context": (
            'Error response from daemon: driver failed programming external connectivity '
            'on endpoint myapp (abc123): Bind for 0.0.0.0:3000 failed: port is already allocated.\n'
            "This happened after a container crash. Now `docker compose up` won't start."
        ),
        "expected_keywords": ["docker compose down", "docker rm", "force release", "docker compose up -d"],
        "expected_lesson": "docker port",
    },
    {
        "id": 2,
        "name": "SQLite database is locked",
        "error_context": (
            'sqlite3.OperationalError: database is locked\n'
            "Multiple ThreadPoolExecutor workers each open their own SQLite connection "
            "and write to the same database file. Works with 1 worker, fails with 4+."
        ),
        "expected_keywords": ["WAL", "journal_mode", "PRAGMA", "timeout", "connection pool"],
        "expected_lesson": "sqlite",
    },
    {
        "id": 3,
        "name": "FastAPI 422 with alias_generator",
        "error_context": (
            "FastAPI POST /api/users returns 422 Unprocessable Entity.\n"
            "Client sends snake_case fields (user_name, email_address) but Pydantic model "
            "uses alias_generator = to_camel and expects camelCase (userName, emailAddress)."
        ),
        "expected_keywords": ["populate_by_name", "ConfigDict", "alias"],
        "expected_lesson": "fastapi 422",
    },
]


def ask_qwen(prompt: str, timeout: int = 300) -> str:
    """Ask Qwen model via Ollama."""
    body = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 8192},
    }).encode()
    try:
        req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", "")
    except Exception as e:
        return f"[ERROR: {e}]"


def ask_deepseek(prompt: str, timeout: int = 60) -> str:
    """DeepSeek V4 not directly callable from Python (OAuth credential pool).
    Returns a placeholder noting this is the DeepSeek session itself."""
    return "[DeepSeek V4 — running in current session. See session benchmark results.]"


def search_lessons(query: str) -> list:
    """Search lesson DB."""
    try:
        result = subprocess.run(
            ["python3", str(OFFLINE_KNOWLEDGE), "lesson", "search", query, "--limit", "5"],
            capture_output=True, text=True, timeout=30,
        )
        output = result.stdout
        lessons = []
        current = {}
        for line in output.split("\n"):
            m = re.match(r"  📖 (.+)", line)
            if m:
                if current and current.get("title"):
                    lessons.append(current)
                current = {"title": m.group(1).strip()}
            m = re.search(r"Similarity:\s*([\d.]+)", line)
            if m and current:
                current["similarity"] = float(m.group(1))
        if current and current.get("title"):
            lessons.append(current)
        return lessons
    except Exception:
        return []


def score_fix(fix_text: str, expected_keywords: list) -> dict:
    """Score a fix proposal against expected keywords."""
    text = fix_text.lower()
    found = [kw for kw in expected_keywords if kw.lower() in text]
    return {
        "keywords_found": found,
        "score": round(len(found) / len(expected_keywords), 2),
    }


def run_scenario(scenario: dict, model: str, use_lessons: bool) -> dict:
    """Run a single scenario for one model + lesson setting."""
    print(f"\n  ── Scenario {scenario['id']}: {scenario['name']} ──")
    print(f"     Model: {model}  |  Lessons: {'ON' if use_lessons else 'OFF'}")

    # Build prompt
    lessons = []
    prompt = f"You are debugging this error:\n\n{scenario['error_context']}\n\n"
    if use_lessons:
        # Search for relevant lessons
        t0 = time.time()
        lessons = search_lessons(scenario["name"][:20])
        t1 = time.time()
        search_time = round(t1 - t0, 2)

        if lessons:
            prompt += "Your lesson database has these relevant entries:\n\n"
            for i, l in enumerate(lessons[:3], 1):
                title = l.get("title", "?")
                sim = l.get("similarity", 0)
                # Read the full lesson content
                lesson_file = None
                for f in sorted(LESSONS_DIR.glob("*.md")):
                    if title.lower() in f.read_text().split("\n")[1][:100].lower():
                        lesson_file = f
                        break
                if lesson_file:
                    text = lesson_file.read_text()
                    prob = re.search(r"## Problem\n\n(.+?)(?:\n##|\Z)", text, re.DOTALL)
                    cause = re.search(r"## Root Cause\n\n(.+?)(?:\n##|\Z)", text, re.DOTALL)
                    sol = re.search(r"## Solution\n\n(.+?)(?:\n##|\Z)", text, re.DOTALL)
                    prompt += f"Lesson {i}: {title} (relevance: {sim})\n"
                    if prob: prompt += f"  Problem: {prob.group(1).strip()[:150]}\n"
                    if cause: prompt += f"  Cause:   {cause.group(1).strip()[:150]}\n"
                    if sol: prompt += f"  Solution: {sol.group(1).strip()[:150]}\n"
                    prompt += "\n"

            found_expected = any(
                scenario["expected_lesson"].lower() in l.get("title", "").lower()
                for l in lessons
            )
            print(f"     Lessons found: {len(lessons)}  |  Matched: {found_expected}  |  Search: {search_time}s")
        else:
            found_expected = False
            print(f"     Lessons found: 0  |  Search: {search_time}s")
    else:
        search_time = 0
        found_expected = False
        prompt += "Use your own knowledge to solve it."
        print(f"     No lesson access")

    prompt += "\nProvide the ROOT CAUSE and FIX. Be specific. Start with 'Root Cause:' and 'Fix:'."

    # Ask the model
    ask_fn = ask_qwen if model == "qwen" else ask_deepseek
    t0 = time.time()
    response = ask_fn(prompt)
    t1 = time.time()
    model_time = round(t1 - t0, 1)

    # Score
    quality = score_fix(response, scenario["expected_keywords"])
    has_root_cause = "root cause" in response.lower()
    has_fix = re.search(r"(?:^|\n)fix:?", response, re.IGNORECASE) is not None

    print(f"     Model time: {model_time}s")
    print(f"     Has root cause: {has_root_cause}  |  Has fix: {has_fix}")
    print(f"     Keywords: {quality['keywords_found']}  |  Score: {quality['score']}")
    print(f"     Response preview: {response[:120].strip()}...")

    return {
        "scenario_id": scenario["id"],
        "scenario_name": scenario["name"],
        "model": model,
        "lessons_enabled": use_lessons,
        "lessons_found_count": len(lessons) if use_lessons and 'lessons' in dir() else 0,
        "found_expected_lesson": found_expected if use_lessons else None,
        "search_time": search_time,
        "model_time": model_time,
        "has_root_cause": has_root_cause,
        "has_fix": has_fix,
        "keyword_score": quality["score"],
        "keywords_found": quality["keywords_found"],
        "response": response[:500],
    }


def main():
    parser = argparse.ArgumentParser(description="Lesson DB model A/B benchmark")
    parser.add_argument("--model", choices=["deepseek", "qwen", "all"], default="all")
    parser.add_argument("--qwen-model", default="qwen3:4b", help="Ollama model name for Qwen (default: qwen3:4b)")
    parser.add_argument("--no-lessons", action="store_true", help="Skip with-lessons runs")
    parser.add_argument("--scenario", type=int, help="Single scenario ID")
    parser.add_argument("--json", action="store_true", help="JSON output only")
    args = parser.parse_args()

    # Override Qwen model
    if args.qwen_model != "qwen3:4b":
        global OLLAMA_MODEL
        OLLAMA_MODEL = args.qwen_model

    models = ["deepseek", "qwen"] if args.model == "all" else [args.model]
    lesson_modes = [False] if args.no_lessons else [False, True]

    scenarios = SCENARIOS
    if args.scenario:
        scenarios = [s for s in scenarios if s["id"] == args.scenario]

    print(f"📍 Model A/B Benchmark — Lesson DB")
    print(f"   Models: {', '.join(models)}")
    print(f"   Scenarios: {len(scenarios)}")
    print(f"   Lessons: {', '.join('ON' if l else 'OFF' for l in lesson_modes)}")
    print()

    all_results = []
    for model in models:
        for use_lessons in lesson_modes:
            tag = f"{model}-{'with' if use_lessons else 'no'}-lessons"
            print(f"\n{'='*60}")
            print(f"  {tag.upper()}")
            print(f"{'='*60}")

            for s in scenarios:
                r = run_scenario(s, model, use_lessons)
                all_results.append(r)
                print()

    # Summary scores
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")

    for model in models:
        for use_lessons in lesson_modes:
            tag = f"{model}-{'with' if use_lessons else 'no'}-lessons"
            runs = [r for r in all_results if r["model"] == model and r["lessons_enabled"] == use_lessons]
            if not runs:
                continue
            avg_keyword = sum(r["keyword_score"] for r in runs) / len(runs)
            avg_time = sum(r["model_time"] for r in runs) / len(runs)
            has_cause = sum(1 for r in runs if r["has_root_cause"])
            has_fix = sum(1 for r in runs if r["has_fix"])
            print(f"\n  {tag}:")
            print(f"    Keyword score:  {avg_keyword:.2f}")
            print(f"    Avg time:      {avg_time:.1f}s")
            print(f"    Root cause:    {has_cause}/{len(runs)}")
            print(f"    Has fix:       {has_fix}/{len(runs)}")

    # Save report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {"models": models, "lesson_modes": lesson_modes},
        "results": all_results,
    }
    report_dir = HOME / "offline"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"model-benchmark-{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\n  Report saved: {report_path}")

    if args.json:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
