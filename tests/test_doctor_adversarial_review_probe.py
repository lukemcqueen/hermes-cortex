#!/usr/bin/env python3
"""Tests for the doctor's check_adversarial_review import probe robustness.

2026-09-28 (Titus host): the doctor import-probes loop-gov-mcp.py in-process
(check_adversarial_review). loop-gov-mcp.py sys.exit(1)s at import when the
probing interpreter lacks the `mcp` package (Titus runs the doctor under
/usr/local/bin/python3 — no mcp). sys.exit raises SystemExit, which the
check's `except Exception` does NOT catch — SystemExit derives from
BaseException — so it killed the whole doctor before the report printed.

The probe must NEVER kill the doctor:
  * interpreter without `mcp`  -> WARN (environment problem, not code rot)
  * helper functions missing   -> FAIL (code rot — original detection kept)
  * ImportError at import      -> FAIL (original detection kept)
"""
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
MANAGE = REPO_ROOT / "ops" / "scripts" / "manage"


def _load_package():
    sys.path.insert(0, str(MANAGE))
    import cortex_doctor.checks as checks
    import cortex_doctor.results as results
    return checks, results


def _find_result(res, name):
    for r in res.checks:
        if r.get("name") == name:
            return r
    return None


def _write_mcp_stub(scripts_home: Path, body: str) -> None:
    """Deploy a loop-gov-mcp.py stub at the deployed-tools path the check reads."""
    tools = scripts_home / "tools" / "loop-governance"
    tools.mkdir(parents=True, exist_ok=True)
    (tools / "loop-gov-mcp.py").write_text(body)


# Mimics loop-gov-mcp.py's real mcp-package guard (lines ~103-113) as it
# behaves on Titus's host: the probing interpreter LACKS mcp, so the guard
# fires — print to stderr, then sys.exit(1). Unconditional here because the
# CI interpreter may have mcp; on Titus's /usr/local/bin/python3 it fires
# for real. The point under test: SystemExit must not escape the check.
MCP_GUARD_STUB = (
    "import sys\n"
    "print('[mcp-server] ERROR: Required mcp package not found.', file=sys.stderr)\n"
    "sys.exit(1)\n"
)


def test_import_refusal_is_warn_not_crash():
    """A loop-gov-mcp.py that sys.exit(1)s at import (no mcp SDK) must not
    kill the doctor — the check reports WARN and returns normally."""
    checks, results = _load_package()
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        _write_mcp_stub(home, MCP_GUARD_STUB)
        old_home = checks.CORTEX_HOME
        checks.CORTEX_HOME = home
        try:
            res = results.Results()
            checks.check_adversarial_review(res)  # must NOT raise SystemExit
            entry = _find_result(res, "Adversarial review gate")
            assert entry is not None, "check produced no 'Adversarial review gate' result"
            assert entry["status"] == "WARN", (
                f"expected WARN for interpreter-without-mcp, got: {entry}"
            )
        finally:
            checks.CORTEX_HOME = old_home


def test_missing_helpers_still_fails():
    """Code-rot detection must survive the fix: a server that imports but
    lacks the review helpers is still a FAIL."""
    checks, results = _load_package()
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        _write_mcp_stub(home, "IMPORTED = True\n")  # imports fine, no helpers
        old_home = checks.CORTEX_HOME
        checks.CORTEX_HOME = home
        try:
            res = results.Results()
            checks.check_adversarial_review(res)
            entry = _find_result(res, "Adversarial review gate")
            assert entry is not None, "check produced no 'Adversarial review gate' result"
            assert entry["status"] == "FAIL", f"expected FAIL for missing helpers, got: {entry}"
            assert "_adversarial_review_gate" in entry.get("detail", "")
        finally:
            checks.CORTEX_HOME = old_home


def test_import_error_still_fails():
    """A SyntaxError/ImportError during the probe is still a FAIL, not a crash."""
    checks, results = _load_package()
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        _write_mcp_stub(home, "raise SyntaxError('broken server')\n")
        old_home = checks.CORTEX_HOME
        checks.CORTEX_HOME = home
        try:
            res = results.Results()
            checks.check_adversarial_review(res)
            entry = _find_result(res, "Adversarial review gate")
            assert entry is not None, "check produced no 'Adversarial review gate' result"
            assert entry["status"] == "FAIL", f"expected FAIL for import error, got: {entry}"
        finally:
            checks.CORTEX_HOME = old_home
