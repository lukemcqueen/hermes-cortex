"""Tests for static OWASP pattern detection in adversarial-verify.py.

RED-GREEN: these tests must fail before the static detector exists.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_ADV = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "quality" / "adversarial-verify.py"
_spec = importlib.util.spec_from_file_location("adversarial_verify", _ADV)
adv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(adv)

VULN = "/tmp/verify-adv/vuln.py"
CLEAN = "/tmp/verify-adv/clean.py"


def _write(path, content):
    Path(path).write_text(content)
    return path


@pytest.fixture(autouse=True)
def _reset_counter():
    adv.FINDING_ID_COUNTER = 0


def test_detects_command_injection_os_system():
    p = _write("/tmp/verify-adv/t_os_system.py", 'import os\ndef ping(h):\n    os.system("ping -c 1 " + h)\n')  # adversarial-ignore: command-injection — test fixture deliberately contains the vuln
    findings = adv.detect_static_security_patterns(p, Path(p).read_text().splitlines(True))
    sevs = {f["severity"] for f in findings}
    assert "critical" in sevs or "high" in sevs


def test_detects_shell_true_rce():
    p = _write("/tmp/verify-adv/t_shell_true.py", 'import subprocess\ndef up(f):\n    subprocess.call("tar -x " + f, shell=True)\n')  # adversarial-ignore: shell-true-rce — test fixture deliberately contains the vuln
    findings = adv.detect_static_security_patterns(p, Path(p).read_text().splitlines(True))
    assert any(f["severity"] in ("critical", "high") for f in findings)


def test_detects_eval_untrusted():
    p = _write("/tmp/verify-adv/t_eval.py", 'def r(c):\n    return eval(c)\n')  # adversarial-ignore: dangerous-eval — test fixture deliberately contains the vuln
    findings = adv.detect_static_security_patterns(p, Path(p).read_text().splitlines(True))
    assert any(f["severity"] in ("critical", "high") for f in findings)


def test_detects_pickle_loads():
    p = _write("/tmp/verify-adv/t_pickle.py", 'import pickle\ndef ld(b):\n    return pickle.loads(b)\n')  # adversarial-ignore: unsafe-deserialization — test fixture deliberately contains the vuln
    findings = adv.detect_static_security_patterns(p, Path(p).read_text().splitlines(True))
    assert any(f["severity"] in ("critical", "high") for f in findings)


def test_detects_sql_injection():
    p = _write("/tmp/verify-adv/t_sqli.py", 'import sqlite3\ndef q(uid):\n    return sqlite3.connect("a.db").execute("SELECT * FROM u WHERE id=" + uid)\n')  # adversarial-ignore: sql-injection — test fixture deliberately contains the vuln
    findings = adv.detect_static_security_patterns(p, Path(p).read_text().splitlines(True))
    assert any(f["severity"] in ("critical", "high") for f in findings)


def test_detects_arbitrary_file_delete():
    p = _write("/tmp/verify-adv/t_rm.py", 'import os\ndef wipe(path):\n    os.remove("/srv/data/" + path)\n')  # adversarial-ignore: arbitrary-delete — test fixture deliberately contains the vuln
    findings = adv.detect_static_security_patterns(p, Path(p).read_text().splitlines(True))
    assert any(f["severity"] in ("critical", "high") for f in findings)


def test_literal_file_delete_not_flagged():
    p = _write("/tmp/verify-adv/t_rm_lit.py", 'import os\ndef wipe():\n    os.remove("config.old")\n')
    findings = adv.detect_static_security_patterns(p, Path(p).read_text().splitlines(True))
    assert not any(f["severity"] in ("critical", "high") for f in findings)


def test_clean_file_no_blockers():
    findings = adv.detect_static_security_patterns(CLEAN, Path(CLEAN).read_text().splitlines(True))
    assert not any(f["severity"] in ("critical", "high") for f in findings)


def test_vuln_file_gate_blocks():
    """End-to-end: the A2 gate must BLOCK the vulnerable file."""
    import subprocess
    r = subprocess.run(
        [sys.executable, str(_ADV), "--file", VULN, "--level", "A2", "--gate"],
        capture_output=True, text=True,
    )
    assert r.returncode == 1, f"gate should block, got {r.returncode}: {r.stdout}"
    assert "GATE_BLOCKED" in r.stdout


def test_clean_file_gate_passes():
    import subprocess
    r = subprocess.run(
        [sys.executable, str(_ADV), "--file", CLEAN, "--level", "A2", "--gate"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"gate should pass, got {r.returncode}: {r.stdout}"
