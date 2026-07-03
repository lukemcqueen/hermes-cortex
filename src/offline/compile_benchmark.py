#!/usr/bin/env python3
"""Compile Qwen3:4b benchmark results into a clean summary."""
import json
from pathlib import Path

# Best representative runs per scenario
results = []

# ── Scenario 1: Docker port (best run with path fix, lessons working) ──
s1_no = {"scenario": 1, "name": "Docker port already allocated",
         "lessons": False, "lesson_count": 0, "keyword": 0.25,
         "rc": True, "fix": True, "time_s": 119,
         "keywords": ["docker compose down"]}

s1_with = {"scenario": 1, "name": "Docker port already allocated",
           "lessons": True, "lesson_count": 5, "keyword": 0.00,
           "rc": True, "fix": True, "time_s": 146,
           "keywords": []}

# ── Scenario 2: SQLite locked (path was wrong, no lessons injected) ──
s2_no = {"scenario": 2, "name": "SQLite database is locked",
         "lessons": False, "lesson_count": 0, "keyword": 0.20,
         "rc": True, "fix": True, "time_s": 83,
         "keywords": ["connection pool"]}

s2_with = {"scenario": 2, "name": "SQLite database is locked",
           "lessons": True, "lesson_count": 0, "keyword": 0.20,
           "rc": True, "fix": False, "time_s": 172,
           "keywords": ["connection pool"]}

# ── Scenario 3: FastAPI 422 (path was wrong, no lessons injected) ──
s3_no = {"scenario": 3, "name": "FastAPI 422 with alias_generator",
         "lessons": False, "lesson_count": 0, "keyword": 0.33,
         "rc": True, "fix": False, "time_s": 130,
         "keywords": ["alias"]}

s3_with = {"scenario": 3, "name": "FastAPI 422 with alias_generator",
           "lessons": True, "lesson_count": 0, "keyword": 0.67,
           "rc": False, "fix": False, "time_s": 164,
           "keywords": ["ConfigDict", "alias"]}

all_results = [s1_no, s1_with, s2_no, s2_with, s3_no, s3_with]

# Summary
for lessons_label in [False, True]:
    runs = [r for r in all_results if r["lessons"] == lessons_label]
    avg_key = sum(r["keyword"] for r in runs) / len(runs)
    avg_time = sum(r["time_s"] for r in runs) / len(runs)
    has_rc = sum(1 for r in runs if r["rc"])
    has_fix = sum(1 for r in runs if r["fix"])
    print(f"{'WITH' if lessons_label else 'WITHOUT'} lessons:")
    print(f"  Keyword score: {avg_key:.2f}")
    print(f"  Avg time:      {avg_time:.0f}s")
    print(f"  Root cause:    {has_rc}/3")
    print(f"  Has fix:       {has_fix}/3")
    print()

# Save
report = {
    "model": "qwen3:4b",
    "machine": "Titus (macOS, CPU, ~35 tok/s)",
    "env": "Ollama local, no GPU",
    "scoring": "keyword match / expected total",
    "expected_keywords": {
        "S1 Docker": ["docker compose down", "docker rm", "force release", "docker compose up -d"],
        "S2 SQLite": ["WAL", "journal_mode", "PRAGMA", "timeout", "connection pool"],
        "S3 FastAPI": ["populate_by_name", "ConfigDict", "alias"],
    },
    "baseline_qwen25coder_15b": {
        "no_lessons": 0.18,
        "with_lessons": 0.75,
    },
    "results": all_results,
    "notes": [
        "Qwen3:4b is a thinking model — puts chain-of-thought in `thinking` field, only final answer in `response`.",
        "Each query needs 4000-8000 thinking tokens before producing a response → 80-170s per query on CPU.",
        "Lesson DB search path was wrong in first runs (used wrong project root directory).",
        "Only S1_with_lessons actually had lesson content injected into the prompt (S1_best run, 5 lessons found).",
        "S2/S3 with_lessons had 0 lesson count (path bug) — those results are equivalent to no-lessons mode.",
        "Temperature 0.1 introduces score noise (0.0-0.25 variation seen across S1 runs).",
    ],
}

report_path = Path.home() / "offline" / "model-benchmark-qwen3-4b-compiled.json"
report_path.write_text(json.dumps(report, indent=2))
print(f"\nReport saved: {report_path}")
print(f"Size: {report_path.stat().st_size / 1024:.0f} KB")
