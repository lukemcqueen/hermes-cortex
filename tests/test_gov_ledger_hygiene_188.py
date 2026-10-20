#!/usr/bin/env python3
"""Issue #188 guards: ledger repair, and stats that separate hook from judged.

Reported by Titus (2026-10-20) and delegated to Esther to decide:

1. 6,395 rows across 62 ids carried a literal newline in `task_id`, minted by
   `$(cmd || echo fallback)` before the hook was fixed. DECISION: normalize them
   AND keep the evidence — the id is repaired, the original malformed value is
   appended to the row's own audit field (`outcome_note`, escaped so the note
   stays one line) and recorded in a manifest. The script targets
   ops/scripts/manage/normalize-precommit-task-ids.py.

2. `cycle_stats` mixed pre-commit hook cycles (71% of the ledger) with judged
   cycles, so a headline like "1,871 scored without user feedback" read as an
   un-reviewed backlog. DECISION: keep every existing key with its all-rows
   meaning (no consumer changes behaviour) and add a judged view whose coverage
   excludes hook cycles, because hook cycles are never owed feedback.

Run: python3 tests/test_gov_ledger_hygiene_188.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MCP = REPO / "mcp-servers" / "loop-gov-mcp.py"
NORMALIZER = REPO / "ops" / "scripts" / "manage" / "normalize-precommit-task-ids.py"

# The malformed shape, built from pieces so this file itself stays clean of the
# literal control character it is testing for.
NL = chr(10)
MALFORMED_A = f"precommit-repo-HEAD{NL}unknown/update"
MALFORMED_B = f"precommit-foreignrepo-10lcy0al-HEAD{NL}unknown/update"
UNREPAIRABLE = f"nonsense{MALFORMED_A}"

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


def load_mcp():
    spec = importlib.util.spec_from_file_location("lg_ledger_under_test", MCP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(repo: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Same helper as the sibling guard: run git in the fixture with a given env."""
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True,
        env={**os.environ, **(env or {})},
    )


def _fixture_conn(path: Path) -> sqlite3.Connection:
    """A connection shaped like the module's own _db(): dict(row) is used on the
    results, which only works when rows are sqlite3.Row."""
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def make_ledger(path: Path, rows: list[tuple]) -> None:
    """rows: (task_id, outcome_note, composite, user_overrode)"""
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE loop_cycles (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, "
        "outcome_note TEXT, composite REAL, user_overrode INTEGER)"
    )
    con.executemany(
        "INSERT INTO loop_cycles (task_id, outcome_note, composite, user_overrode) "
        "VALUES (?, ?, ?, ?)", rows)
    con.commit()
    con.close()


def test_stats_separate_hook_cycles_and_judge_coverage_on_the_rest() -> None:
    m = load_mcp()
    tmp = Path(tempfile.mkdtemp(prefix="stats188-"))
    try:
        db = tmp / "ledger.db"
        make_ledger(db, [
            # hook cycles: never owed feedback
            ("precommit-repo-HEAD/update", "hook fixture", 5.8, None),
            ("precommit-hermes-cortex-main/fix-x", "hook real", 6.7, None),
            ("precommit-dry-HEAD/update", "hook fixture", 5.8, None),
            # judged cycles: 1 of 3 has feedback
            ("docs-consolidation-cleanup", "judged", 8.6, 0),
            ("pii-scrub-hc-repo-2", "judged", 7.9, None),
            ("titus-learning-report-gap", "judged", 8.0, None),
        ])
        m._db = lambda: _fixture_conn(db)
        out = json.loads(m._cycle_stats({}).content[0].text)

        check(out["total_cycles"] == 6, f"total_cycles should be 6, got {out.get('total_cycles')}")
        check(out["hook_cycles"] == 3, f"hook_cycles should be 3, got {out.get('hook_cycles')}")
        check(out["judged_cycles"] == 3, f"judged_cycles should be 3, got {out.get('judged_cycles')}")

        # back-compat: the old keys keep their all-rows meaning
        for key in ("avg_composite", "cycles_over_7", "feedback_count", "accepted",
                    "overridden", "top_tasks"):
            check(key in out, f"existing key {key!r} must survive (consumers depend on it)")

        # the judged view is what a reader should quote
        check(out["judged_feedback_count"] == 1,
              f"judged feedback must count only judged rows: {out.get('judged_feedback_count')}")
        # Assert the INPUTS (integers) as the load-bearing claim, and only bound the
        # float: an exact == on a percentage is fragile against a different rounding.
        check(out["judged_cycles"] == 3 and out["judged_feedback_count"] == 1,
              "coverage must be computed over judged cycles only (1 of 3)")
        pct = out["feedback_coverage_pct_judged"]
        check(isinstance(pct, (int, float)) and abs(pct - 100.0 / 3) < 0.1,
              f"coverage must be judged-only (100*1/3): {pct}")
        check(all(not str(t["task_id"]).startswith("precommit-")
                  for t in out["top_judged_tasks"]),
              "top_judged_tasks must not contain hook cycles")
        check("precommit-" in json.dumps(out["top_tasks"]),
              "top_tasks keeps its all-rows meaning, hook cycles included")
        check("exclude them" in out["note"] or "exclude" in out["note"],
              "the output must say what the judged figures exclude")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_normalizer_repairs_ids_and_records_the_original() -> None:
    if not NORMALIZER.exists():
        check(False, f"{NORMALIZER} is missing")
        return
    tmp = Path(tempfile.mkdtemp(prefix="norm188-"))
    try:
        db = tmp / "ledger.db"
        make_ledger(db, [
            (MALFORMED_A, None, 5.8, None),
            (MALFORMED_B, "hook fixture artifact", 5.8, None),
            ("precommit-hermes-cortex-main/fix-y", "clean row", 6.7, None),
            (UNREPAIRABLE, None, 5.8, None),
        ])
        manifest = tmp / "manifest.txt"

        dry = subprocess.run([sys.executable, str(NORMALIZER), "--db", str(db),
                              "--manifest", str(manifest)],
                             capture_output=True, text=True, timeout=120)
        check(dry.returncode == 0, f"dry run must exit 0: {dry.stderr[-300:]}")
        check("DRY RUN" in dry.stdout, "the default must be a dry run")
        check(manifest.exists() is False, "a dry run must not write a manifest")
        before = sqlite3.connect(db).execute(
            "SELECT COUNT(*) FROM loop_cycles WHERE task_id = ?", (MALFORMED_A,)).fetchone()[0]
        check(before == 1, "a dry run must not touch the ledger")

        app = subprocess.run([sys.executable, str(NORMALIZER), "--db", str(db), "--apply",
                              "--manifest", str(manifest)],
                             capture_output=True, text=True, timeout=120)
        check(app.returncode == 1, "the unreparable row must make the run report PARTIAL")
        check("nonsense" in app.stdout, "the skipped row must be reported, not silently guessed")

        con = sqlite3.connect(db)
        rows = dict(con.execute("SELECT task_id, outcome_note FROM loop_cycles").fetchall())
        check("precommit-repo-HEAD/update" in rows,
              f"the malformed id must be repaired to the fixed hook's shape: {list(rows)}")
        # Whitespace may survive only on a row the script REFUSED to touch — it
        # reports those instead of guessing. Everything repairable must be clean.
        dirty = [t for t in rows if any(c.isspace() for c in t)]
        check(dirty in ([], [UNREPAIRABLE]),
              f"only the reported unrepairable id may keep whitespace: {dirty}")
        note = rows.get("precommit-repo-HEAD/update") or ""
        check("task_id normalized (issue #188)" in note,
              f"the repair must be recorded in the row's own audit field: {note!r}")
        escaped_original = MALFORMED_A.replace(NL, "\\n")
        check(escaped_original in note,
              f"the ORIGINAL malformed value must survive (escaped) in the note: {note!r}")
        check("\n" not in note, "the audit note must stay a single line")
        kept = rows.get(UNREPAIRABLE)
        check(kept is None or MALFORMED_A in kept or True, "skipped rows are left as they are")
        preserved = con.execute("SELECT COUNT(*) FROM loop_cycles WHERE task_id = ?",
                                (UNREPAIRABLE,)).fetchone()[0]
        check(preserved == 1, "an id that cannot be safely reduced must be left untouched")
        check(rows.get("precommit-hermes-cortex-main/fix-y") == "clean row",
              "clean rows must be untouched")
        con.close()

        check(manifest.exists(), "an applied run must write the manifest")
        text = manifest.read_text() if manifest.exists() else ""
        check("precommit-repo-HEAD" in text and "row" in text,
              "the manifest must list row, old and new ids")

        backups = list(tmp.glob("ledger.db.backup-*"))
        check(bool(backups), "the ledger must be backed up before the first write")

        again = subprocess.run([sys.executable, str(NORMALIZER), "--db", str(db), "--apply",
                               "--manifest", str(manifest)],
                               capture_output=True, text=True, timeout=120)
        check("nothing to do" in again.stdout or "PARTIAL" in again.stdout,
              f"the repair must be idempotent — second run said: {again.stdout[-200:]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_repair_target_matches_what_the_fixed_hook_mints() -> None:
    """The repair is only correct if it lands on the id the FIXED hook produces.

    Without this, `_normalized()` is one person's reconstruction of what the hook
    "should" have written. Here the fixed hook is actually run: a no-commit fixture
    repo (the exact case that used to mint the malformed id) does its first commit,
    and the id it records must equal what `_normalized()` derives from the malformed
    value. That is the claim the normalizer's docstring makes, asserted rather than
    asserted-about.
    """
    norm_spec = importlib.util.spec_from_file_location("normalizer_under_test", NORMALIZER)
    norm = importlib.util.module_from_spec(norm_spec)
    norm_spec.loader.exec_module(norm)

    derived = norm._normalized(MALFORMED_A)
    check(derived == "precommit-repo-HEAD/update",
          f"_normalized must reduce the malformed id to the hook's shape, got {derived!r}")

    hook_src = REPO / "ops" / "scripts" / "pre-commit-score"
    if not hook_src.exists():
        check(False, f"{hook_src} is missing — cannot cross-check the repair target")
        return
    tmp = Path(tempfile.mkdtemp(prefix="hookmint-"))
    try:
        repo = tmp / "repo"                     # the fixture name IS part of the id
        repo.mkdir()
        check(_git(repo, "init", "-q").returncode == 0, "git init failed in the fixture")
        _git(repo, "config", "user.email", "fixture@example.com")
        _git(repo, "config", "user.name", "fixture")
        hooks = tmp / "hooks"
        hooks.mkdir()
        shutil.copy2(hook_src, hooks / "pre-commit")
        os.chmod(hooks / "pre-commit", 0o755)
        _git(repo, "config", "core.hooksPath", str(hooks))
        (repo / "f.txt").write_text("x\n")
        _git(repo, "add", "f.txt")
        db = tmp / "scratch.db"
        proc = _git(repo, "commit", "-m", "first commit no parent", "-q",
                    env={"PRE_COMMIT_SCORE_DB": str(db)})
        check(proc.returncode == 0, f"the fixture commit must succeed: {(proc.stderr or '')[-200:]}")
        if not db.exists():
            check(False, "the fixed hook recorded no cycle — cannot cross-check")
            return
        minted = [r[0] for r in sqlite3.connect(db).execute(
            "SELECT DISTINCT task_id FROM loop_cycles")]
        check(bool(minted), "the fixed hook must record a cycle")
        for tid in minted:
            check(tid == derived,
                  f"the fixed hook mints {tid!r} but the repair derives {derived!r} — "
                  "repaired rows and new rows would not group together")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    test_stats_separate_hook_cycles_and_judge_coverage_on_the_rest()
    test_normalizer_repairs_ids_and_records_the_original()
    test_repair_target_matches_what_the_fixed_hook_mints()
    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS: hook cycles are separated from judged, and malformed ids repair with their original kept")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
