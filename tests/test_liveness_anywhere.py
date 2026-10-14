"""#124: the liveness rescue must see activity in ANY repo, not only the lock's own.

`_session_worked_since` scopes its check to the lock's OWN repo. That is right for stopping a PEER
repo's activity from holding this lock, but it left the ordinary case — a session doing a long
governed stretch in a DIFFERENT checkout — invisible: after its TTL plus one renewal budget the
session was judged provably dead and could lose a lock it was holding at that moment.

Every case runs against throwaway trees: `HOME` is repointed (the candidate walk reads it) and the
lock store is a temp dir, so no live lock can be touched. The widening is only safe because the
renewal budget still bounds it, so that is asserted too — otherwise the rescue becomes a lock that
never ages out.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MOD_PATH = REPO / "mcp-servers" / "loop-gov-mcp.py"


def _load():
    spec = importlib.util.spec_from_file_location("loopgov_liveness_under_test", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _iso(minutes_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _repo(path: Path, author: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "-c", f"user.name={author}", "-c", f"user.email={author}@example.com",
                    "commit", "-q", "--allow-empty", "-m", "work"], cwd=path, check=True)
    return path


def test_activity_in_another_repo_counts_as_liveness():
    mod = _load()
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        own = _repo(home / "own-repo", "someone-else")       # nobody the lock's agent authored
        other = _repo(home / "other-repo", "locked-agent")   # the agent working elsewhere
        mod.HOME = home          # a Path: _candidate_repos calls .iterdir() on it
        state = {"session_id": "s", "agent": "locked-agent", "repo_path": str(own)}
        since = _iso(120)
        assert mod._session_worked_since(state, since) is False, (
            "precondition for #124: the repo-scoped check cannot see the other repo's work"
        )
        assert mod._session_worked_anywhere_since(state, since) is True, (
            "the agent committed in another repo since the heartbeat — that is evidence of life"
        )
        assert other.is_dir()


def test_a_peers_commits_in_another_repo_do_not_count():
    """The property the narrow scope protected is preserved: author-scoped, not repo-wide."""
    mod = _load()
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        own = _repo(home / "own-repo", "locked-agent")
        _repo(home / "peer-repo", "some-other-agent")
        mod.HOME = home          # a Path: _candidate_repos calls .iterdir() on it
        state = {"session_id": "s", "agent": "locked-agent", "repo_path": str(own)}
        assert mod._session_worked_anywhere_since(state, _iso(120)) is False, (
            "a peer's commit must never keep this agent's lock alive — that is the deadlock again"
        )


def test_no_activity_anywhere_stays_stale():
    mod = _load()
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        own = _repo(home / "own-repo", "locked-agent")
        mod.HOME = home          # a Path: _candidate_repos calls .iterdir() on it
        state = {"session_id": "s", "agent": "locked-agent", "repo_path": str(own)}
        assert mod._session_worked_anywhere_since(state, _iso(120)) is False


def test_a_missing_or_empty_since_never_claims_activity():
    mod = _load()
    assert mod._session_worked_anywhere_since({"agent": "a"}, "") is False
    assert mod._session_worked_anywhere_since({"agent": "a"}, None) is False


def test_the_scan_is_bounded():
    """It runs inside a staleness judgement inside a purge sweep — an unbounded walk would stall."""
    src = MOD_PATH.read_text(encoding="utf-8")
    assert "_candidate_repos()[:LIVENESS_SCAN_MAX_REPOS]" in src, (
        "the anywhere-scan must cap how many repos it interrogates"
    )
    assert "def _candidate_repos" in src
    assert src.count("def _candidate_repos") == 1, (
        "a duplicated _candidate_repos is a SILENT DISARM: Python keeps the LAST def, so one copy "
        "(and every check only it contained) would be dead while the suite stayed green"
    )


def test_a_stale_lock_is_saved_by_another_repos_activity():
    """End to end through the real predicate: the lock is renewed, not aged out."""
    mod = _load()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        home = tmp_path / "home"
        own = _repo(home / "own-repo", "locked-agent")
        _repo(home / "other-repo", "locked-agent")
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        mod.HOME = home          # a Path: _candidate_repos calls .iterdir() on it
        mod.GOVERNANCE_STATE_DIR = state_dir
        mod.LOOP_DB = tmp_path / "loop-governance.db"
        stale_hb = _iso(120)
        state = {"session_id": "liveness-sess", "task_id": "t", "agent": "locked-agent",
                 "status": "executing", "repo_path": str(own), "repo_slug": "own-repo",
                 "started_at": stale_hb, "heartbeat_at": stale_hb, "ttl_seconds": 3600}
        assert mod._is_lock_stale(state) is False, (
            "a session working in another repo must not be aged out after its TTL"
        )
        assert state.get("liveness_renewals") == 1, "the renewal should be recorded on the lock"

        # …and the OTHER direction: with no activity anywhere it IS stale (a genuinely dead lock).
        # A DIFFERENT agent, deliberately: reusing the busy agent here would be renewed for the
        # right reason, so the case would prove nothing about a lock nobody is working under.
        dead = {"session_id": "dead-sess", "task_id": "t2", "agent": "agent-with-no-commits",
                "status": "executing", "repo_path": str(tmp_path / "gone-repo"),
                "repo_slug": "gone-repo", "started_at": _iso(300), "heartbeat_at": _iso(300),
                "ttl_seconds": 3600}
        assert mod._is_lock_stale(dead) is True


def test_the_renewal_budget_still_bounds_the_rescue():
    """The widening is only safe because a lock cannot be renewed forever."""
    mod = _load()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        home = tmp_path / "home"
        own = _repo(home / "own-repo", "locked-agent")
        _repo(home / "other-repo", "locked-agent")
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        mod.HOME = home          # a Path: _candidate_repos calls .iterdir() on it
        mod.GOVERNANCE_STATE_DIR = state_dir
        mod.LOOP_DB = tmp_path / "loop-governance.db"
        stale_hb = _iso(120)
        state = {"session_id": "budget-sess", "task_id": "t", "agent": "locked-agent",
                 "status": "executing", "repo_path": str(own), "repo_slug": "own-repo",
                 "started_at": stale_hb, "heartbeat_at": stale_hb, "ttl_seconds": 3600}
        assert mod._is_lock_stale(state) is False, "first look: renewed"
        # age it again past the TTL WITHOUT letting the budget reset, then look once more
        state["heartbeat_at"] = _iso(120)
        state["started_at"] = _iso(120)
        assert mod._is_lock_stale(state) is True, (
            "past the renewal budget a commit elsewhere must no longer keep the lock alive — "
            "otherwise an agent (or a cron committing as it) holds a lock forever"
        )
