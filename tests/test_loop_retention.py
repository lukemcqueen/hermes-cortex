"""Hermetic tests for the loop-governance retention script.

The reference `skills/devops/loop-governance/references/db-maintenance.md` used to
carry this script only as prose, asserting a schema it never checked. It is now a
committed, runnable artefact and these tests exercise it against a throwaway DB
built from the REAL schema — not a convenient invention.

Schema columns copied verbatim from the live DB on 2026-10-22
(`PRAGMA table_info(loop_cycles)`), so a drift in the real table shows up here
rather than silently invalidating the reference:

    id, timestamp, task_id, cycle_num, spec_hash, code_hash, test_output_hash,
    completeness, quality, progress, composite, no_progress, decision,
    user_overrode, outcome_note, schema_version, model_name, session_id,
    unscored_reason

The CREATE TABLE statements below are LITERALS, one per column order, and the
insert uses a literal placeholder list. sqlite3 cannot parameterise identifiers,
so the only alternatives were f-strings or concatenation — both of which the
adversarial scanner refuses, correctly: a schema built by assembling strings is
the same shape whether the source is a fixture or a request body. Writing the
three orders out costs ~20 lines and removes the interpolation entirely, so the
guard is satisfied by construction instead of by a review of who calls it.
"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "skills" / "devops" / "loop-governance" / "scripts" / "loop-retention.py"

# variant -> (literal DDL, that table's column order)
VARIANTS = {
    "canon": (
        'CREATE TABLE loop_cycles ("id" INTEGER, "timestamp" TEXT, "task_id" TEXT, "cycle_num" INTEGER, "spec_hash" TEXT, "code_hash" TEXT, "test_output_hash" TEXT, "completeness" REAL, "quality" REAL, "progress" REAL, "composite" REAL, "no_progress" INTEGER, "decision" TEXT, "user_overrode" INTEGER, "outcome_note" TEXT, "schema_version" INTEGER, "model_name" TEXT, "session_id" TEXT, "unscored_reason" TEXT)',
        ["id", "timestamp", "task_id", "cycle_num", "spec_hash", "code_hash", "test_output_hash", "completeness", "quality", "progress", "composite", "no_progress", "decision", "user_overrode", "outcome_note", "schema_version", "model_name", "session_id", "unscored_reason"],
    ),
    "ts_first": (
        'CREATE TABLE loop_cycles ("timestamp" TEXT, "id" INTEGER, "task_id" TEXT, "cycle_num" INTEGER, "spec_hash" TEXT, "code_hash" TEXT, "test_output_hash" TEXT, "completeness" REAL, "quality" REAL, "progress" REAL, "composite" REAL, "no_progress" INTEGER, "decision" TEXT, "user_overrode" INTEGER, "outcome_note" TEXT, "schema_version" INTEGER, "model_name" TEXT, "session_id" TEXT, "unscored_reason" TEXT)',
        ["timestamp", "id", "task_id", "cycle_num", "spec_hash", "code_hash", "test_output_hash", "completeness", "quality", "progress", "composite", "no_progress", "decision", "user_overrode", "outcome_note", "schema_version", "model_name", "session_id", "unscored_reason"],
    ),
    "ts_last": (
        'CREATE TABLE loop_cycles ("id" INTEGER, "task_id" TEXT, "cycle_num" INTEGER, "spec_hash" TEXT, "code_hash" TEXT, "test_output_hash" TEXT, "completeness" REAL, "quality" REAL, "progress" REAL, "composite" REAL, "no_progress" INTEGER, "decision" TEXT, "user_overrode" INTEGER, "outcome_note" TEXT, "schema_version" INTEGER, "model_name" TEXT, "session_id" TEXT, "unscored_reason" TEXT, "timestamp" TEXT)',
        ["id", "task_id", "cycle_num", "spec_hash", "code_hash", "test_output_hash", "completeness", "quality", "progress", "composite", "no_progress", "decision", "user_overrode", "outcome_note", "schema_version", "model_name", "session_id", "unscored_reason", "timestamp"],
    ),
}

# 19 columns in every variant above, so ONE literal statement serves all three.
# No column list: VALUES therefore land in the table's own declared order.
INSERT_SQL = "INSERT INTO loop_cycles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"

OLD_TS = ["2020-01-01 00:00:00", "2020-01-02 00:00:00", "2020-01-03 00:00:00"]
NEW_TS = ["2999-01-01 00:00:00", "2999-01-02 00:00:00"]


def _build_db(path, variant="canon"):
    """A loop_cycles table in the named column ORDER, with rows either side of the window."""
    ddl, order = VARIANTS[variant]
    con = sqlite3.connect(path)
    con.execute(ddl)
    rows = []
    for i, ts in enumerate(OLD_TS + NEW_TS):
        vals: dict = {c: None for c in order}
        vals["id"] = i + 1
        vals["timestamp"] = ts
        vals["composite"] = float(i + 1)
        vals["task_id"] = f"task-{i + 1}"
        rows.append(tuple(vals[c] for c in order))
    con.executemany(INSERT_SQL, rows)
    con.commit()
    con.close()
    return len(OLD_TS), len(NEW_TS)


def _run(db, *extra):
    # timeout: a hung child would hang the whole suite rather than fail it.
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--db", str(db), *extra],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "PYTHONPATH": ""},
    )


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "loop-governance.db"
    old, new = _build_db(path)
    return path, old, new


def test_script_is_committed_and_runnable():
    """The reviewer's point: a script that exists only inside a document cannot run."""
    assert SCRIPT.is_file(), f"retention script is not committed at {SCRIPT}"


def test_dry_run_reports_the_real_range_and_changes_nothing(db):
    path, old, new = db
    before = path.read_bytes()
    r = _run(path)
    assert r.returncode == 0, r.stderr
    assert "[DRY RUN]" in r.stdout
    assert f"Would archive {old} cycles" in r.stdout
    assert "2020-01-01 00:00:00" in r.stdout and "2020-01-03 00:00:00" in r.stdout
    assert path.read_bytes() == before, "dry-run must not touch the DB"


def test_apply_archives_and_deletes_only_the_old_rows(db, tmp_path, monkeypatch):
    path, old, new = db
    # Point the archive at tmp_path so the test never writes into ~/.hermes-cortex/data.
    monkeypatch.setenv("HOME", str(tmp_path))
    r = _run(path, "--apply")
    assert r.returncode == 0, r.stderr

    con = sqlite3.connect(path)
    remaining = con.execute("SELECT COUNT(*) FROM loop_cycles").fetchone()[0]
    surviving = [row[0] for row in con.execute("SELECT timestamp FROM loop_cycles")]
    con.close()
    assert remaining == new, f"expected {new} rows to survive, got {remaining}"
    assert all(ts.startswith("2999") for ts in surviving), surviving


def test_apply_leaves_a_clean_db_alone(db):
    """No old rows -> nothing to do, and no failure."""
    path, _, _ = db
    con = sqlite3.connect(path)
    con.execute("DELETE FROM loop_cycles WHERE timestamp < datetime('now', '-90 days')")
    con.commit()
    con.close()
    r = _run(path, "--apply")
    assert r.returncode == 0, r.stderr
    assert "DB is clean" in r.stdout


@pytest.mark.parametrize("variant", ["ts_first", "ts_last"])
def test_timestamp_is_found_by_name_not_by_index(tmp_path, variant):
    """The bug this replaces: `min(r[1] for r in old_rows)`, a POSITIONAL index.

    On the live table `timestamp` happens to sit at index 1, so a positional read
    looks correct — and reports whatever field lands in that slot the moment the
    column order changes. These two variants move it first and last; the reported
    range must not move with it.
    """
    path = tmp_path / f"{variant}.db"
    _build_db(path, variant)
    r = _run(path)
    assert r.returncode == 0, r.stderr
    assert "2020-01-01 00:00:00" in r.stdout and "2020-01-03 00:00:00" in r.stdout, (
        f"range reported wrong when the table's columns are in {variant} order:\n{r.stdout}"
    )


def test_missing_timestamp_column_fires_a_warning_not_a_guess(tmp_path):
    """A check that cannot run is a third outcome — say COULD NOT VERIFY, don't crash quietly."""
    path = tmp_path / "no-ts.db"
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE loop_cycles ("id" INTEGER, "composite" REAL)')
    con.commit()
    con.close()
    r = _run(path)
    assert r.returncode != 0
    assert "COULD NOT VERIFY" in (r.stdout + r.stderr)


def test_missing_db_is_reported(tmp_path):
    r = _run(tmp_path / "nope.db")
    assert r.returncode == 3
    assert "COULD NOT VERIFY" in (r.stdout + r.stderr)


def test_archive_json_holds_the_full_rows(tmp_path, monkeypatch):
    path = tmp_path / "loop-governance.db"
    _build_db(path)
    monkeypatch.setenv("HOME", str(tmp_path))
    r = _run(path, "--apply")
    assert r.returncode == 0, r.stderr
    archives = list((tmp_path / ".hermes-cortex" / "data").glob("loop-cycles-archive-*.json"))
    assert len(archives) == 1, f"expected one archive, found {archives}"
    payload = json.loads(archives[0].read_text())
    assert len(payload) == 3
    assert {"id", "timestamp", "composite"} <= set(payload[0])
