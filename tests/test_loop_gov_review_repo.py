#!/usr/bin/env python3
"""Regression tests: the adversarial review must audit the repo the SESSION is
working in, never a tree that cannot contain its work.

Failure (2026-10-06, fleet operator reporting an orchestrator host): a delegated
subagent opened its governance lock while working in `~/steadfaste`, but the
lock was tagged `repo_slug: hermes-cortex` — both `_derive_slug()` (MCP) and
`_derive_repo_slug()` (enforcer) return the host's canonical repo whenever
`~/hermes-cortex/.git` exists, regardless of the session's repo. The close gate
then did `repo = HOME / lock["repo_slug"]` and reviewed hermes-cortex: a tree
that cannot contain the work. It returned FINDINGS every time, the close was
refused forever, and each retry spawned another full review (a dozen 420s
timeouts), wedging the server.

Two layers, tested here:

  Part 1 — FAIL LOUD (mcp/servers/loop-gov-mcp.py). When the lock's repo shows
    nothing in the lock window while ANOTHER candidate repo does, refuse the
    close and name both, instead of silently reviewing the wrong tree.
    A no-misfire control is asserted: when the lock's repo DOES contain the
    window's work, the guard does not fire.

  Part 2 — INJECTED IDENTITY (plugins/governance-enforcer/__init__.py). The
    enforcer already injects `session_id` into every mcp__loop_governance__*
    call. It now also learns the session's repo from the paths that session
    actually touches (write/read targets, terminal workdir) and injects it, so
    begin_change records the correct repo_slug in the first place.

Run:  python3 tests/test_loop_gov_review_repo.py   (also pytest-discoverable)
"""
import importlib.util
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

_mcp_spec = importlib.util.spec_from_file_location(
    "loop_gov_mcp_repo", _REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(_mcp_spec)
_mcp_spec.loader.exec_module(mcp)

_enf_spec = importlib.util.spec_from_file_location(
    "enforcer_repo", _REPO / "plugins" / "governance-enforcer" / "__init__.py")
enf = importlib.util.module_from_spec(_enf_spec)
_enf_spec.loader.exec_module(enf)

FAILURE_TEXT = "cannot contain"


# ── helpers ──

def _git(cwd, *args, env=None):
    e = {**os.environ, **(env or {})}
    return subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, text=True, env=e)


def _mkrepo(path: Path, with_commit: bool = True) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "agent@hermes.local")
    _git(path, "config", "user.name", "agent")
    # Hermetic: the host's global hooks would fire on every sandbox commit and
    # add seconds of latency between the window opening and the commit.
    hooks = path / ".nohooks"
    hooks.mkdir(exist_ok=True)
    _git(path, "config", "core.hooksPath", str(hooks))
    if with_commit:
        (path / "work.txt").write_text("x\n")
        _git(path, "add", "work.txt")
        _git(path, "commit", "-q", "-m", "work")
    return path


def _sandbox_home(two_repos: bool = True):
    """(home, started_at): `started_at` is the instant the lock OPENED — taken
    before the work commits, as in production."""
    home = Path(tempfile.mkdtemp(prefix="loop-gov-review-repo-"))
    _mkrepo(home / "hermes-cortex", with_commit=False)      # canonical, EMPTY
    started_at = _iso(time.time())                          # ← the lock opens here
    if two_repos:
        time.sleep(1.1)                                     # commits land INSIDE the window
        _mkrepo(home / "steadfaste", with_commit=True)
    mcp.HOME = home
    mcp.SESSION_FILE = home / ".hermes" / "session.id"
    mcp.GOVERNANCE_STATE_DIR = home / ".hermes-cortex" / "state"
    mcp.GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    mcp._PROCESS_SESSION_ID = ""
    return home, started_at


def _lock(repo_slug: str, started_at: str) -> dict:
    return {
        "task_id": "task-under-test",
        "description": "work in a non-canonical repo",
        "repo_slug": repo_slug,
        "started_at": started_at,
        "session_id": "S1",
        "ttl_seconds": 3600,
        "heartbeat_at": started_at,
    }


# ── Part 1: fail loud on a repo that cannot contain the work ──

def test_review_refuses_when_lock_repo_cannot_contain_the_work():
    _home, started_at = _sandbox_home()
    lock = _lock("hermes-cortex", started_at)

    block = mcp._adversarial_review_gate(lock, {"id": 4242})

    assert block is not None, (
        "the gate reviewed a repo that cannot contain this session's work "
        "instead of refusing"
    )
    text = block.content[0].text
    assert FAILURE_TEXT in text, f"refusal did not explain the mismatch: {text!r}"
    assert "steadfaste" in text, f"refusal did not name the repo holding the work: {text!r}"
    assert "hermes-cortex" in text, f"refusal did not name the lock's repo: {text!r}"


def test_guard_does_not_fire_when_lock_repo_holds_the_work():
    """No-misfire control: a lock whose repo contains the window's work must
    NOT be refused."""
    home, started_at = _sandbox_home(two_repos=False)
    # Commit in the CANONICAL repo, after the lock opened: the work is here.
    time.sleep(1.1)
    repo = home / "hermes-cortex"
    (repo / "work.txt").write_text("y\n")
    _git(repo, "add", "work.txt")
    _git(repo, "commit", "-q", "-m", "the real work")

    lock = _lock("hermes-cortex", started_at)

    block = mcp._adversarial_review_gate(lock, {"id": 4243})
    text = block.content[0].text if block is not None else ""
    assert FAILURE_TEXT not in text, (
        f"the guard fired on a lock whose own repo holds the work: {text!r}"
    )


# ── Part 2a: the MCP honours an injected repo slug ──

def test_derive_slug_prefers_the_injected_repo():
    home, _started = _sandbox_home()
    _mkrepo(home / "proj", with_commit=True)
    mcp.HOME = home

    assert mcp._derive_slug({"repo_slug": "proj"}) == "proj", (
        "an injected repo_slug was ignored — the lock would be tagged with the "
        "host's canonical repo again"
    )


def test_derive_slug_ignores_an_injected_slug_that_is_not_a_repo():
    """An injected slug must be a real repo, else fall back — a bogus value
    must not be able to point the review at an arbitrary directory."""
    home, _started = _sandbox_home()
    mcp.HOME = home
    resolved = mcp._derive_slug({"repo_slug": "not-a-repo"})
    assert resolved != "not-a-repo", "a non-repo slug was accepted as the lock's repo"
    assert resolved == "hermes-cortex", f"expected the canonical fallback, got {resolved!r}"


# ── Part 2b: the enforcer learns the session's repo and injects it ──

def test_enforcer_records_session_repo_from_touched_paths():
    home = Path(tempfile.mkdtemp(prefix="enf-repo-hint-"))
    proj = _mkrepo(home / "repos" / "proj", with_commit=True)
    enf.GOVERNANCE_STATE_DIR = home / ".hermes-cortex" / "state"
    enf.GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)

    enf._note_session_repo("S-hint", {"path": str(proj / "work.txt")})

    assert enf._session_repo_slug("S-hint") == "proj", (
        "the enforcer did not learn the session's repo from a touched path"
    )


def test_enforcer_injects_recorded_repo_into_governance_calls():
    home = Path(tempfile.mkdtemp(prefix="enf-repo-inject-"))
    proj = _mkrepo(home / "repos" / "proj", with_commit=True)
    enf.GOVERNANCE_STATE_DIR = home / ".hermes-cortex" / "state"
    enf.GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)

    enf._note_session_repo("S-inj", {"workdir": str(proj)})
    args = {"task_id": "t", "description": "d"}
    enf._inject_session_context("S-inj", "mcp__loop_governance__begin_change", args)

    assert args.get("session_id") == "S-inj", "session_id injection regressed"
    assert args.get("repo_slug") == "proj", (
        "the session's repo was not injected into the governance call"
    )


def test_enforcer_does_not_inject_a_repo_it_never_learned():
    home = Path(tempfile.mkdtemp(prefix="enf-repo-none-"))
    enf.GOVERNANCE_STATE_DIR = home / ".hermes-cortex" / "state"
    enf.GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    args = {}
    enf._inject_session_context("S-unknown", "mcp__loop_governance__begin_change", args)
    assert "repo_slug" not in args, "injected a repo without any evidence for it"


def _iso(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = []
    for fn in tests:
        try:
            fn()
        except AssertionError as e:
            failed.append((fn.__name__, str(e)))
        except Exception as e:  # noqa: BLE001
            failed.append((fn.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(f"FAIL ({len(failed)}/{len(tests)}):")
        for name, msg in failed:
            print(f"  - {name}: {msg}")
        raise SystemExit(1)
    print(f"PASS ({len(tests)}):")
    for fn in tests:
        print(f"  - {fn.__name__}")
    raise SystemExit(0)
