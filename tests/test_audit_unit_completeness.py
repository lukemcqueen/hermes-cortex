#!/usr/bin/env python3
"""Tests for the corpus completeness audit helper shipped with the
corpus-scrape-and-verify skill.

The script exists because a scraped corpus that was short by exactly one
unit still looked plausible in a total row count — the audit must fail
loudly on a missing unit, a missing sub-unit, a short sub-unit, and a
duplicate natural key, and pass only when every expected unit/sub-unit is
present with the expected count.

Run: python3 -m pytest tests/test_audit_unit_completeness.py -q
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = (
    _REPO
    / "skills"
    / "software-development"
    / "corpus-scrape-and-verify"
    / "scripts"
    / "audit_unit_completeness.py"
)


def _run(rows_path, expect_path=None):
    cmd = [sys.executable, str(_SCRIPT), "--rows", str(rows_path)]
    if expect_path is not None:
        cmd += ["--expect", str(expect_path)]
    return subprocess.run(cmd, capture_output=True, text=True)


def _write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _write_expect(path, rows):
    path.write_text(
        "\n".join(f"{u}\t{s}\t{c}" for u, s, c in rows) + "\n", encoding="utf-8"
    )


@pytest.fixture
def corpus(tmp_path):
    """Two units, each with two sub-units of two rows — the clean case."""
    rows = []
    for unit in ("Alpha", "Beta"):
        for chapter in (1, 2):
            for verse in (1, 2):
                rows.append({"unit": unit, "chapter": chapter, "verse": verse})
    rows_path = tmp_path / "rows.jsonl"
    _write_jsonl(rows_path, rows)
    expect_path = tmp_path / "expect.tsv"
    _write_expect(
        expect_path,
        [("Alpha", 1, 2), ("Alpha", 2, 2), ("Beta", 1, 2), ("Beta", 2, 2)],
    )
    return rows, rows_path, expect_path


def test_script_exists():
    assert _SCRIPT.is_file(), f"audit script missing at {_SCRIPT}"


def test_clean_corpus_passes(corpus):
    _rows, rows_path, expect_path = corpus
    res = _run(rows_path, expect_path)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "OK" in res.stdout


def test_missing_unit_fails(corpus):
    """A fully missing unit must be caught — the failure mode the script exists for."""
    rows, rows_path, expect_path = corpus
    kept = [r for r in rows if r["unit"] != "Beta"]
    _write_jsonl(rows_path, kept)
    res = _run(rows_path, expect_path)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "MISSING UNIT: Beta" in res.stdout


def test_short_subunit_fails(corpus):
    """A sub-unit with fewer rows than expected must be reported."""
    rows, rows_path, expect_path = corpus
    # Drop one row from Beta chapter 2 so it has 1 row instead of 2.
    kept = [
        r
        for r in rows
        if not (r["unit"] == "Beta" and r["chapter"] == 2 and r["verse"] == 2)
    ]
    _write_jsonl(rows_path, kept)
    res = _run(rows_path, expect_path)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "Beta" in res.stdout
    assert "count mismatch" in res.stdout


def test_duplicate_row_fails(corpus):
    """A duplicated natural key is a defect even when counts look right."""
    rows, rows_path, expect_path = corpus
    _write_jsonl(rows_path, rows + [rows[0]])
    res = _run(rows_path, expect_path)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "duplicate row" in res.stdout


def test_missing_subunit_fails(corpus):
    """A missing sub-unit (chapter) inside a present unit must be caught."""
    rows, rows_path, expect_path = corpus
    kept = [r for r in rows if not (r["unit"] == "Alpha" and r["chapter"] == 2)]
    _write_jsonl(rows_path, kept)
    res = _run(rows_path, expect_path)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "missing sub-units" in res.stdout


def test_no_expect_warns_it_cannot_detect_missing_unit(corpus):
    """Without an independent expected table a missing unit is undetectable —
    the script must say so rather than imply a clean bill."""
    _rows, rows_path, _expect_path = corpus
    res = _run(rows_path)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "CANNOT be detected" in res.stdout


def test_bad_expect_line_exits_nonzero(corpus):
    _rows, rows_path, expect_path = corpus
    expect_path.write_text("Alpha\t1\n", encoding="utf-8")  # only two fields
    res = _run(rows_path, expect_path)
    assert res.returncode != 0
    assert "bad --expect line" in (res.stdout + res.stderr)
