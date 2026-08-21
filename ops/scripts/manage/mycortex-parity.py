#!/usr/bin/env python3
"""
mycortex-parity.py — golden known-answer parity runner (S-001).

Makes retrieval quality measurable: a committed golden set
(tests/fixtures/golden-queries.json) with expected top-3 paths per query,
pinned to source SHAs. The legacy brain's baseline capture phase is retired
(recorded once 2026-08-01; migration flip done) — the golden set is now a
regression fixture for mycortex itself.

Modes:
  check    — run the golden set against an engine and compute the pass rate.
             Federated gate: 100% of queries must have their primary expected
             path in the engine top-3. Isolated gate: >=90%.

Engines (--engine):
  mycortex — subprocess `mycortex search <query> --json` (deployed CLI, S-004/005/006)
  fixture  — read canned results from --fixture-file (tests only)

Exit codes: 0 = gate passed; 1 = gate failed or error.

Usage:
  mycortex-parity.py --mode check --engine fixture --fixture-file /tmp/results.json
  mycortex-parity.py --mode check --engine mycortex   # live CLI
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Resolve the hermes-cortex repo root from either runtime location:
#   repo:   <root>/ops/scripts/manage/mycortex-parity.py  → parents[3]
#   deploy: ~/.hermes-cortex/scripts/mycortex-parity.py   → parents[2] is the
#           HOME dir (~), NOT the repo — so also probe $HOME/hermes-cortex.
_HERE = Path(__file__).resolve()
_REPO_CANDIDATES = [
    _HERE.parents[3],                                     # repo layout
    Path.home() / "hermes-cortex",                        # deployed layout → repo
    _HERE.parents[2],                                     # deployed layout (legacy comment; harmless)
]
REPO_ROOT = next((p for p in _REPO_CANDIDATES if (p / "tests" / "fixtures").is_dir()), _HERE.parents[3])
DEFAULT_GOLDEN = REPO_ROOT / "tests" / "fixtures" / "golden-queries.json"

FEDERATED_PASS_REQUIRED = 1.0   # 100% top-3 federated
ISOLATED_PASS_REQUIRED = 0.90   # >=90% isolated


# ── Path normalization ────────────────────────────────────────

def normalize_path(p: str) -> str:
    """Map engine + golden paths to a comparable key.

    The legacy brain returned relpaths without .md and lowercase
    (skills/.../skill); mycortex returns stored relpaths with .md. Strip ./,
    strip .md, lowercase — both sides collapse to the same key.
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

def run_mycortex(query: str, limit: int = 10, source: str | None = None) -> list[str]:
    """mycortex search → [relpath, ...] in rank order (deployed CLI)."""
    cmd = ["mycortex", "search", query, "--json", "--limit", str(limit)]
    if source:
        cmd += ["--source", source]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(
            f"mycortex search failed (rc={proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
            "\n  → is `mycortex` on PATH? Deployed to ~/.hermes-cortex/scripts (or use --engine fixture)."
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

def _registered_sources() -> set[str]:
    """Names of sources registered on THIS host (per-host model, design D4).

    The moses source lives on Moses' host; a parity run on Esther must not
    fail isolated queries for sources that exist elsewhere.
    """
    try:
        proc = subprocess.run(
            ["mycortex", "sources", "list", "--json"],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            return {str(s.get("name")) for s in data if isinstance(s, dict) and s.get("name")}
    except Exception:
        pass
    # Fallback: if we can't enumerate, assume all sources exist (old behavior)
    return set()


def mode_check(args) -> int:
    golden = load_golden(args.golden)
    queries = golden.get("queries", [])
    results: list[dict] = []
    registered = _registered_sources() if args.engine == "mycortex" else set()
    skipped = 0
    for i, q in enumerate(queries, 1):
        qid = q.get("id", f"q{i}")
        # Per-host: skip isolated queries whose source isn't registered here.
        if args.engine == "mycortex" and q.get("scope") == "isolated" and registered:
            src = q.get("source")
            if src and src not in registered:
                print(f"  ⏭ [{i}/{len(queries)}] {qid}: source '{src}' not on this host — skipped")
                skipped += 1
                continue
        try:
            if args.engine == "mycortex":
                # Scope EVERY query to its golden-declared source. Federated
                # (HC) queries target the federated source (hermes-cortex);
                # isolated (MO) queries target their source. Passing None for
                # federated queries searched ALL visible sources — including
                # isolated sources with reader grants — so archive/session
                # content from shared/lessons crowded out the correct docs
                # (2026-08-03: HC-005/010/018 failed on noise, not relevance).
                src = q.get("source")
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

    if skipped:
        print(f"  (skipped {skipped} query(s) for sources not on this host)")
    if not results:
        print("  ❌ no applicable queries — nothing to gate", file=sys.stderr)
        return 1
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
    parser.add_argument("--mode", choices=["check"], default="check")
    parser.add_argument("--engine", choices=["mycortex", "fixture"],
                        help="search engine for check mode (default: mycortex)")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--fixture-file", type=Path, help="fixture engine results JSON")
    args = parser.parse_args()

    # check mode
    if args.engine is None:
        args.engine = "mycortex"
    if args.engine == "fixture" and not args.fixture_file:
        print("ERROR: --engine fixture requires --fixture-file", file=sys.stderr)
        return 1
    return mode_check(args)


if __name__ == "__main__":
    sys.exit(main())
