#!/usr/bin/env python3
"""A lock must not lie about WHO holds it, or about WHICH repo it governs.

Two claims, reported by kustos (2026-10-13) and verified in the code:

  A. `check_lock` is session-scoped. Asked with no arguments it reads only THIS
     session's lock file, so it answers `active: false` while a live lock for
     another session sits on disk (docs/enforcer-known-issues.md #1: root-caused,
     fix proposed, never implemented). A false "no lock at all" is the same class
     of defect as a false PASS — a diagnostic that cannot see the fault.

  B. `loop-gov.py` stamps the cwd's git root onto the payload so a lock cannot be
     tagged with the wrong repo. When the cwd is NOT a git repo it returns
     "no-repo" and says NOTHING, so a lock opened in a non-repo tree is tagged
     with the host-canonical repo, `repo_path` empty, with no signal at all.

Hermetic: the MCP module's state dir is patched to a tmp dir, so no real lock,
cycle or DB row is touched. Run with pytest.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _mcp():
    return _load(REPO / "mcp-servers" / "loop-gov-mcp.py", "loop_gov_locktruth")


def _cli():
    return _load(REPO / "ops" / "scripts" / "loop-gov.py", "loop_gov_cli_locktruth")


def _write_lock(state_dir: Path, session_id: str, **over) -> Path:
    state = {
        "task_id": "foreign-task",
        "session_id": session_id,
        "status": "executing",
        "heartbeat_at": "2099-01-01T00:00:00Z",
        "ttl_seconds": 3600,
        "repo_slug": "koscap-mwi",
        "repo_path": "",
    }
    state.update(over)
    p = state_dir / f".governance-{session_id}.json"
    p.write_text(json.dumps(state))
    return p


# ── A: every live lock is reported, not just mine ────────────────────────────

def test_a_foreign_live_lock_is_reported(tmp_path, monkeypatch):
    m = _mcp()
    monkeypatch.setattr(m, "GOVERNANCE_STATE_DIR", tmp_path)
    _write_lock(tmp_path, "sess_FOREIGN")

    locks = m._live_locks()
    assert [l["session_id"] for l in locks] == ["sess_FOREIGN"], locks
    assert locks[0]["task_id"] == "foreign-task"
    assert locks[0]["repo_slug"] == "koscap-mwi"


def test_check_lock_no_longer_reads_as_no_locks_at_all(tmp_path, monkeypatch):
    """`active` stays this session's truth (a bare call resolves no session); the
    FULL picture rides beside it, which is what the tool's contract promised."""
    m = _mcp()
    monkeypatch.setattr(m, "GOVERNANCE_STATE_DIR", tmp_path)
    _write_lock(tmp_path, "sess_FOREIGN")

    got = json.loads(m._check_lock({}).content[0].text)
    assert got["active"] is False, got
    assert got["live_lock_count"] == 1, got
    assert [l["session_id"] for l in got["locks"]] == ["sess_FOREIGN"], got


def test_stale_and_unparseable_files_are_not_reported_as_truth(tmp_path, monkeypatch):
    """A stale lock is not live, and a mid-write file is not truth (P1-A: never
    delete what you cannot parse — and never report it either)."""
    m = _mcp()
    monkeypatch.setattr(m, "GOVERNANCE_STATE_DIR", tmp_path)
    _write_lock(tmp_path, "sess_STALE", heartbeat_at="2000-01-01T00:00:00Z")
    (tmp_path / ".governance-midwrite.json").write_text("{not json")

    assert m._live_locks() == []

    _write_lock(tmp_path, "sess_LIVE")
    assert [l["session_id"] for l in m._live_locks()] == ["sess_LIVE"]


def test_an_empty_state_dir_is_zero_locks_not_an_error(tmp_path, monkeypatch):
    m = _mcp()
    monkeypatch.setattr(m, "GOVERNANCE_STATE_DIR", tmp_path / "does-not-exist")
    assert m._live_locks() == []
    got = json.loads(m._check_lock({}).content[0].text)
    assert got["active"] is False and got["live_lock_count"] == 0, got


# ── B: an unresolvable repo identity is named, never silent ──────────────────

def test_a_non_repo_cwd_is_named_not_silent():
    c = _cli()
    note, fatal = c._repo_identity_note(
        "no-repo", Path("/home/app/mwi/koscap-mwi"), "hermes-cortex", "begin_change")

    assert fatal is False, "a non-repo cwd is the documented benign case — report it, do not refuse"
    assert note, "silence is the defect: the caller never learns what the lock will claim"
    assert "not a git repo" in note
    assert "/home/app/mwi/koscap-mwi" in note, "name the cwd — it is the only record of where the work was"
    assert "hermes-cortex" in note, "name the repo the lock WILL be tagged with"
    assert "--repo" in note and "inside a repo" in note, "and both ways out"


def test_a_stamped_repo_says_nothing():
    c = _cli()
    assert c._repo_identity_note("stamped", Path("/x"), "koscap-mwi", "begin_change") == (None, False)


def test_an_unresolvable_git_is_fatal_for_begin_change():
    c = _cli()
    note, fatal = c._repo_identity_note("unexpected", Path("/x"), None, "begin_change")
    assert fatal is True, "git missing/hung must fail CLOSED, not warn-and-continue"
    assert note and "Cannot begin" in note, note


def test_an_unresolvable_git_is_reported_for_a_read_tool_too():
    c = _cli()
    note, fatal = c._repo_identity_note("unexpected", Path("/x"), None, "check_lock")
    assert fatal is False
    assert note, "a read tool must say the repo could not be resolved, not stay silent"


def test_the_tool_description_says_what_it_now_returns():
    """The description IS the contract an operator reads. Someone who sees `active:false`
    and stops reading must still be told the full picture is in `locks`. Pinned against
    drift, because a description that silently loses this sentence recreates the trap."""
    import asyncio

    m = _mcp()
    res = asyncio.run(m.list_tools(None))
    desc = {t.name: (t.description or "") for t in res.tools}["check_lock"]
    assert "EVERY live lock" in desc, desc
    assert "locks" in desc and "live_lock_count" in desc, desc


def test_the_cli_wires_the_note_and_prints_it():
    """Superseded by the integration tests below, which RUN the CLI and read its
    real stderr/exit code. Kept as a one-line guard that the call site exists at
    all, since a missing call is a silent-silence regression no runtime test can
    see (the CLI would simply never print)."""
    src = (REPO / "ops" / "scripts" / "loop-gov.py").read_text()
    assert "note, fatal = _repo_identity_note(" in src, "the CLI must consult the note"


# ── B, for real: run the CLI and read what the operating system got ───────────

def _run_cli(args: list[str], cwd: Path, env_overrides: dict[str, str] | None = None):
    """Invoke the CLI as a real process. `cycle_query` is used as the harmless tool:
    it is a read-only SELECT, and the repo stamp runs before dispatch, so the note
    under test is exercised without touching governance state."""
    env = dict(os.environ)
    env.update(env_overrides or {})
    return subprocess.run(
        [sys.executable, str(REPO / "ops" / "scripts" / "loop-gov.py"), *args],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=180)


def test_a_real_non_repo_cwd_run_warns_on_stderr(tmp_path):
    """The point of the fix: the operator LEARNS it. Real process, real stderr."""
    d = tmp_path / "not-a-repo"
    d.mkdir()
    r = _run_cli(["cycle_query", '{"task_id": "no-such-task-zzz"}'], cwd=d)

    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "is not a git repo" in r.stderr, r.stderr
    assert str(d) in r.stderr, "the cwd must be named — it is where the work would happen"
    # portable: name the fallback slug when it resolves, else say it could not be resolved
    assert "hermes-cortex" in r.stderr or "host-canonical" in r.stderr, r.stderr
    assert "--repo" in r.stderr, "and the way out"


def test_a_real_broken_git_refuses_begin_change_with_exit_1(tmp_path):
    """'unexpected' (git missing/hung) fails CLOSED for begin_change — and because the
    refusal happens before dispatch, no cycle or lock is created by this test."""
    d = tmp_path / "not-a-repo"
    d.mkdir()
    r = _run_cli(["begin_change", '{"task_id": "must-not-be-created", "description": "x"}'],
                 cwd=d, env_overrides={"PATH": "/nonexistent"})

    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    assert "Cannot begin" in (r.stdout + r.stderr), (r.stdout, r.stderr)


def test_a_real_broken_git_is_reported_for_a_read_tool_too(tmp_path):
    d = tmp_path / "not-a-repo"
    d.mkdir()
    r = _run_cli(["cycle_query", '{"task_id": "no-such-task-zzz"}'],
                 cwd=d, env_overrides={"PATH": "/nonexistent"})

    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "could not resolve" in r.stderr, r.stderr
