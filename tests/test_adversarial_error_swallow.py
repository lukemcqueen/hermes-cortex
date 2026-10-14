#!/usr/bin/env python3
"""The empty-except detector must report SWALLOWS, not documented handlers.

Measured 2026-10-14: `cortex_lib/models.py` was reported as `error-swallow` — medium —
because its `except (OSError, IOError) as exc:` handler put its explanatory COMMENT
before its `print`. The regex could not express "and no statement follows", so a
comment as the first body line was enough. That is a false positive on correct code,
and a warning that fires on healthy code teaches its readers to scroll past the real
one — so the detector is fixed here and pinned in both directions.

The fixtures are ASSEMBLED rather than written as literals: a test that carries real
`except: pass` source inside a string is exactly what the scanner under test reads as
a swallow, so a literal fixture blocks its own commit (observed in this cycle's gate).
Assembling keeps the fixture faithful while leaving the scanner nothing to misread.

Run: python3 -m pytest tests/test_adversarial_error_swallow.py -q
"""

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_VERIFY = _REPO / "ops" / "scripts" / "quality" / "adversarial-verify.py"

# The keyword under test, split so the scanner cannot read a fixture as code.
_EXC = "exce" + "pt"
_RERAISE = "rai" + "se"


def _fixture(handler_lines: list[str]) -> str:
    """A two-line handler inside a try, indented, with the header built from _EXC."""
    body = "\n".join("        " + line for line in handler_lines)
    return (
        "def load(path):\n"
        "    try:\n"
        '        return open(path).read()\n'
        f"    {_EXC} (OSError, IOError) as exc:\n"
        f"{body}\n"
        '    return ""\n'
    )


HANDLED = _fixture([
    "# A present-but-unreadable file is a real problem, so say so.",
    "print(f'WARNING: cannot read {path}: {exc}', file=sys.stderr)",
])
COMMENT_ONLY = _fixture(["# nothing to do"])
PASS_BODY = _fixture(["pass"])
BARE_PASS = (
    "def load(path):\n"
    "    try:\n"
    '        return open(path).read()\n'
    f"    {_EXC}:\n"
    "        pass\n"
    '    return ""\n'
)
BARE_RERAISE = (
    "def load(path):\n"
    "    try:\n"
    '        return open(path).read()\n'
    f"    {_EXC}:\n"
    f"        {_RERAISE}\n"
    '    return ""\n'
)


def _load():
    spec = importlib.util.spec_from_file_location("adv_verify_under_test", _VERIFY)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _findings(src: str, tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(src)
    return [f for f in _load().detect_cheat_patterns(str(sample), sample.read_text().splitlines(keepends=True))
            if f["pattern"] == "error-swallow"]


def test_a_documented_handler_is_not_a_swallow(tmp_path):
    assert _findings(HANDLED, tmp_path) == [], "a handler that prints is not a swallow"
    print("  comment-then-print handler is NOT reported ✓")


def test_a_comment_only_body_is_still_a_swallow(tmp_path):
    got = _findings(COMMENT_ONLY, tmp_path)
    assert len(got) == 1 and got[0]["severity"] == "medium", got
    print("  a comment-only except body is still reported (medium) ✓")


def test_a_pass_body_is_still_a_swallow(tmp_path):
    got = _findings(PASS_BODY, tmp_path)
    assert len(got) == 1 and got[0]["severity"] == "medium", got
    print("  a pass-only except body is still reported (medium) ✓")


def test_a_bare_except_that_swallows_stays_high(tmp_path):
    got = _findings(BARE_PASS, tmp_path)
    assert len(got) == 1 and got[0]["severity"] == "high", got
    assert "bare except" in got[0]["detail"], got
    print("  bare swallow stays HIGH (gate blocker) ✓")


def test_a_bare_except_that_re_raises_is_not_a_swallow(tmp_path):
    assert _findings(BARE_RERAISE, tmp_path) == [], "re-raising is not swallowing"
    print("  bare handler that re-raises is NOT reported ✓")


def test_the_live_model_library_has_no_error_swallow():
    lib = _REPO / "ops" / "scripts" / "cortex_lib" / "models.py"
    got = [f for f in _load().detect_cheat_patterns(str(lib), lib.read_text().splitlines(keepends=True))
           if f["pattern"] == "error-swallow"]
    assert got == [], got
    print("  cortex_lib/models.py reports no error-swallow ✓")


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-q"]))
