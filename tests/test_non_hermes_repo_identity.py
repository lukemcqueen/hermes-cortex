#!/usr/bin/env python3
"""Regression tests: a NON-Hermes session's repo identity — 2026-10-09.

Luke's report (titus, pi): a pi session working in a project repo opened a
governance lock, and the lock was NEVER released — he had to delete
`~/.hermes-cortex/state/.governance-sess_*.json` by hand each time ("the lock is
not being removed when the reviewer finishes").

Root cause. The lock's repo comes from `_derive_slug()` / `_derive_repo_path()`.
A Hermes caller has its repo INJECTED by the governance enforcer, so it is
tagged correctly. A non-Hermes caller (pi, Claude Code, Codex, the `loop-gov`
CLI) has NO injector — and the resolver then fell through to Priority 1, the
HOST-CANONICAL repo `~/hermes-cortex`, which exists on every dev host. A session
working in `~/projects/proj` was therefore locked as `hermes-cortex`.

At close, `_adversarial_review_gate` looked for the session's work in the lock's
repo, found none, and refused:

    "Cannot close: the lock's repo cannot contain this session's work."

That refusal leaves the lock HELD (by design) and its only prescribed remedy is
an enforcer injection that does not exist on a non-Hermes host — so nothing but
an operator could release the lock.

Part A — TAGGING: for a caller with no injected repo, the session's own repo
         (the MCP child's working directory = the harness's project, or the
         documented CORTEX_SESSION_REPO identity) wins over the host-canonical
         default.
Part B — NO WEDGE: the whole begin_change -> commit -> score -> end_change path
         releases the lock in that scenario.
Part C — CONTROLS: an injected repo still wins; a cwd that is NOT a git repo
         still falls back to the canonical default (no repo is invented); a
         Hermes caller without a repo hint still keeps the canonical default.

Run:  python3 tests/test_non_hermes_repo_identity.py   (also pytest-discoverable)
"""
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "loop_gov_mcp_repo_identity", _REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mcp)

_FAIL: list = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        _FAIL.append(name)
        print(f"  FAIL  {name} — {detail}")


# ── helpers ──────────────────────────────────────────────────────────────────

def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, text=True)


def _mkrepo(path: Path, with_commit: bool = True, msg: str = "work") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "agent@hermes.local")
    _git(path, "config", "user.name", "agent")
    # Hermetic: the host's global hooks (core.hooksPath) would fire on every
    # sandbox commit and add seconds of latency inside the lock window.
    hooks = path / ".nohooks"
    hooks.mkdir(exist_ok=True)
    _git(path, "config", "core.hooksPath", str(hooks))
    if with_commit:
        (path / "work.txt").write_text("x\n")
        _git(path, "add", "work.txt")
        _git(path, "commit", "-q", "-m", msg)
    return path


def _sandbox(with_project_commit: bool = True):
    """HOME holding the host-canonical repo (as on titus) + a PROJECT repo.

    Returns (home, proj, state_dir). The caller chdirs into `proj`, so the MCP
    child's working directory is the session's project — exactly the pi/Claude
    Code layout.
    """
    home = Path(tempfile.mkdtemp(prefix="non-hermes-repo-id-"))
    _mkrepo(home / "hermes-cortex", with_commit=False)      # canonical, EMPTY
    proj = _mkrepo(home / "projects" / "proj", with_commit=with_project_commit)

    state = home / ".hermes-cortex" / "state"
    state.mkdir(parents=True, exist_ok=True)
    mcp.HOME = home
    mcp.SESSION_FILE = home / ".hermes" / "session.id"
    mcp.GOVERNANCE_STATE_DIR = state
    mcp.LOOP_DB = home / ".hermes-cortex" / "data" / "loop-governance.db"
    mcp._PROCESS_SESSION_ID = ""                            # fresh non-Hermes child
    return home, proj, state


class _Cwd:
    """Run the block with cwd = the session's project (the MCP child's cwd)."""

    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        self.prev = os.getcwd()
        os.chdir(self.path)

    def __exit__(self, *exc):
        os.chdir(self.prev)
        return False


# ── Part A: tagging ──────────────────────────────────────────────────────────

def test_non_hermes_session_is_tagged_with_its_own_repo():
    _home, proj, _state = _sandbox()
    with _Cwd(proj):
        got = mcp._derive_slug(None)
        assert got == "proj", (
            "a non-Hermes session working in a project repo was tagged with the "
            f"host-canonical repo ({got!r}) — the close gate then audits a tree "
            "that cannot contain its work"
        )
        assert mcp._session_repo_path(None) == proj, (
            f"the session's repo path was not resolved: {mcp._session_repo_path(None)}"
        )


def test_begin_change_writes_the_session_repo_into_the_lock():
    _home, proj, state = _sandbox()
    with _Cwd(proj):
        mcp._begin_change({"task_id": "tag-1", "description": "pi work"})
        sid = mcp.get_session_id(None)
        lock = json.loads((state / f".governance-{sid}.json").read_text())
        check("lock carries the session's repo slug", lock.get("repo_slug") == "proj",
              f"repo_slug={lock.get('repo_slug')!r}")
        check("lock carries the session's absolute repo path",
              lock.get("repo_path") == str(proj), f"repo_path={lock.get('repo_path')!r}")
        mcp._release_lock(None)


def test_session_repo_env_identity_is_honoured():
    """The documented per-harness session identity (CORTEX_SESSION_REPO) names
    the repo when the child's cwd is not the project (a gateway-spawned pi).

    Both accepted forms are exercised — an absolute path, and a repo NAME
    resolved as HOME/<name> — plus the bogus case, which must fall back rather
    than point the review at a directory that is not a repo.
    """
    home, proj, _state = _sandbox()
    _mkrepo(home / "named-proj", with_commit=False)
    prev = os.environ.get("CORTEX_SESSION_REPO")

    def _slug_with(value, cwd):
        os.environ["CORTEX_SESSION_REPO"] = value
        with _Cwd(cwd):
            return mcp._derive_slug(None)

    try:
        with _Cwd(Path.home()):     # NOT a repo: cwd gives no answer
            got = _slug_with(str(proj), Path.home())          # absolute path form
            check("CORTEX_SESSION_REPO absolute path is honoured", got == "proj",
                  f"got {got!r}")
            got = _slug_with("named-proj", Path.home())       # HOME/<name> form
            check("CORTEX_SESSION_REPO name form is honoured", got == "named-proj",
                  f"got {got!r}")
            got = _slug_with("does-not-exist", home)          # not a repo → fall back
            check("a bogus CORTEX_SESSION_REPO falls back to the canonical default",
                  got == "hermes-cortex", f"got {got!r}")
    finally:
        if prev is None:
            os.environ.pop("CORTEX_SESSION_REPO", None)
        else:
            os.environ["CORTEX_SESSION_REPO"] = prev


# ── Part B: the reported symptom — the lock must be released ─────────────────

def test_end_change_releases_the_lock_on_a_non_hermes_host():
    """The full pi flow: begin_change -> commit in the PROJECT repo -> score ->
    end_change. The lock must be released, with no 'cannot contain' refusal."""
    _home, proj, state = _sandbox()
    with _Cwd(proj):
        mcp._begin_change({"task_id": "titus-pi-1", "description": "work in a project repo"})
        sid = mcp.get_session_id(None)
        lock_file = state / f".governance-{sid}.json"
        check("begin_change wrote a lock", lock_file.exists())

        # The work lands INSIDE the window, in the project repo (as a pi session
        # does), and is trivial so no live reviewer runs.
        (proj / "work.txt").write_text("x\ny\n")
        _git(proj, "add", "work.txt")
        _git(proj, "commit", "-q", "-m", "pi work")

        mcp._feedback_accept({"task_id": "titus-pi-1", "note": "done, verified",
                              "completeness": 8, "quality": 8, "progress": 8})
        text = mcp._end_change({"task_id": "titus-pi-1"}).content[0].text

        check("close was not refused as a wrong repo", "cannot contain" not in text,
              text[:300])
        check("close succeeded", "closed" in text.lower(), text[:300])
        check("lock released (no manual removal needed)", not lock_file.exists(),
              f"lock file still present: {lock_file}")


# ── Part C: controls — no regression for the injector path ───────────────────

def test_injected_repo_still_wins_over_cwd():
    home, proj, _state = _sandbox()
    deep = _mkrepo(home / "org" / "deeper", with_commit=True)
    with _Cwd(proj):
        assert mcp._derive_slug({"repo_path": str(deep)}) == "deeper", (
            "an injected repo_path was ignored — the enforcer's observation must "
            "stay authoritative"
        )
        assert mcp._session_repo_path({"repo_path": str(deep)}) == deep


def test_cwd_that_is_not_a_repo_still_falls_back_to_canonical():
    home, _proj, _state = _sandbox()
    plain = home / "not-a-repo"
    plain.mkdir()
    with _Cwd(plain):
        got = mcp._derive_slug(None)
        assert got == "hermes-cortex", (
            "a session in a non-repo directory must keep the canonical fallback, "
            f"got {got!r}"
        )


def test_hermes_caller_without_a_repo_hint_keeps_the_canonical_default():
    """A Hermes caller (per-call session_id injected by the enforcer) must NOT be
    re-tagged from the shared daemon's cwd — that is the hermes-agent/hermes-cortex
    mismatch the canonical preference exists to prevent."""
    _home, proj, _state = _sandbox()
    injected = {"session_id": "sess_hermes_injected"}
    with _Cwd(proj):
        slug = mcp._derive_slug(injected)
        check("Hermes caller without a repo hint keeps the canonical default",
              slug == "hermes-cortex", f"got {slug!r}")
        check("no repo path is inferred for a Hermes caller",
              mcp._session_repo_path(injected) is None)


def main():
    print("A. tagging — the session's own repo, not the host-canonical default")
    tests = [
        test_non_hermes_session_is_tagged_with_its_own_repo,
        test_begin_change_writes_the_session_repo_into_the_lock,
        test_session_repo_env_identity_is_honoured,
        test_end_change_releases_the_lock_on_a_non_hermes_host,
        test_injected_repo_still_wins_over_cwd,
        test_cwd_that_is_not_a_repo_still_falls_back_to_canonical,
        test_hermes_caller_without_a_repo_hint_keeps_the_canonical_default,
    ]
    for fn in tests:
        try:
            fn()
        except AssertionError as e:
            _FAIL.append(fn.__name__)
            print(f"  FAIL  {fn.__name__} — {e}")
        except Exception as e:  # noqa: BLE001
            _FAIL.append(fn.__name__)
            print(f"  FAIL  {fn.__name__} — {type(e).__name__}: {e}")
    print()
    if _FAIL:
        print(f"{len(_FAIL)} FAILED: {', '.join(_FAIL)}")
        raise SystemExit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
