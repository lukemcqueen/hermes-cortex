#!/usr/bin/env python3
"""
mycortex-parity.py — golden known-answer parity runner (S-001).

Makes "retrieval parity with gbrain" measurable: a committed golden set
(tests/fixtures/golden-queries.json) with expected top-3 paths per query,
pinned to source SHAs. Two modes:

  baseline — run the golden set against gbrain (while it still runs) and
             record its top-3 per query to gbrain-baseline.json (Phase 0).
  check    — run the golden set against an engine and compute the pass rate.
             Federated gate: 100% of queries must have their primary expected
             path in the engine top-3. Isolated gate: >=90%.

Engines (--engine):
  gbrain   — subprocess `gbrain search <query> --limit <n>` (text output)
  mycortex — subprocess `mycortex search <query> --json` (deployed CLI, S-004/005/006)
  fixture  — read canned results from --fixture-file (tests only)

Exit codes: 0 = gate passed / baseline recorded; 1 = gate failed or error.

Usage:
  mycortex-parity.py --mode baseline
  mycortex-parity.py --mode check --engine gbrain
  mycortex-parity.py --mode check --engine fixture --fixture-file /tmp/results.json
  mycortex-parity.py --mode check --engine mycortex   # live CLI
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GOLDEN = REPO_ROOT / "tests" / "fixtures" / "golden-queries.json"
DEFAULT_BASELINE = REPO_ROOT / "tests" / "fixtures" / "gbrain-baseline.json"

FEDERATED_PASS_REQUIRED = 1.0   # 100% top-3 federated
ISOLATED_PASS_REQUIRED = 0.90   # >=90% isolated


# ── Path normalization ────────────────────────────────────────

def normalize_path(p: str) -> str:
    """Map engine + golden paths to a comparable key.

    gbrain returns relpaths without .md and lowercase (skills/.../skill);
    mycortex will return stored relpaths with .md. Strip ./, strip .md,
    lowercase — both sides collapse to the same key.
    """
    p = p.strip().lower()
    if p.startswith("./"):
        p = p[2:]
    if p.endswith(".md"):
        p = p[:-3]
    return p


def matches(engine_path: str, expected_path: str) -> bool:
    return normalize_path(engine_path) == normalize_path(expected_path)


# ── Engines ───────────────────────────────────────────────────

def run_gbrain(query: str, limit: int = 10) -> list[str]:
    """gbrain search → [relpath, ...] in rank order."""
    proc = subprocess.run(
        ["gbrain", "search", query, "--limit", str(limit)],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gbrain search failed (rc={proc.returncode}): {proc.stderr.strip()}")
    paths: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        # Format: [0.9603] docs/foo -- Title
        if line.startswith("[") and "--" in line:
            rest = line.split("]", 1)[1].strip()
            relpath = rest.split(" --", 1)[0].strip()
            if relpath:
                paths.append(relpath)
    return paths


def run_mycortex(query: str, limit: int = 10, source: str | None = None) -> list[str]:
    """mycortex search → [relpath, ...] in rank order (deployed CLI)."""
    cmd = ["mycortex", "search", query, "--json", "--limit", str(limit)]
    if source:
        cmd += ["--source", source]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(
            f"mycortex search failed (rc={proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
            "\n  → is `mycortex` on PATH? Deployed to ~/.hermes-cortex/scripts (or use --engine gbrain / --engine fixture)."
        )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"mycortex search returned non-JSON: {e}\n{proc.stdout[:500]}")
    return [r.get("relpath", r.get("path", "")) for r in data if isinstance(r, dict)]


def load_fixture(fixture_file: Path) -> dict[str, list[str]]:
    """Fixture results: {query_id or query_text: [relpath, ...]}."""
    with open(fixture_file) as f:
        data = json.load(f)
    return data


# ── Core ──────────────────────────────────────────────────────

def load_golden(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def top3(paths: list[str]) -> list[str]:
    return paths[:3]


def evaluate_query(expected: dict, actual: list[str]) -> dict:
    """Pass = primary expected path (expected_top3[0]) in engine top-3."""
    expected_paths = expected.get("expected_top3", [])
    primary = expected_paths[0] if expected_paths else None
    top = top3(actual)
    passed = bool(primary and any(matches(ap, primary) for ap in top))
    return {
        "id": expected.get("id", "?"),
        "query": expected.get("query", ""),
        "scope": expected.get("scope", "federated"),
        "passed": passed,
        "expected": expected_paths,
        "actual_top3": top,
    }


def compute_pass_rate(results: list[dict]) -> dict:
    fed = [r for r in results if r["scope"] == "federated"]
    iso = [r for r in results if r["scope"] == "isolated"]
    fed_rate = (sum(r["passed"] for r in fed) / len(fed)) if fed else 1.0
    iso_rate = (sum(r["passed"] for r in iso) / len(iso)) if iso else 1.0
    return {"federated": fed_rate, "isolated": iso_rate}


def gate_passed(rates: dict) -> bool:
    return (
        rates["federated"] >= FEDERATED_PASS_REQUIRED - 1e-9
        and rates["isolated"] >= ISOLATED_PASS_REQUIRED - 1e-9
    )


def print_failures(results: list[dict]) -> None:
    failed = [r for r in results if not r["passed"]]
    if not failed:
        return
    print("\n❌ FAILED QUERIES:")
    for r in failed:
        print(f"  [{r['id']}] scope={r['scope']} query=\"{r['query']}\"")
        print(f"      expected: {r['expected']}")
        print(f"      actual  : {r['actual_top3']}")


# ── Modes ─────────────────────────────────────────────────────

def mode_baseline(args) -> int:
    golden = load_golden(args.golden)
    results = {}
    queries = golden.get("queries", [])
    print(f"Capturing gbrain baseline for {len(queries)} queries …")
    for i, q in enumerate(queries, 1):
        qid = q.get("id", f"q{i}")
        try:
            paths = run_gbrain(q["query"])
        except RuntimeError as e:
            print(f"  ❌ [{qid}] {e}", file=sys.stderr)
            return 1
        results[qid] = {
            "query": q["query"],
            "source": q.get("source"),
            "top3": top3(paths),
            "top10": paths,
        }
        print(f"  [{i}/{len(queries)}] {qid}: {results[qid]['top3']}")
    baseline = {
        "version": 1,
        "engine": "gbrain",
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sources": golden.get("sources", {}),
        "results": results,
    }
    args.baseline_out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.baseline_out, "w") as f:
        json.dump(baseline, f, indent=2)
    print(f"\n✅ baseline written: {args.baseline_out}")
    return 0


def mode_check(args) -> int:
    golden = load_golden(args.golden)
    queries = golden.get("queries", [])
    results: list[dict] = []
    for i, q in enumerate(queries, 1):
        qid = q.get("id", f"q{i}")
        try:
            if args.engine == "gbrain":
                paths = run_gbrain(q["query"])
            elif args.engine == "mycortex":
                src = q.get("source") if q.get("scope") == "isolated" else None
                paths = run_mycortex(q["query"], source=src)
            elif args.engine == "fixture":
                fixture = load_fixture(args.fixture_file)
                paths = fixture.get(qid, fixture.get(q["query"], []))
            else:
                raise RuntimeError(f"unknown engine: {args.engine}")
        except RuntimeError as e:
            print(f"  ❌ [{qid}] {e}", file=sys.stderr)
            return 1
        results.append(evaluate_query(q, paths))
        print(f"  [{i}/{len(queries)}] {qid}: {'PASS' if results[-1]['passed'] else 'FAIL'} → {top3(paths)}")

    rates = compute_pass_rate(results)
    print(f"\nPass rates: federated={rates['federated']:.0%} (need {FEDERATED_PASS_REQUIRED:.0%})  "
          f"isolated={rates['isolated']:.0%} (need {ISOLATED_PASS_REQUIRED:.0%})")
    print_failures(results)

    passed = gate_passed(rates)
    print(f"\n{'✅ GATE PASSED' if passed else '❌ GATE FAILED'}")
    return 0 if passed else 1


# ── CLI ───────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["baseline", "check"], default="check")
    parser.add_argument("--engine", choices=["gbrain", "mycortex", "fixture"],
                        help="search engine for check mode (default: mycortex)")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--baseline-out", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--fixture-file", type=Path, help="fixture engine results JSON")
    args = parser.parse_args()

    if args.mode == "baseline":
        return mode_baseline(args)
    # check mode
    if args.engine is None:
        args.engine = "mycortex"
    if args.engine == "fixture" and not args.fixture_file:
        print("ERROR: --engine fixture requires --fixture-file", file=sys.stderr)
        return 1
    return mode_check(args)


if __name__ == "__main__":
    sys.exit(main())
