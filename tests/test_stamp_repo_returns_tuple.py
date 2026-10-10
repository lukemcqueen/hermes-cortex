#!/usr/bin/env python3
"""Regression test: _stamp_repo_into_payload returns a (dict, str) tuple in
every branch.

ADV-4907-1: the close reviewer read an unrelated `return out` (in `discover_tools`)
as this function returning a bare dict. Every branch actually returns a two-tuple
(the caller in main() unpacks `payload, _stamp_status = ...`). This drives the
REAL function through both the explicit-repo and no-repo paths and asserts the
unpack, so a future bare-dict return fails loudly.
"""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOOP_GOV = REPO / "ops" / "scripts" / "loop-gov.py"


def _load():
    spec = importlib.util.spec_from_file_location("loop_gov_cli_tuple", LOOP_GOV)
    assert spec and spec.loader, "cannot load loop-gov.py"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_explicit_repo_returns_a_tuple():
    mod = _load()
    out, status = mod._stamp_repo_into_payload(
        {"task_id": "t", "repo_path": "/x", "repo_slug": "x"}, Path("/"))
    assert isinstance(out, dict) and isinstance(status, str), (
        f"expected (dict, str), got {type(out).__name__}, {type(status).__name__}")
    assert status == "stamped"


def test_no_repo_path_returns_a_tuple():
    mod = _load()
    tmp = Path(tempfile.mkdtemp(prefix="stamp-tuple-norepo-"))
    out, status = mod._stamp_repo_into_payload({"task_id": "t"}, tmp)
    assert isinstance(out, dict) and isinstance(status, str), (
        f"expected (dict, str), got {type(out).__name__}, {type(status).__name__}")
    assert status in ("stamped", "no-repo", "unexpected")


if __name__ == "__main__":
    test_explicit_repo_returns_a_tuple()
    test_no_repo_path_returns_a_tuple()
    print("PASS (2): _stamp_repo_into_payload returns (dict, str) tuples")