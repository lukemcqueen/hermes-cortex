#!/usr/bin/env python3
"""The repo a write gate consults must be the SESSION'S OWN — never a namesake.

Operator directive (2026-10-14): "cover every project on the server, but do not
mix gates. Each session has its own."

The gate asks the shared predicate (`_check_repo_lock`) whether a live lock
covers a given repo. That predicate originally accepted a lock that recorded no
`repo_path` on a NAME-only match — an upgrade-compat rule borrowed from the git
hook. On this path it is a gate-mixer: two different projects can share a
directory basename, and a lock opened in one would then authorise a native write
in the other. The rule is now fail-closed (an unscoped lock covers nothing) and
`unscoped_locks` reports how many were skipped, so the reason is visible.

This test drives the DEPLOYABLE helper directly against a THROWAWAY state dir —
never the live one. Building the case needs a lock with no `repo_path`, and
hand-writing a lock file in the real state dir is a governance violation, so the
store is repointed before anything runs.

Run:  python3 tests/test_check_repo_lock_scoping.py
   or: pytest tests/test_check_repo_lock_scoping.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# CORTEX_LOOP_GOV_SERVER is the discrimination seam: point it at the PRE-FIX
# server (git show <rev>:mcp-servers/loop-gov-mcp.py > /tmp/pre-fix.py) and this
# suite MUST fail. A test that has never failed on the broken revision proves
# nothing about the fix.
import os as _os

SERVER = Path(
    _os.environ.get("CORTEX_LOOP_GOV_SERVER", REPO / "mcp-servers" / "loop-gov-mcp.py")
)


def _load_server():
    """Import the server module WITHOUT touching live state.

    Safe to import: the file's only module-level side effect is constructing the
    MCP `Server` when the SDK is present, and its entrypoint is behind
    `if __name__ == "__main__"`.
    """
    spec = importlib.util.spec_from_file_location("loop_gov_scoping_under_test", SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_lock(state_dir: Path, name: str, *, repo_path: str | None, mod) -> None:
    """Write one lock in the shape the server itself reads."""
    now = mod._now_iso()
    lock = {
        "task_id": f"task-{name}",
        "session_id": f"sess-{name}",
        "agent": "scoping-test",
        "status": "executing",
        "started_at": now,
        "heartbeat_at": now,
        "ttl_seconds": mod.DEFAULT_TTL,
        "repo_slug": "shared-name",
    }
    if repo_path:
        lock["repo_path"] = repo_path
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / f".governance-sess-{name}.json").write_text(json.dumps(lock))


def _verdict(mod, repo: str) -> dict:
    """Parse the predicate's answer. A refusal returns PLAIN TEXT, not JSON —
    so it is surfaced as {"raw": ...} rather than blowing up the test."""
    res = mod._check_repo_lock({"repo_path": repo})
    text = res.content[0].text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def test_two_projects_sharing_a_name_do_not_share_a_gate(tmp_path):
    mod = _load_server()
    # Repoint the store BEFORE anything runs — the live state dir is never read.
    mod.GOVERNANCE_STATE_DIR = tmp_path / "state"

    # Two DIFFERENT projects that happen to share a directory basename. Each needs
    # a .git marker: without one the predicate cannot resolve a repo and REFUSES
    # before reaching the scoping logic under test (a bare .git dir is enough —
    # the predicate checks existence, so the test stays hermetic and needs no git).
    proj_a = tmp_path / "x" / "shared-name"
    proj_b = tmp_path / "y" / "shared-name"
    proj_a.mkdir(parents=True)
    proj_b.mkdir(parents=True)
    (proj_a / ".git").mkdir()
    (proj_b / ".git").mkdir()

    # A properly scoped lock for A, and an unscoped (legacy) lock also naming
    # "shared-name" — the shape that used to leak A's authority into B.
    _seed_lock(mod.GOVERNANCE_STATE_DIR, "a", repo_path=str(proj_a), mod=mod)
    _seed_lock(mod.GOVERNANCE_STATE_DIR, "b", repo_path=None, mod=mod)

    a = _verdict(mod, str(proj_a))
    assert a["covered"] is True, f"the lock that names this repo must cover it: {a}"
    assert a["match"] == "path", a

    b = _verdict(mod, str(proj_b))
    assert b["covered"] is False, (
        "a lock with no recorded repo_path authorised a DIFFERENT project that "
        f"merely shares its directory name — gates are mixed: {b}"
    )
    assert b["unscoped_locks"] >= 1, (
        "the skipped unscoped lock must be REPORTED, not silently ignored, or "
        f"'fail closed' and 'no lock exists' look identical: {b}"
    )


def test_a_lock_for_another_project_never_covers_this_one(tmp_path):
    """The plain case: a scoped lock for A does not cover B."""
    mod = _load_server()
    mod.GOVERNANCE_STATE_DIR = tmp_path / "state"
    proj_a = tmp_path / "alpha"
    proj_b = tmp_path / "beta"
    proj_a.mkdir(parents=True)
    proj_b.mkdir(parents=True)
    (proj_a / ".git").mkdir()
    (proj_b / ".git").mkdir()
    _seed_lock(mod.GOVERNANCE_STATE_DIR, "a", repo_path=str(proj_a), mod=mod)

    assert _verdict(mod, str(proj_a))["covered"] is True
    assert _verdict(mod, str(proj_b))["covered"] is False
    assert _verdict(mod, str(proj_b))["unscoped_locks"] == 0


def test_an_unresolvable_repo_is_a_refusal_not_an_unlocked_verdict(tmp_path):
    """Cannot-verify must never read as 'fine, no lock needed'."""
    mod = _load_server()
    mod.GOVERNANCE_STATE_DIR = tmp_path / "state"
    mod.GOVERNANCE_STATE_DIR.mkdir(parents=True)
    v = _verdict(mod, str(tmp_path / "not-a-repo"))
    assert "covered" not in v, f"an unresolvable repo must REFUSE, not answer: {v}"
    assert "Cannot verify" in json.dumps(v), v


def test_the_covered_branch_reports_every_unscoped_lock(tmp_path):
    """A covered repo must still report the unscoped locks it skipped.

    Review finding ADV-12605-2: the covered branch returned the count accumulated
    only UP TO the matching lock, so an unscoped lock ordered after it vanished
    from the report. The operator's question ("which gates are mixed?") is
    answered by this number, so a partial count is a wrong answer, not a detail.
    """
    mod = _load_server()
    mod.GOVERNANCE_STATE_DIR = tmp_path / "state"
    proj = tmp_path / "covered"
    proj.mkdir(parents=True)
    (proj / ".git").mkdir()

    # The matching lock FIRST, then an unscoped one — the order that hid it.
    _seed_lock(mod.GOVERNANCE_STATE_DIR, "a", repo_path=str(proj), mod=mod)
    _seed_lock(mod.GOVERNANCE_STATE_DIR, "b", repo_path=None, mod=mod)

    v = _verdict(mod, str(proj))
    assert v["covered"] is True, v
    assert v["unscoped_locks"] == 1, (
        "the covered branch under-reported unscoped locks (an unscoped lock "
        f"ordered after the match was not counted): {v}"
    )


if __name__ == "__main__":
    import tempfile as _t

    failures = 0
    for fn in (
        test_two_projects_sharing_a_name_do_not_share_a_gate,
        test_a_lock_for_another_project_never_covers_this_one,
        test_an_unresolvable_repo_is_a_refusal_not_an_unlocked_verdict,
        test_the_covered_branch_reports_every_unscoped_lock,
    ):
        with _t.TemporaryDirectory() as td:
            try:
                fn(Path(td))
                print(f"✅ {fn.__name__}")
            except AssertionError as exc:
                failures += 1
                print(f"❌ {fn.__name__}: {exc}")
    sys.exit(1 if failures else 0)
