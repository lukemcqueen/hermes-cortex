#!/usr/bin/env python3
"""Verifies `_stamp_repo_into_payload` returns (dict, str) tuples in every
branch, addressing ADV-4907-1 (which misread an unrelated `return out` in
`discover_tools` as this function returning a bare dict).

Also a hermetic regression: the function must never return a bare dict, or the
caller in main() (`payload, _stamp_status = _stamp_repo_into_payload(...)`)
would raise on unpack.
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

_ensure = importlib.util.spec_from_file_location(
    "loop_gov_cli_verify", "ops/scripts/loop-gov.py")
if _ensure is None or _ensure.loader is None:
    print("COULD NOT VERIFY: cannot load ops/scripts/loop-gov.py", file=sys.stderr)
    raise SystemExit(3)
mod = importlib.util.module_from_spec(_ensure)
_ensure.loader.exec_module(mod)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="stamp-verify-"))
    cases = [
        {"task_id": "t"},                                     # no repo -> stamp probe
        {"task_id": "t", "repo_path": "/x", "repo_slug": "x"},  # explicit -> stamped
    ]
    for payload in cases:
        result = mod._stamp_repo_into_payload(dict(payload), tmp)
        assert isinstance(result, tuple), f"not a tuple: {result!r}"
        assert len(result) == 2, f"not a 2-tuple: {result!r}"
        d, status = result
        assert isinstance(d, dict) and isinstance(status, str), (
            f"expected (dict, str), got {type(d).__name__}, {type(status).__name__}")
        assert status in ("stamped", "no-repo", "unexpected"), status
    print("RESULT: verified _stamp_repo_into_payload returns (dict, str) in all cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())