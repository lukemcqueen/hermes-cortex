#!/usr/bin/env python3
"""Regression test: adversarial-verify TOON check works from BOTH locations.

2026-08-24 live test found: the DEPLOYED verifier
(~/.hermes-cortex/scripts/adversarial-verify.py) resolved its lib dir to
~/.hermes-cortex/lib (dirname×2 from scripts/ — one level too shallow),
which does not exist → import toon_parse failed → except:pass silently
disabled the TOON check → malformed TOON produced 0 findings.

The REPO verifier (ops/scripts/quality/) resolved correctly because
dirname×2 lands on ops/scripts/ where lib/ exists. The fix must make the
lib resolution work from both layouts.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
VERIFIER = REPO_ROOT / "ops" / "scripts" / "quality" / "adversarial-verify.py"

MALFORMED = "tasks[2]{id,title}:\n  T-1,hello\n  T-2,world\n"
VALID = "tasks[1]{id,status}:\n  T-1,done\ncount: 1 of 3\n"


def _run_verifier_json(verifier: Path, file_path: Path) -> dict:
    r = subprocess.run(
        [sys.executable, str(verifier), "--file", str(file_path), "--level", "A2", "--json"],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _finding_patterns(data: dict) -> list:
    return [f.get("pattern") for f in data.get("findings", [])]


def test_repo_verifier_flags_malformed_toon():
    """The repo-located verifier must flag TOON with no count line."""
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "bad_toon.py"
        bad.write_text(MALFORMED)
        data = _run_verifier_json(VERIFIER, bad)
        assert "malformed-toon" in _finding_patterns(data), (
            f"repo verifier missed malformed TOON: {data}"
        )


def test_repo_verifier_clean_toon_no_finding():
    """Valid TOON (header + rows + matching count) must NOT be flagged."""
    with tempfile.TemporaryDirectory() as td:
        good = Path(td) / "good_toon.py"
        good.write_text(VALID)
        data = _run_verifier_json(VERIFIER, good)
        assert "malformed-toon" not in _finding_patterns(data), (
            f"valid TOON wrongly flagged: {data}"
        )


def test_deployed_layout_toon_check_works():
    """Simulate the DEPLOYED layout: verifier in scripts/ with lib/ as a
    sibling. Copy both into a temp scripts/ dir and confirm the TOON check
    fires (this is the path that silently broke — the lib path resolved to
    ~/.hermes-cortex/lib, dirname×2 from scripts/, which doesn't exist)."""
    with tempfile.TemporaryDirectory() as td:
        scripts = Path(td) / "scripts"
        lib = scripts / "lib"
        lib.mkdir(parents=True)
        verifier_copy = scripts / "adversarial-verify.py"
        verifier_copy.write_text(VERIFIER.read_text())
        src_lib = REPO_ROOT / "ops" / "scripts" / "lib" / "toon_parse.py"
        (lib / "toon_parse.py").write_text(src_lib.read_text())

        bad = Path(td) / "bad_toon.py"
        bad.write_text(MALFORMED)
        data = _run_verifier_json(verifier_copy, bad)
        assert "malformed-toon" in _finding_patterns(data), (
            f"deployed-layout verifier missed malformed TOON: {data}"
        )
