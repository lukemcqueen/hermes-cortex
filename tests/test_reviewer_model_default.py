#!/usr/bin/env python3
"""The reviewer's DEFAULT model must be the canonical reviewer, never flash.

WHY THIS FILE EXISTS (operator directive, 2026-10-18, verbatim): "FLASH SHOULD NOT BE THE REVIEWER
DEFAULT." Measured on this host before the fix: `_tier` returns "light" as its CATCH-ALL
(mcp-servers/loop-gov-mcp.py:4581), `REVIEWER_LIGHT_MODEL_DEFAULT` was
deepseek/deepseek-v4-flash (:3763), and no `ADVERSARIAL_REVIEW_LIGHT_MODEL` override was set — so
every ORDINARY change was judged by flash while the module's own docstring claimed the reviewer is
deepseek/deepseek-v4-pro. The tier existed to save transport time; it silently decided the judge.

Two properties are pinned here, and both must hold together:

  1. With no explicit operator choice, a light-tier change is judged by the CANONICAL reviewer.
     Choosing the cheaper judge stays POSSIBLE — it is an explicit env var, so it is an operator
     decision recorded in the environment rather than a default nobody picked.
  2. Every recorded blob verdict NAMES the model that produced it. The columns already exist and
     the writer already accepts them; the per-blob call site simply passed neither, so all 144
     rows in blob_reviews carried an empty reviewer_model and no record could show which judge
     produced a verdict. A default you cannot read back is not verifiable.

Run: python3 tests/test_reviewer_model_default.py
"""
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "mcp-servers" / "loop-gov-mcp.py"


def _mod():
    spec = importlib.util.spec_from_file_location("loop_gov_model_under_test", SERVER)
    assert spec is not None and spec.loader is not None, f"cannot load {SERVER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _light_cx():
    """A change that is complex enough to be reviewed but on no always-review surface: the
    catch-all `return "light"` — i.e. the ordinary case, which is the one that was judged by
    flash."""
    return {"always_review": False, "files": 1, "lines": 4}


def _conn():
    """The blob_reviews table as the server creates it, with no store and no git."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE blob_reviews (blob_sha TEXT PRIMARY KEY, verdict TEXT,"
                 " findings_json TEXT, summary TEXT, reviewer_id TEXT, reviewer_model TEXT,"
                 " ts TEXT)")
    return conn


def test_the_ordinary_case_is_not_judged_by_flash():
    """THE directive. An ordinary complex change is tier "light" — and must still get the canonical
    reviewer, because the tier is about transport and depth-of-wait, not about who judges.

    Both env vars are SAVED and RESTORED: popping them unconditionally would silently discard an
    operator's own ADVERSARIAL_REVIEWER_MODEL for every later test in this process.
    """
    mod = _mod()
    saved = {k: os.environ.pop(k, None) for k in
             ("ADVERSARIAL_REVIEW_LIGHT_MODEL", "ADVERSARIAL_REVIEWER_MODEL")}
    try:
        assert mod._tier(_light_cx()) == "light", "precondition: this is the catch-all tier"
        chosen = mod._light_reviewer_model()
        label = mod._reviewer_label(_light_cx())
        assert "flash" not in chosen.lower(), f"flash is still the light-tier default: {chosen}"
        assert "flash" not in label.lower(), f"the recorded label would name flash: {label}"
        assert chosen == mod.REVIEWER_MODEL_DEFAULT, (chosen, mod.REVIEWER_MODEL_DEFAULT)
        assert label == mod.REVIEWER_MODEL_DEFAULT, (label, mod.REVIEWER_MODEL_DEFAULT)
        print(f"  ordinary change -> tier {mod._tier(_light_cx())}, judge {chosen} ✓")
    finally:
        for _k, _v in saved.items():
            if _v is not None:
                os.environ[_k] = _v


def test_the_cheaper_judge_is_still_reachable_by_an_explicit_operator_choice():
    """Not forbidden — opt-in. A downgrade must be an operator decision visible in the environment,
    which is exactly what the env var is."""
    mod = _mod()
    os.environ["ADVERSARIAL_REVIEW_LIGHT_MODEL"] = "deepseek/deepseek-v4-flash"
    try:
        assert mod._light_reviewer_model() == "deepseek/deepseek-v4-flash", mod._light_reviewer_model()
        assert mod._reviewer_label(_light_cx()) == "deepseek/deepseek-v4-flash"
    finally:
        os.environ.pop("ADVERSARIAL_REVIEW_LIGHT_MODEL", None)
    print("  explicit ADVERSARIAL_REVIEW_LIGHT_MODEL still selects the cheaper judge ✓")


def test_every_blob_verdict_records_the_model_that_judged_it():
    """A default you cannot read back is not verifiable. The writer already accepts the model; the
    call site passed none, so no stored row named its judge."""
    mod = _mod()
    conn = _conn()
    try:
        mod._review_uncovered_blobs(
            {"a.py": "shaA"}, reviewer=lambda sha, path, material: '{"verdict": "CLEAN", "findings": []}',
            material_for=lambda sha, path: "material", reviewer_label="deepseek/deepseek-v4-pro",
            conn=conn)
        row = conn.execute("SELECT verdict, reviewer_model FROM blob_reviews "
                           "WHERE blob_sha='shaA'").fetchone()
        assert row is not None, "the verdict was not recorded at all"
        assert row[0] == "CLEAN", row
        assert row[1] == "deepseek/deepseek-v4-pro", (
            f"the stored verdict must name its judge, got {row[1]!r}")
    finally:
        conn.close()
    print("  blob verdict records its judge ✓")


def test_the_close_call_site_PASSES_the_label_down():
    """The plumbing that matters: the close knows the reviewer it dispatched and must hand that
    label to the store. Asserted on the source because the alternative — a full close against a
    live store — is the thing this whole change is about not being able to do quickly."""
    src = SERVER.read_text()
    assert "reviewer_label=_reviewer_label(cx)" in src, \
        "the close's per-blob call must pass the reviewer label it dispatched"
    print("  the close hands the dispatched reviewer's label to the store ✓")


def test_a_whitespace_override_falls_back_to_the_canonical_reviewer():
    """An env var set to spaces is not an operator choice. It must resolve to the canonical
    reviewer — not to nothing, and not to the cheaper judge."""
    mod = _mod()
    os.environ["ADVERSARIAL_REVIEW_LIGHT_MODEL"] = "   "
    try:
        assert mod._light_reviewer_model() == mod.REVIEWER_MODEL_DEFAULT, \
            mod._light_reviewer_model()
    finally:
        os.environ.pop("ADVERSARIAL_REVIEW_LIGHT_MODEL", None)
    print("  whitespace override -> canonical reviewer ✓")


def test_a_BLOCKING_verdict_also_records_its_judge():
    """The judge matters MOST when it blocks: a worker contesting a FINDINGS verdict has to be able
    to name which model produced it, and how strong it was."""
    mod = _mod()
    conn = _conn()
    try:
        mod._review_uncovered_blobs(
            {"b.py": "shaB"},
            reviewer=lambda sha, path, material: json.dumps(
                {"verdict": "FINDINGS", "findings": [
                    {"finding_id": "F-1", "severity": "high", "evidence": "quoted fragment"}]}),
            material_for=lambda sha, path: "material", reviewer_label="deepseek/deepseek-v4-pro",
            conn=conn)
        row = conn.execute("SELECT verdict, reviewer_model FROM blob_reviews "
                           "WHERE blob_sha='shaB'").fetchone()
        assert row is not None and str(row[0]).upper() == "FINDINGS", row
        assert row[1] == "deepseek/deepseek-v4-pro", f"a blocking verdict must name its judge: {row}"
    finally:
        conn.close()
    print("  a blocking verdict records its judge too ✓")


def test_an_EMPTY_label_still_records_the_verdict_and_flags_the_gap():
    """A caller that passes no label must not lose the VERDICT — an unrecorded verdict is a blob
    that gets re-bought on every close. The row is written with the empty value it was given, so
    the gap is visible in the record rather than silently absent."""
    mod = _mod()
    conn = _conn()
    try:
        mod._review_uncovered_blobs(
            {"c.py": "shaC"},
            reviewer=lambda sha, path, material: '{"verdict": "CLEAN", "findings": []}',
            material_for=lambda sha, path: "material", conn=conn)
        row = conn.execute("SELECT verdict, reviewer_model FROM blob_reviews "
                           "WHERE blob_sha='shaC'").fetchone()
        assert row is not None, "the verdict was dropped when no label was given"
        assert str(row[0]).upper() == "CLEAN", row
        assert (row[1] or "") == "", f"nothing may be invented for the judge: {row[1]!r}"
    finally:
        conn.close()
    print("  empty label still records the verdict, judge left visibly blank ✓")


def _main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    if not tests:
        print("NO TESTS RAN — this file executed nothing")
        return 1
    print("server:", SERVER)
    assert SERVER.is_file(), f"missing server: {SERVER}"
    failed = []
    for name, fn in tests:
        try:
            fn()
        except Exception:
            import traceback
            failed.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()
    if failed:
        print(f"RESULT: FAIL ({len(failed)}/{len(tests)}): {failed}")
        return 1
    print(f"RESULT: ALL PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
