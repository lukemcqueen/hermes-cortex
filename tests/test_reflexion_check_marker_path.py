#!/usr/bin/env python3
"""The reflexion gate's artefact-marker path (option 2) — fail-closed edges.

Row 482de205: an automated session whose cron job carries an explicit
`enabled_toolsets` allowlist WITHOUT the `skills` toolset can never record a
`skill_view` load, so the gate was structurally unsatisfiable for that job. The
fix (option 2 of docs/evidence/briefings/BLOCKER-reflexion-gate-skill_view-2026-10-16.md)
lets such a session present a COMMITTED, session-keyed, non-trivial reflexion-answer
marker under `<repo>/docs/evidence/briefings/` instead of the impossible tool row.

This test pins the CONTRACT of `automated_reflexion_marker`:

  * reachable ONLY with positive evidence (automated session + explicit allowlist
    WITHOUT `skills`) AND a git checkout AND a marker with the required header
    AND >= REFLEXION_MARKER_MIN_BYTES;
  * every other case stays fail-closed (rc 1).

HERMETIC: the checker is copied into a temp tree that is its OWN `git init` repo
(so `repo_root()` resolves there), with a stub store module and a temp `jobs.json`
under a temp HOME. No live DB, no live governance state.

The gate's DECISIONS are unchanged: 0 loaded / 1 not loaded / 2 usage / 3 store
unreachable. Only the refusal path for a provably tool-deprived automated session
gains the marker acceptance.

Run: <venv>/bin/python -m pytest tests/test_reflexion_check_marker_path.py -q
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CHECKER = REPO / "ops" / "scripts" / "hc-reflexion-check.py"

JOB_ID = "f6694d02d29c"
CRON_SESSION = f"cron_{JOB_ID}_20261030_073743"

STUB_STORE_LOADED_FALSE = '''
class _Sessions:
    def loaded_skill(self, skill, _x="", session_key=None):
        return False


class Store:
    def __init__(self, *a, **k):
        self.sessions = _Sessions()

    def available(self):
        return True
'''


def _marker_content(n_bytes: int = 320, *, include_header: bool = True) -> str:
    header = "## Reflexion Check\n\n" if include_header else ""
    body = header
    n = 1
    while len(body.encode()) < n_bytes:
        body += f"Q{n} answered — verified with tool output.\n"
        n += 1
    return body


def _sandbox(tmp_path: Path, *, jobs, marker: "str | None" = None,
             as_git: bool = True) -> tuple[Path, Path, Path]:
    """Return (checker_copy, root, home) for one hermetic run.

    The temp `root` is its OWN git repo so the checker's `repo_root()` resolves
    to it (not to the outer checkout). The marker, when given, is placed under
    `<root>/docs/evidence/briefings/Reflexion-check-<session>.<suffix>`.
    """
    root = tmp_path / "root"
    (root / "ops" / "scripts").mkdir(parents=True, exist_ok=True)
    checker = root / "ops" / "scripts" / "hc-reflexion-check.py"
    shutil.copy2(CHECKER, checker)
    # stub store (loaded=False) so the store-backed question answers NOT-LOADED.
    store_dir = root / "ops" / "services" / "mycortex-mem"
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / "store.py").write_text(STUB_STORE_LOADED_FALSE)
    if as_git:
        subprocess.run(["git", "init", "-q", str(root)], check=True)
    home = tmp_path / "home"
    (home / ".hermes" / "cron").mkdir(parents=True, exist_ok=True)
    if jobs is not None:
        import json
        (home / ".hermes" / "cron" / "jobs.json").write_text(json.dumps(jobs))
    if marker is not None:
        marker_dir = root / "docs" / "evidence" / "briefings"
        marker_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".md" if marker.endswith(".md") else ".txt"
        # marker is the CONTENT; write under the session-keyed filename
        (marker_dir / f"Reflexion-check-{CRON_SESSION}{suffix}").write_text(marker)
    return checker, root, home


def _run(checker: Path, root: Path, home: Path, session: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(checker), "--session", session],
        capture_output=True, text=True, cwd=root,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        timeout=120,
    )


def _job(name: str, toolsets):
    return {"id": JOB_ID, "name": name, "enabled_toolsets": toolsets, "prompt": "p"}


# ── AC1 (positive): tool-deprived automated session + valid marker -> PASS ────

def test_deprived_session_with_valid_marker_passes(tmp_path):
    marker = _marker_content(320, include_header=True)
    checker, root, home = _sandbox(
        tmp_path,
        jobs={"jobs": [_job("orch-task-morning-pass", ["terminal", "web", "file"])]},
        marker=marker + ".md")
    r = _run(checker, root, home, CRON_SESSION)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    assert "AUDITED-MARKER" in out, "the acceptance must name the marker path"
    assert "Reflexion-check-" in out


# ── AC2 (fail-closed): same session, marker MISSING -> still refused ─────────

def test_deprived_session_without_marker_refuses(tmp_path):
    checker, root, home = _sandbox(
        tmp_path, jobs={"jobs": [_job("orch-task-morning-pass", ["terminal", "web", "file"])]},
        marker=None)
    r = _run(checker, root, home, CRON_SESSION)
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "NOT-LOADED" in out
    assert "AUDITED-MARKER" not in out


# ── AC3 (fail-closed): marker WITHOUT the required header (stub) -> refused ──

def test_stub_marker_without_header_refuses(tmp_path):
    marker = _marker_content(320, include_header=False)
    checker, root, home = _sandbox(
        tmp_path, jobs={"jobs": [_job("orch-task-morning-pass", ["terminal", "web", "file"])]},
        marker=marker + ".md")
    r = _run(checker, root, home, CRON_SESSION)
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "AUDITED-MARKER" not in out


# ── AC4 (fail-closed): marker with header but BELOW min bytes -> refused ─────

def test_undersized_marker_refuses(tmp_path):
    marker = _marker_content(10, include_header=True)  # header only, < 200 bytes
    checker, root, home = _sandbox(
        tmp_path, jobs={"jobs": [_job("orch-task-morning-pass", ["terminal", "web", "file"])]},
        marker=marker + ".md")
    r = _run(checker, root, home, CRON_SESSION)
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "AUDITED-MARKER" not in out


# ── AC5 (fail-closed): INTERACTIVE session never reaches the marker path ─────

def test_interactive_session_ignores_marker(tmp_path):
    marker = _marker_content(320, include_header=True)
    checker, root, home = _sandbox(
        tmp_path, jobs={"jobs": [_job("orch-task-morning-pass", ["terminal", "web", "file"])]},
        marker=marker + ".md")
    r = _run(checker, root, home, "interactive-session-abc")
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "AUDITED-MARKER" not in out


# ── AC6 (fail-closed): job with NO allowlist -> cannot prove a gap -> refused ─

def test_no_allowlist_job_nevers_fires_marker(tmp_path):
    marker = _marker_content(320, include_header=True)
    checker, root, home = _sandbox(
        tmp_path, jobs={"jobs": [_job("orch-bus-worker", None)]},
        marker=marker + ".md")
    r = _run(checker, root, home, CRON_SESSION)
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "AUDITED-MARKER" not in out


# ── AC7 (fail-closed): job WITH skills toolset -> session could load -> refused ─

def test_job_with_skills_toolset_nevers_fires_marker(tmp_path):
    marker = _marker_content(320, include_header=True)
    checker, root, home = _sandbox(
        tmp_path,
        jobs={"jobs": [_job("orch-task-morning-pass", ["terminal", "web", "file", "skills"])]},
        marker=marker + ".md")
    r = _run(checker, root, home, CRON_SESSION)
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "AUDITED-MARKER" not in out


# ── AC8 (fail-closed): no git checkout -> repo_root None -> refused ──────────

def test_no_git_checkout_refuses(tmp_path):
    marker = _marker_content(320, include_header=True)
    checker, root, home = _sandbox(
        tmp_path, jobs={"jobs": [_job("orch-task-morning-pass", ["terminal", "web", "file"])]},
        marker=marker + ".md", as_git=False)
    r = _run(checker, root, home, CRON_SESSION)
    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    assert "AUDITED-MARKER" not in out