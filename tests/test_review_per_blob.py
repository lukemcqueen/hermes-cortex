#!/usr/bin/env python3
"""Per-blob review: a wide range must stop being unshippable.

The close-time reviewer is ONE call over the whole range, and a reasoning model
starved of output budget answers with null content — measured twice on an
8-file/381-line range at `max_tokens=48000` and again at `96000`. The contract
here is that the same judgement is earned in UNITS THE RECEIPT ALREADY SPEAKS:
one verdict per BLOB, keyed by blob sha, so a big range is a series of small
reviews, a re-review of identical content is free, and the receipt's
`reviewed_blobs` names only blobs that were actually judged.

Hermetic: the store is repointed to a throwaway DB and the reviewer is an
injected callable. No git, no network, no live governance state.

Run:  python3 tests/test_review_per_blob.py
   or: pytest tests/test_review_per_blob.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# The discrimination seam: point it at a pre-change module and this suite MUST
# fail (the baseline carries no per-blob surface at all).
SERVER = Path(os.environ.get("CORTEX_LOOP_GOV_SERVER", REPO / "mcp-servers" / "loop-gov-mcp.py"))


def _load_server(tmp: Path):
    """Import the server module with its store repointed. Inert on import.

    The file's entrypoint is behind `if __name__ == "__main__"`, and its only
    module-level side effect is constructing the MCP Server when the SDK is
    present — so importing it touches no live state. Repoint BEFORE anything
    runs regardless: `_ensure_schema` is memoized per database file.
    """
    spec = importlib.util.spec_from_file_location("loop_gov_per_blob_under_test", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.LOOP_DB = tmp / "loop-governance.db"
    mod.GOVERNANCE_STATE_DIR = tmp / "state"
    return mod


def _clean() -> str:
    return json.dumps({"verdict": "CLEAN", "findings": [], "summary": "no findings"})


def _findings(sev: str = "medium") -> str:
    return json.dumps({
        "verdict": "FINDINGS",
        "findings": [{
            "finding_id": "ADV-T-1",
            "severity": sev,
            "technique": "unverified-claim",
            "target": "the edited blob",
            "evidence": "this blob claims a behaviour with no test beside it",
            "recommendation": "add the test",
        }],
        "summary": "one finding",
    })


class Reviewer:
    """A reviewer that answers per blob and counts its calls."""

    def __init__(self, verdicts: dict[str, str]):
        self.verdicts = verdicts
        self.calls: list[str] = []

    def __call__(self, blob_sha: str, path: str, material: str) -> str:
        self.calls.append(blob_sha)
        if not material.strip():
            raise AssertionError(f"empty material handed to the reviewer for {path}")
        return self.verdicts.get(path, _clean())


def _drive(mod, blobs, reviewer, *, cap=12, budget=60.0, fresh=True):
    """Run the per-blob pass with an injected reviewer over a throwaway store."""
    conn = mod._db()
    return mod._review_uncovered_blobs(
        blobs,
        reviewer=reviewer,
        material_for=lambda sha, path: f"[{path} @ {sha[:8]}] diff text",
        cap=cap,
        budget_s=budget,
        conn=conn,
    )


def test_a_clean_blob_is_reviewed_once_then_cached(tmp_path):
    mod = _load_server(tmp_path)
    blobs = {"a.py": "sha-a", "b.py": "sha-b"}
    rev = Reviewer({})
    first = _drive(mod, blobs, rev)
    assert first["verdicts"] == {"sha-a": "CLEAN", "sha-b": "CLEAN"}, first
    assert first["remaining"] == [] and first["calls"] == 2, first

    second = _drive(mod, blobs, rev)
    assert second["calls"] == 0, (
        "a blob whose content already has a CLEAN verdict must not be re-reviewed "
        f"— the cache is what makes a re-close affordable: {second}"
    )
    assert second["verdicts"] == {"sha-a": "CLEAN", "sha-b": "CLEAN"}, second


def test_one_non_clean_blob_makes_the_range_not_clean(tmp_path):
    mod = _load_server(tmp_path)
    blobs = {"a.py": "sha-a", "b.py": "sha-b", "c.py": "sha-c"}
    rev = Reviewer({"b.py": _findings("medium")})
    res = _drive(mod, blobs, rev)
    assert res["verdicts"]["sha-b"] == "FINDINGS", res
    assert res["verdicts"]["sha-a"] == "CLEAN", res
    assert res["remaining"] == [], res
    assert res["blocking"], "a MEDIUM finding must surface as blocking: %s" % res

    # and the clean blobs still cached work is kept: only the failing blob is re-asked
    rev.calls.clear()
    again = _drive(mod, blobs, rev)
    assert rev.calls == ["sha-b"], (
        "a re-close must re-ask ONLY the blob that failed, not re-review the range: "
        f"{rev.calls} / {again}"
    )


def test_a_low_finding_annotates_and_does_not_block(tmp_path):
    mod = _load_server(tmp_path)
    rev = Reviewer({"a.py": _findings("low")})
    res = _drive(mod, {"a.py": "sha-a"}, rev)
    assert res["verdicts"]["sha-a"] == "FINDINGS", res
    assert not res["blocking"], f"LOW findings annotate, they do not block: {res}"


def test_the_cap_reports_progress_instead_of_deadlocking(tmp_path):
    mod = _load_server(tmp_path)
    blobs = {f"f{i}.py": f"sha-{i}" for i in range(5)}
    rev = Reviewer({})
    res = _drive(mod, blobs, rev, cap=2)
    assert res["calls"] == 2, f"the cap bounds one close's work: {res}"
    assert len(res["remaining"]) == 3, (
        "the blobs left for the next close must be REPORTED, not silently dropped: "
        f"{res}"
    )
    assert len(res["verdicts"]) == 2, res

    # the next pass picks up exactly where this one stopped
    rev.calls.clear()
    nxt = _drive(mod, blobs, rev, cap=2)
    assert nxt["calls"] == 2 and len(nxt["remaining"]) == 1, nxt


def test_a_changed_blob_is_re_reviewed(tmp_path):
    mod = _load_server(tmp_path)
    rev = Reviewer({})
    _drive(mod, {"a.py": "sha-old"}, rev)
    rev.calls.clear()
    res = _drive(mod, {"a.py": "sha-new"}, rev)
    assert rev.calls == ["sha-new"], (
        "the cache is keyed by CONTENT: an edited file is a new blob and must be "
        f"judged again: {rev.calls} / {res}"
    )


def test_only_judged_blobs_are_uncovered(tmp_path):
    """The receipt may claim a blob ONLY when a verdict for that blob exists."""
    mod = _load_server(tmp_path)
    _drive(mod, {"a.py": "sha-a", "b.py": "sha-b"}, Reviewer({}))
    covered = mod._blobs_with_clean_verdict({"a.py": "sha-a", "b.py": "sha-b",
                                             "c.py": "sha-c"})
    assert covered == {"sha-a", "sha-b"}, (
        "an unjudged blob must NOT appear in the receipt's reviewed_blobs — the "
        f"receipt is the authorisation, so it may only name what was judged: {covered}"
    )


def test_the_pre_change_revision_has_no_per_blob_surface(tmp_path):
    """Discrimination: the fix is a new surface, and the baseline must lack it."""
    if SERVER == REPO / "mcp-servers" / "loop-gov-mcp.py":
        print("SKIP: this is the discrimination case — run it with "
              "CORTEX_LOOP_GOV_SERVER=<pre-change copy>")
        return
    src = SERVER.read_text()
    for symbol in ("_review_uncovered_blobs", "_blobs_with_clean_verdict",
                   "blob_reviews"):
        assert symbol not in src, (
            f"the baseline at {SERVER} already carries {symbol} — it is not a "
            "pre-change revision and this comparison proves nothing"
        )


if __name__ == "__main__":
    CASES = (
        test_a_clean_blob_is_reviewed_once_then_cached,
        test_one_non_clean_blob_makes_the_range_not_clean,
        test_a_low_finding_annotates_and_does_not_block,
        test_the_cap_reports_progress_instead_of_deadlocking,
        test_a_changed_blob_is_re_reviewed,
        test_only_judged_blobs_are_uncovered,
        test_the_pre_change_revision_has_no_per_blob_surface,
    )
    failures = 0
    for fn in CASES:
        with tempfile.TemporaryDirectory() as td:
            try:
                fn(Path(td))
                print(f"✅ {fn.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"❌ {fn.__name__}: {exc}")
            except Exception as exc:  # noqa: BLE001 — a missing symbol is a finding too
                failures += 1
                print(f"❌ {fn.__name__}: {type(exc).__name__}: {exc}")
    sys.exit(1 if failures else 0)
