#!/usr/bin/env python3
"""Regression tests: gates are TOON-aware (AXI Phase 0, QA showstopper)."""
import json
import os
import pathlib
import shutil
import subprocess
import tempfile

_REPO = pathlib.Path(__file__).resolve().parent.parent
_DETECTOR = _REPO / "ops" / "scripts" / "secret-leak-detector.sh"
_VERIFIER = _REPO / "ops" / "scripts" / "quality" / "adversarial-verify.py"
_GOLDEN = _REPO / "tests" / "fixtures" / "toon_golden.txt"

_TOON_SAMPLE = """tasks[2]{id,email,domain,path}:
  T-1,admin@client-domain.com,example.org,/home/user/data
  T-2,dev@example.com,test.local,/opt/cortex/logs
count: 2 of 10
"""

# Control domain is runtime-built so the file never contains a literal
# non-placeholder domain (PII gate: test fixtures are runtime-constructed).
_DOM = "real-client-xyz.com"
_FREE_TEXT_SAMPLE = f"contact admin@{_DOM} at https://{_DOM} now\n"


def _init_repo_with(content: str, filename: str = "sample.txt") -> str:
    repo = tempfile.mkdtemp(prefix="toon-gate-")
    subprocess.run(["git", "init", "-q", repo], check=True)
    pathlib.Path(repo, filename).write_text(content)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    return repo


def test_detector_ignores_toon_rows():
    repo = _init_repo_with(_TOON_SAMPLE)
    try:
        r = subprocess.run(["bash", str(_DETECTOR)], cwd=repo,
                           capture_output=True, text=True, timeout=60)
        assert "PII" not in r.stdout, r.stdout
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_detector_still_flags_free_text():
    repo = _init_repo_with(_FREE_TEXT_SAMPLE)
    try:
        r = subprocess.run(["bash", str(_DETECTOR)], cwd=repo,
                           capture_output=True, text=True, timeout=60)
        assert "PII" in r.stdout, r.stdout
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_verifier_flags_malformed_toon():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("# x\n" + "tasks[2]{id,title}:\n  T-1,hello\n  T-2,world\n")
        path = f.name
    try:
        r = subprocess.run(
            ["python3", str(_VERIFIER), "--file", path, "--level", "A2", "--json"],
            capture_output=True, text=True, timeout=60)
        out = json.loads(r.stdout)
        toon = [x for x in out["findings"] if x.get("technique") == "toon-conformance"]
        assert len(toon) == 1, out["findings"]
        assert toon[0]["pattern"] == "malformed-toon"
    finally:
        os.unlink(path)


def test_verifier_accepts_golden_toon():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("# golden\n" + _GOLDEN.read_text())
        path = f.name
    try:
        r = subprocess.run(
            ["python3", str(_VERIFIER), "--file", path, "--level", "A2", "--json"],
            capture_output=True, text=True, timeout=60)
        out = json.loads(r.stdout)
        toon = [x for x in out["findings"] if x.get("technique") == "toon-conformance"]
        assert toon == [], out["findings"]
    finally:
        os.unlink(path)
