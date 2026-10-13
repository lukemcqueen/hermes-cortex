"""Liveness is OBSERVED ACTIVITY — and a busy session must not be aged out.

Two gaps, both measured on this fleet rather than theorised:

1. `heartbeat_at` moved ONLY inside `check_lock`, a status tool a working agent never calls, so it
   still equalled `started_at` after two hours of governed work. Fixed by refreshing on every
   governed tool call.
2. That alone still freezes during a long stretch of editing and committing with no loop-gov call in
   between — the exact shape of the deadlock. Fixed by checking the lock's OWN repo for a commit
   authored by the lock's OWN agent before declaring it stale.

Both directions are pinned here, including the ones that must NOT be treated as activity: a peer
repo (would keep somebody else's lock alive) and a peer's commit in the same repo (would delay the
peer's own takeover, which is the deadlock again).
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MCP = REPO / "mcp-servers" / "loop-gov-mcp.py"


def _load():
    spec = importlib.util.spec_from_file_location("gov_liveness", MCP)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gov_liveness"] = mod
    spec.loader.exec_module(mod)
    return mod


def _git_author(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%an"],
                          capture_output=True, text=True).stdout.strip()


def test_a_commit_by_the_locks_own_agent_counts_as_activity():
    """The real repo has commits by this agent, so a heartbeat aged since 2020 is 'busy'."""
    mod = _load()
    state = {"repo_path": str(REPO), "agent": _git_author(REPO)}
    assert mod._session_worked_since(state, "2020-01-01T00:00:00Z") is True


def test_a_future_timestamp_is_not_activity():
    """Deterministic negative: nothing was committed after 2030."""
    mod = _load()
    state = {"repo_path": str(REPO), "agent": _git_author(REPO)}
    assert mod._session_worked_since(state, "2030-01-01T00:00:00Z") is False


def test_another_repo_or_another_author_is_not_this_locks_activity(tmp_path):
    """Scoped twice over: the lock's repo AND the lock's agent. Either one wrong means 'not mine'."""
    mod = _load()
    # A repo with no such commits at all.
    other = tmp_path / "empty-repo"
    other.mkdir()
    subprocess.run(["git", "-C", str(other), "init", "-q"], capture_output=True)
    assert mod._session_worked_since({"repo_path": str(other), "agent": "someone"}, "2020-01-01T00:00:00Z") is False
    # The real repo, but attributed to an agent who never committed here.
    assert mod._session_worked_since(
        {"repo_path": str(REPO), "agent": "nobody-saw-me"}, "2020-01-01T00:00:00Z"
    ) is False
    # A path that is not a repo, and a missing path, are not activity either — and must not raise.
    assert mod._session_worked_since({"repo_path": str(tmp_path / "nope")}, "2020-01-01T00:00:00Z") is False
    assert mod._session_worked_since({"repo_path": str(REPO)}, "") is False


def test_the_agent_unknown_field_does_not_disable_the_check():
    """Live locks have carried agent='unknown'. It must fall back to the repo's real author, or the
    check silently stops working — the failure mode this whole exercise is about."""
    mod = _load()
    state = {"repo_path": str(REPO), "agent": "unknown"}
    assert mod._session_worked_since(state, "2020-01-01T00:00:00Z") is True


def test_a_busy_lock_is_not_stale_and_says_so_on_the_file(tmp_path, monkeypatch):
    """End to end through _is_lock_stale: the lock is refreshed instead of purged."""
    mod = _load()
    lock = tmp_path / ".governance-test.json"
    monkeypatch.setattr(mod, "_session_lock_path", lambda sid=None: lock)
    monkeypatch.setattr(mod, "_secondary_lock_path", lambda state: None)
    state = {
        "session_id": "test-session",
        "repo_path": str(REPO),
        "repo_slug": "hermes-cortex",
        "agent": _git_author(REPO),
        "started_at": "2020-01-01T00:00:00Z",
        "heartbeat_at": "2020-01-01T00:00:00Z",
        "ttl_seconds": 3600,
    }
    lock.write_text(json.dumps(state))
    assert mod._is_lock_stale(state) is False, "a session with commits since is busy, not dead"
    written = json.loads(lock.read_text())
    assert written["heartbeat_at"] != "2020-01-01T00:00:00Z", (
        "the lock must record when work happened, not when someone last asked about the lock"
    )
    assert written["started_at"] == "2020-01-01T00:00:00Z", "and must not rewrite history"


def test_an_idle_lock_still_ages_out(tmp_path, monkeypatch):
    """The other direction: no activity, no rescue. An abandoned lock must still expire, or this
    'fix' would pin every orphan forever — worse than the deadlock it cures."""
    mod = _load()
    lock = tmp_path / ".governance-test.json"
    monkeypatch.setattr(mod, "_session_lock_path", lambda sid=None: lock)
    monkeypatch.setattr(mod, "_secondary_lock_path", lambda state: None)
    state = {
        "session_id": "test-session",
        "started_at": "2020-01-01T00:00:00Z",
        "heartbeat_at": "2020-01-01T00:00:00Z",
        "ttl_seconds": 3600,
    }
    lock.write_text(json.dumps(state))
    assert mod._is_lock_stale(state) is True, "no repo, no commits, no rescue: it expires"
    assert json.loads(lock.read_text())["heartbeat_at"] == "2020-01-01T00:00:00Z", (
        "an aged-out lock must not be touched"
    )


def test_commit_liveness_cannot_be_renewed_forever(tmp_path, monkeypatch):
    """The deep-model review named THIS the most dangerous change of the night, and the missing test
    is worth naming too: a commit-based liveness rule is infinitely renewable by anything that keeps
    committing as this agent — a cron, a long-running job — so one lock could outlive every TTL and
    starve every other session in the repo. At most ONE renewal per acquisition."""
    mod = _load()
    lock = tmp_path / ".governance-test.json"
    monkeypatch.setattr(mod, "_session_lock_path", lambda sid=None: lock)
    monkeypatch.setattr(mod, "_secondary_lock_path", lambda state: None)
    state = {
        "session_id": "test-session",
        "repo_path": str(REPO),
        "agent": _git_author(REPO),
        "started_at": "2020-01-01T00:00:00Z",
        "heartbeat_at": "2020-01-01T00:00:00Z",
        "liveness_renewals": 1,  # its one renewal is already spent
        "ttl_seconds": 3600,
    }
    lock.write_text(json.dumps(state))
    assert mod._is_lock_stale(state) is True, (
        "a lock that already used its renewal must age out, however much its agent commits — "
        "otherwise 'activity' is an unbounded hold-open"
    )
    assert json.loads(lock.read_text())["heartbeat_at"] == "2020-01-01T00:00:00Z", (
        "and it must not be touched on the way out"
    )


def test_the_first_renewal_still_works(tmp_path, monkeypatch):
    """The bound must not break the case it exists for: a long busy stretch between two governed
    calls, which is the failure that started all of this."""
    mod = _load()
    lock = tmp_path / ".governance-test.json"
    monkeypatch.setattr(mod, "_session_lock_path", lambda sid=None: lock)
    monkeypatch.setattr(mod, "_secondary_lock_path", lambda state: None)
    state = {
        "session_id": "test-session",
        "repo_path": str(REPO),
        "agent": _git_author(REPO),
        "started_at": "2020-01-01T00:00:00Z",
        "heartbeat_at": "2020-01-01T00:00:00Z",
        "ttl_seconds": 3600,
    }
    lock.write_text(json.dumps(state))
    assert mod._is_lock_stale(state) is False, "the first renewal is the whole point of the rule"
    written = json.loads(lock.read_text())
    assert written["liveness_renewals"] == 1
    assert written["liveness_renewed_at"] == written["heartbeat_at"], (
        "the lock must record that it was renewed by observed activity, not by a status call"
    )


def test_a_fresh_heartbeat_is_never_stale():
    mod = _load()
    assert mod._is_lock_stale(
        {"heartbeat_at": mod._now_iso(), "ttl_seconds": 3600, "repo_path": str(REPO)}
    ) is False
