#!/usr/bin/env python3
"""The reflexion gate's refusal must NAME the fix for an automated session.

Row 482de205: `orch-task-morning-pass` (cron `f6694d02d29c`) could not commit its own
evidence because the gate answered `NOT-LOADED reflexion-check`. The cause is a
config one, not a gate one: that job carries an explicit per-job
`enabled_toolsets` allowlist (`['terminal','web','file']`) that omits the
`skills` toolset, so `skill_view` is never registered in its session and the
enforcer hook never records a load. The sibling `orch-bus-worker` job has no
allowlist and DOES satisfy the gate.

This test pins the DIAGNOSTIC half: when the gate refuses a session whose cron
job provably cannot present the tool, it must say so — naming the job and the
fix — instead of repeating "load the skill" to a session that cannot.

HERMETIC: the checker is copied into a temp tree with a STUB store module (the
same seam `tests/test-reflexion-gate-repoint.sh` uses), and the cron store is a
temp `jobs.json` under a temp HOME. No live DB, no live governance state.

The gate's DECISIONS are unchanged: 0 loaded / 1 not loaded / 2 usage / 3 store
unreachable. Only the message on the refusal path gains the diagnosis.

Run: <venv>/bin/python -m pytest tests/test_reflexion_check_cron_diagnostic.py -q
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CHECKER = REPO / "ops" / "scripts" / "hc-reflexion-check.py"

JOB_ID = "f6694d02d29c"
CRON_SESSION = f"cron_{JOB_ID}_20261026_073743"

STUB_STORE = '''
class _Sessions:
    def loaded_skill(self, skill, _x="", session_key=None):
        return {loaded}


class Store:
    def __init__(self, *a, **k):
        self.sessions = _Sessions()

    def available(self):
        return True
'''


def _load_checker_module():
    """The REPO copy, as a module (for the helper's own unit cases)."""
    spec = importlib.util.spec_from_file_location("hc_reflexion_check_under_test", CHECKER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sandbox(tmp_path: Path, *, jobs, loaded: bool, with_store: bool = True) -> tuple[Path, Path]:
    """Return (checker_copy, home) for one hermetic run."""
    root = tmp_path / "root"
    (root / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
    checker = root / "ops" / "scripts" / "hc-reflexion-check.py"
    shutil.copy2(CHECKER, checker)
    if with_store:
        store_dir = root / "ops" / "services" / "mycortex-mem"
        store_dir.mkdir(parents=True, exist_ok=True)
        (store_dir / "store.py").write_text(STUB_STORE.format(loaded=loaded))
    home = tmp_path / "home"
    (home / ".hermes" / "cron").mkdir(parents=True, exist_ok=True)
    if jobs is not None:
        (home / ".hermes" / "cron" / "jobs.json").write_text(json.dumps(jobs))
    return checker, home


def _run(checker: Path, home: Path, session: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(checker), "--session", session],
        capture_output=True, text=True,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        timeout=120,
    )


def _job(name: str, toolsets):
    return {"id": JOB_ID, "name": name, "enabled_toolsets": toolsets, "prompt": "p"}


# ── AC1: the exact live shape refuses (rc 1) and names the job + the fix ──────

def test_cron_session_without_skills_toolset_names_the_job_and_the_fix(tmp_path):
    checker, home = _sandbox(
        tmp_path, jobs={"jobs": [_job("orch-task-morning-pass", ["terminal", "web", "file"])]},
        loaded=False)
    r = _run(checker, home, CRON_SESSION)
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "NOT-LOADED" in out
    assert JOB_ID in out, "the refusal must name the offending job id"
    assert "enabled_toolsets" in out, "the refusal must name the config field"
    assert "skills" in out, "the refusal must name the toolset to add"


# ── AC2: a job that CAN present the tool gets no config hint ─────────────────

def test_cron_session_with_skills_toolset_gets_no_config_hint(tmp_path):
    checker, home = _sandbox(
        tmp_path, jobs={"jobs": [_job("orch-task-morning-pass", ["terminal", "web", "file", "skills"])]},
        loaded=False)
    r = _run(checker, home, CRON_SESSION)
    out = r.stdout + r.stderr
    assert r.returncode == 1  # still refuses — a load is still absent
    assert "enabled_toolsets" not in out


def test_cron_session_with_no_allowlist_gets_no_config_hint(tmp_path):
    """enabled_toolsets=None => the job follows platform_toolsets.cron; we cannot claim a gap."""
    checker, home = _sandbox(tmp_path, jobs={"jobs": [_job("orch-bus-worker", None)]}, loaded=False)
    r = _run(checker, home, CRON_SESSION)
    out = r.stdout + r.stderr
    assert r.returncode == 1
    assert "enabled_toolsets" not in out


def test_interactive_session_is_unchanged(tmp_path):
    checker, home = _sandbox(tmp_path, jobs={"jobs": [_job("x", [])]}, loaded=False)
    r = _run(checker, home, "interactive-session-abc")
    out = r.stdout + r.stderr
    assert r.returncode == 1
    assert "NOT-LOADED" in out
    assert "enabled_toolsets" not in out and JOB_ID not in out


# ── AC3: unknown/absent/unreadable cron store => no speculation, rc unchanged ─

@pytest.mark.parametrize("jobs", [None, {"jobs": []}, {"jobs": "not-a-list"}])
def test_unknown_job_or_broken_store_never_speculates(tmp_path, jobs):
    checker, home = _sandbox(tmp_path, jobs=jobs, loaded=False)
    r = _run(checker, home, CRON_SESSION)
    out = r.stdout + r.stderr
    assert r.returncode == 1
    assert "Traceback" not in out
    assert "enabled_toolsets" not in out


# ── AC4: LOADED sessions never see the diagnostic ───────────────────────────

def test_loaded_session_passes_and_gets_no_diagnostic(tmp_path):
    checker, home = _sandbox(
        tmp_path, jobs={"jobs": [_job("orch-task-morning-pass", ["terminal"])]}, loaded=True)
    r = _run(checker, home, CRON_SESSION)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert "LOADED" in out
    assert "enabled_toolsets" not in out


# ── AC5: the store-unreachable path stays rc 3 and ONE line ─────────────────

def test_store_unreachable_stays_rc3_single_line(tmp_path):
    checker, home = _sandbox(
        tmp_path, jobs={"jobs": [_job("orch-task-morning-pass", ["terminal"])]},
        loaded=False, with_store=False)
    r = _run(checker, home, CRON_SESSION)
    out = (r.stdout + r.stderr).strip()
    assert r.returncode == 3, out
    assert len(out.splitlines()) == 1, out
    assert "enabled_toolsets" not in out


# ── AC6: the helper is pure and positive-evidence-only ──────────────────────

def test_helper_requires_positive_evidence(tmp_path):
    hint = getattr(_load_checker_module(), "automated_session_job_hint", None)
    assert hint is not None, "automated_session_job_hint is missing from hc-reflexion-check.py"

    jobs = tmp_path / "jobs.json"
    jobs.write_text(json.dumps({"jobs": [_job("orch-task-morning-pass", ["terminal", "web", "file"])]}))

    assert hint("interactive-abc", jobs_file=jobs) == []
    assert hint("cron_", jobs_file=jobs) == []
    assert hint("cron_bbbbbbbbbbbb_20261026_000000", jobs_file=jobs) == []      # unknown job
    assert hint("cron_", jobs_file=tmp_path / "missing.json") == []
    named = hint(CRON_SESSION, jobs_file=jobs)
    assert named and any(JOB_ID in ln for ln in named)
