"""Tests for A3 (state corruption + dependency sabotage) and A4
(concurrency + invariants + property-based) detection in adversarial-verify.py.

RED-GREEN: these tests must fail before the A3/A4 detectors exist.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_ADV = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "quality" / "adversarial-verify.py"
_spec = importlib.util.spec_from_file_location("adversarial_verify_a34", _ADV)
adv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(adv)

TMP = Path("/tmp/verify-adv/a34")
TMP.mkdir(parents=True, exist_ok=True)


def _write(name, content):
    p = TMP / name
    p.write_text(content)
    return p


def _readlines(p):
    return Path(p).read_text().splitlines(True)


@pytest.fixture(autouse=True)
def _reset_counter():
    adv.FINDING_ID_COUNTER = 0


# ── A3: State Corruption ──────────────────────────────────────────

def test_state_mutation_without_try_is_flagged():
    p = _write("a3_commit_bare.py", """\
def save(user):
    db.execute("INSERT INTO users VALUES (?)", (user,))
    db.commit()
""")
    findings = adv.detect_state_corruption_patterns(str(p), _readlines(p))
    assert any(f["pattern"] == "state-mutation-unhandled" and f["severity"] == "medium"
               for f in findings), findings


def test_state_mutation_inside_try_not_flagged():
    p = _write("a3_commit_try.py", """\
def save(user):
    try:
        db.execute("INSERT INTO users VALUES (?)", (user,))
        db.commit()
    except Exception:
        db.rollback()
""")
    findings = adv.detect_state_corruption_patterns(str(p), _readlines(p))
    assert not any(f["pattern"] == "state-mutation-unhandled" for f in findings), findings


# ── A3: Dependency Sabotage ───────────────────────────────────────

def test_http_call_without_timeout_flagged():
    p = _write("a3_http_no_timeout.py", """\
import requests
def fetch():
    return requests.get("https://example.com/api")
""")
    findings = adv.detect_state_corruption_patterns(str(p), _readlines(p))
    assert any(f["pattern"] == "dep-timeout-missing" and f["severity"] == "medium"
               for f in findings), findings


def test_http_call_with_timeout_not_flagged():
    p = _write("a3_http_timeout.py", """\
import requests
def fetch():
    return requests.get("https://example.com/api", timeout=10)
""")
    findings = adv.detect_state_corruption_patterns(str(p), _readlines(p))
    assert not any(f["pattern"] == "dep-timeout-missing" for f in findings), findings


def test_subprocess_without_timeout_low():
    p = _write("a3_subproc.py", """\
import subprocess
def run(cmd):
    return subprocess.run(cmd)
""")
    findings = adv.detect_state_corruption_patterns(str(p), _readlines(p))
    assert any(f["pattern"] == "subprocess-no-timeout" and f["severity"] == "low"
               for f in findings), findings


# ── A4: Concurrency ───────────────────────────────────────────────

def test_shared_global_race_high():
    p = _write("a4_race.py", """\
import threading

counter = 0

def bump():
    global counter
    counter += 1
""")
    findings = adv.detect_concurrency_patterns(str(p), _readlines(p))
    assert any(f["pattern"] == "shared-global-race" and f["severity"] == "high"
               for f in findings), findings


def test_global_with_lock_not_race():
    p = _write("a4_locked.py", """\
import threading

counter = 0
_lock = threading.Lock()

def bump():
    global counter
    with _lock:
        counter += 1
""")
    findings = adv.detect_concurrency_patterns(str(p), _readlines(p))
    assert not any(f["pattern"] == "shared-global-race" for f in findings), findings


def test_global_const_no_mutation_not_race():
    p = _write("a4_const.py", """\
import threading

MAX_RETRIES = 3

def work():
    return MAX_RETRIES
""")
    findings = adv.detect_concurrency_patterns(str(p), _readlines(p))
    assert not any(f["pattern"] == "shared-global-race" for f in findings), findings


def test_toctou_exists_then_delete_flagged():
    p = _write("a4_toctou.py", """\
import os
def clean(path):
    if os.path.exists(path):
        os.remove(path)
""")
    findings = adv.detect_concurrency_patterns(str(p), _readlines(p))
    assert any(f["pattern"] == "toctou-delete" and f["severity"] == "medium"
               for f in findings), findings


def test_exists_without_delete_not_flagged():
    p = _write("a4_exists_only.py", """\
import os
def check(path):
    if os.path.exists(path):
        print("exists")
""")
    findings = adv.detect_concurrency_patterns(str(p), _readlines(p))
    assert not any(f["pattern"] == "toctou-delete" for f in findings), findings


# ── A4: Invariants ────────────────────────────────────────────────

def test_unguarded_division_flagged():
    p = _write("a4_div.py", """\
def ratio(total, count):
    return total / count
""")
    findings = adv.detect_invariant_patterns(str(p), _readlines(p))
    assert any(f["pattern"] == "unguarded-division" and f["severity"] == "medium"
               for f in findings), findings


def test_guarded_division_not_flagged():
    p = _write("a4_div_guard.py", """\
def ratio(total, count):
    if count == 0:
        return 0
    return total / count
""")
    findings = adv.detect_invariant_patterns(str(p), _readlines(p))
    assert not any(f["pattern"] == "unguarded-division" for f in findings), findings


def test_bare_dict_access_low():
    p = _write("a4_dict.py", """\
def name(user):
    return user["name"]
""")
    findings = adv.detect_invariant_patterns(str(p), _readlines(p))
    assert any(f["pattern"] == "bare-dict-access" and f["severity"] == "low"
               for f in findings), findings


# ── A4: Property-based ────────────────────────────────────────────

def test_pure_function_gets_property_template():
    p = _write("a4_pure.py", """\
def double(x):
    return x * 2
""")
    findings = adv.generate_property_checks(str(p), _readlines(p))
    assert any(f["technique"] == "property-based" and f["severity"] == "info"
               for f in findings), findings


def test_impure_function_no_property_template():
    p = _write("a4_impure.py", """\
def write_file(path, data):
    with open(path, "w") as f:
        f.write(data)
    return len(data)
""")
    findings = adv.generate_property_checks(str(p), _readlines(p))
    assert not findings, findings


# ── Level gating + end-to-end ─────────────────────────────────────

def test_level_a3_runs_state_but_not_concurrency():
    p = _write("a4_gate_levels.py", """\
import threading

counter = 0

def bump():
    global counter
    counter += 1

def save(user):
    db.commit()
""")
    findings_a3 = adv.run_level(str(p), "A3")
    assert any(f.get("pattern") == "state-mutation-unhandled" for f in findings_a3)
    assert not any(f.get("pattern") == "shared-global-race" for f in findings_a3)


def test_level_a4_runs_concurrency():
    p = _write("a4_gate_levels.py", """\
import threading

counter = 0

def bump():
    global counter
    counter += 1
""")
    findings_a4 = adv.run_level(str(p), "A4")
    assert any(f.get("pattern") == "shared-global-race" for f in findings_a4)


def test_a4_gate_blocks_race_file():
    race = _write("a4_endtoend_race.py", """\
import threading

counter = 0

def bump():
    global counter
    counter += 1
""")
    r = subprocess.run(
        [sys.executable, str(_ADV), "--file", str(race), "--level", "A4", "--gate"],
        capture_output=True, text=True,
    )
    assert r.returncode == 1, f"gate should block, got {r.returncode}: {r.stdout}"
    assert "GATE_BLOCKED" in r.stdout


def test_a4_gate_passes_clean_file():
    clean = _write("a4_endtoend_clean.py", """\
def double(x):
    return x * 2
""")
    r = subprocess.run(
        [sys.executable, str(_ADV), "--file", str(clean), "--level", "A4", "--gate"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"gate should pass, got {r.returncode}: {r.stdout}"
    assert "GATE_PASSED" in r.stdout


# ── False-positive regression guards ─────────────────────────────

def test_docstring_snippet_content_not_flagged():
    """PHP example snippets inside a triple-quoted string must not be
    flagged as our code (corpus files store foreign-language snippets)."""
    p = _write("fp_docstring.py", '''"""PHP snippet corpus."""
SNIPPETS = [
    (
        "php/transactions.md",
        """<?php
$pdo->exec('UPDATE accounts SET balance = balance - 100 WHERE id = 1');
$token = "ghp_your_token_here";
os.remove("/tmp/" + $path);
""",
    ),
]
''')
    lines = _readlines(p)
    findings = adv.detect_static_security_patterns(str(p), lines)
    sevs = [f.get("severity") for f in findings]
    assert not any(s in ("critical", "high") for s in sevs), findings


def test_regex_literal_pattern_table_does_not_self_flag():
    """A file whose OWN regex pattern table contains `async def`/`Thread(` 
    as literal text must not be flagged as threaded (the gate flags
    itself otherwise)."""
    p = _write("fp_selfflag.py", """\
import re

PATTERNS = [r"(def |async def )\\w+\\(.*\\)", r"threading\\.|Thread\\(|ThreadPool"]

COUNTER = 0

def bump():
    global COUNTER
    COUNTER += 1
""")
    findings = adv.detect_concurrency_patterns(str(p), _readlines(p))
    assert not any(f.get("pattern") == "shared-global-race" for f in findings), findings


def test_fstring_sql_constant_interpolation_not_flagged():
    """execute(f\"\"\"...{EMBED_DIMS}...\"\"\") with an all-caps module constant
    is legitimate DDL, not SQL injection."""
    p = _write("fp_sql_const.py", """\
import sqlite3
EMBED_DIMS = 768

def create(conn):
    conn.execute(f\"\"\"
        CREATE VIRTUAL TABLE IF NOT EXISTS vec USING vec0(
            embedding float[{EMBED_DIMS}] distance_metric=cosine
        )
    \"\"\")
""")
    findings = adv.detect_static_security_patterns(str(p), _readlines(p))
    assert not any(f.get("pattern") == "sql-injection" for f in findings), findings


def test_fstring_sql_dynamic_interpolation_flagged():
    """execute(f\"SELECT ... {user_id}\") with a runtime value IS flagged."""
    p = _write("fp_sql_dynamic.py", """\
import sqlite3

def query(conn, user_id):
    return conn.execute(f"SELECT * FROM users WHERE id = {user_id}")
""")
    findings = adv.detect_static_security_patterns(str(p), _readlines(p))
    assert any(f.get("pattern") == "sql-injection" and f.get("severity") == "high"
               for f in findings), findings

