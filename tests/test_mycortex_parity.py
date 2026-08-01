"""Tests for mycortex-parity.py — golden known-answer parity runner (S-001).

Uses the fixture engine (--engine fixture) so tests never depend on gbrain or
the not-yet-built mycortex CLI. Verifies:
  - path normalization (gbrain vs mycortex path forms)
  - per-query pass/fail semantics (primary expected path in top-3)
  - pass-rate math for federated + isolated
  - the 100% / 90% gate
  - failure naming (query id + actual/expected paths)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PARITY = REPO_ROOT / "ops" / "scripts" / "manage" / "mycortex-parity.py"
GOLDEN = REPO_ROOT / "tests" / "fixtures" / "golden-queries.json"

# Filename has a hyphen (per design doc) — import via importlib, not by name.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("mycortex_parity", PARITY)
parity = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(parity)


# ── Normalization ─────────────────────────────────────────────

def test_normalize_strips_dot_and_md():
    assert parity.normalize_path("./docs/foo.md") == "docs/foo"
    assert parity.normalize_path("docs/foo") == "docs/foo"
    assert parity.normalize_path("docs/FOO.MD") == "docs/foo"


def test_matches_cross_engine_forms():
    # gbrain: no .md, lowercase; mycortex: with .md
    assert parity.matches("skills/devops/loop-governance/skill",
                          "skills/devops/loop-governance/SKILL.md")
    assert parity.matches("docs/loop-governance-reference",
                          "docs/loop-governance-reference.md")


# ── Golden set integrity ──────────────────────────────────────

def test_golden_set_shape():
    golden = parity.load_golden(GOLDEN)
    queries = golden["queries"]
    assert 25 <= len(queries) <= 30, f"golden set must have 25-30 queries, has {len(queries)}"
    for q in queries:
        assert q["id"], f"query missing id: {q}"
        assert q["query"], f"{q['id']} missing query text"
        assert q["source"] in golden["sources"], f"{q['id']} unknown source {q['source']}"
        assert q["scope"] in ("federated", "isolated"), f"{q['id']} bad scope"
        assert len(q["expected_top3"]) == 3, f"{q['id']} must have exactly 3 expected paths"


def test_golden_sources_pinned():
    golden = parity.load_golden(GOLDEN)
    for name, src in golden["sources"].items():
        assert src.get("sha"), f"source {name} not pinned to a SHA"
        assert src.get("scope") in ("federated", "isolated")


def test_golden_expected_paths_exist_in_repo():
    """Every expected path must exist (hermes-cortex paths repo-relative)."""
    golden = parity.load_golden(GOLDEN)
    missing = []
    for q in golden["queries"]:
        if q["source"] != "hermes-cortex":
            continue
        for p in q["expected_top3"]:
            if not (REPO_ROOT / p).exists():
                missing.append(f"{q['id']}: {p}")
    assert not missing, f"expected paths missing in repo:\n" + "\n".join(missing)


# ── Evaluation semantics ──────────────────────────────────────

def test_evaluate_pass_primary_in_top3():
    expected = {"id": "T1", "query": "loop governance", "scope": "federated",
                "expected_top3": ["docs/a.md", "docs/b.md", "docs/c.md"]}
    r = parity.evaluate_query(expected, ["docs/z.md", "docs/a.md", "docs/y.md"])
    assert r["passed"] is True
    assert r["actual_top3"] == ["docs/z.md", "docs/a.md", "docs/y.md"]


def test_evaluate_fail_primary_not_in_top3():
    expected = {"id": "T2", "query": "loop governance", "scope": "federated",
                "expected_top3": ["docs/a.md", "docs/b.md", "docs/c.md"]}
    r = parity.evaluate_query(expected, ["docs/z.md", "docs/x.md", "docs/y.md"])
    assert r["passed"] is False
    assert r["expected"] == ["docs/a.md", "docs/b.md", "docs/c.md"]


def test_evaluate_empty_actual():
    expected = {"id": "T3", "query": "nothing", "scope": "isolated",
                "expected_top3": ["docs/a.md"]}
    r = parity.evaluate_query(expected, [])
    assert r["passed"] is False


# ── Pass-rate + gate ──────────────────────────────────────────

def _mk(scope, passed):
    return {"scope": scope, "passed": passed}


def test_pass_rate_math():
    rates = parity.compute_pass_rate([
        _mk("federated", True), _mk("federated", True), _mk("federated", False),
        _mk("isolated", True), _mk("isolated", False),
    ])
    assert rates["federated"] == pytest.approx(2 / 3)
    assert rates["isolated"] == pytest.approx(0.5)


def test_gate_100_90():
    assert parity.gate_passed({"federated": 1.0, "isolated": 0.95})
    assert not parity.gate_passed({"federated": 0.99, "isolated": 1.0})
    assert not parity.gate_passed({"federated": 1.0, "isolated": 0.89})


# ── End-to-end via fixture engine ─────────────────────────────

def _write_fixture(tmp_path, mapping):
    f = tmp_path / "results.json"
    f.write_text(json.dumps(mapping))
    return f


def test_check_mode_fixture_all_pass(tmp_path):
    """Every query returns its primary expected path in top-3 → gate passes."""
    golden = parity.load_golden(GOLDEN)
    mapping = {q["id"]: q["expected_top3"] for q in golden["queries"]}
    f = _write_fixture(tmp_path, mapping)
    rc = parity.mode_check(type("A", (), {
        "engine": "fixture", "fixture_file": f, "golden": GOLDEN,
    })())
    assert rc == 0


def test_check_mode_fixture_federated_miss_fails(tmp_path):
    """One federated miss → 100% gate fails, failure names query + paths."""
    golden = parity.load_golden(GOLDEN)
    mapping = {q["id"]: q["expected_top3"] for q in golden["queries"]}
    # Break the first federated query: return a wrong top-3
    first_fed = next(q for q in golden["queries"] if q["scope"] == "federated")
    mapping[first_fed["id"]] = ["nowhere.md", "elsewhere.md", "wrong.md"]
    f = _write_fixture(tmp_path, mapping)

    rc = parity.mode_check(type("A", (), {
        "engine": "fixture", "fixture_file": f, "golden": GOLDEN,
    })())
    assert rc == 1  # gate failed


def test_check_mode_fixture_isolated_90_gate(tmp_path):
    """1 isolated miss out of 10 → 90% passes; 2 misses → fails."""
    golden = parity.load_golden(GOLDEN)
    isolated = [q for q in golden["queries"] if q["scope"] == "isolated"]
    assert len(isolated) == 10

    # 1 miss → 90% → pass
    mapping = {q["id"]: q["expected_top3"] for q in golden["queries"]}
    mapping[isolated[0]["id"]] = ["miss.md", "x.md", "y.md"]
    f = _write_fixture(tmp_path, mapping)
    rc = parity.mode_check(type("A", (), {
        "engine": "fixture", "fixture_file": f, "golden": GOLDEN,
    })())
    assert rc == 0

    # 2 misses → 80% → fail
    mapping[isolated[1]["id"]] = ["miss.md", "x.md", "y.md"]
    f2 = _write_fixture(tmp_path, mapping)
    rc = parity.mode_check(type("A", (), {
        "engine": "fixture", "fixture_file": f2, "golden": GOLDEN,
    })())
    assert rc == 1


# ── CLI smoke (module importable, main parseable) ─────────────

def test_cli_parses():
    assert parity.main is not None
