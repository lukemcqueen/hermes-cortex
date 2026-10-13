"""The 2026-10-13 split: liveness, mutual exclusion and review gating are THREE jobs.

One mechanism used to do all three, so any single failure took the other two down with it: a
heartbeat that only moved when a worker asked about the lock (a status tool nobody calls mid-task),
and a review verdict that gated the LOCK, so a finding the worker could not repair — a window it
could not see past — stranded the whole repo.

These pin the two halves.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MCP = REPO / "mcp-servers" / "loop-gov-mcp.py"


def _load():
    spec = importlib.util.spec_from_file_location("gov_split", MCP)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["gov_split"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def gov(tmp_path, monkeypatch):
    """The module, with the lock path pointed at a tmp file so nothing touches real state."""
    mod = _load()
    lock = tmp_path / ".governance-test.json"
    monkeypatch.setattr(mod, "_session_lock_path", lambda sid=None: lock)
    monkeypatch.setattr(mod, "_secondary_lock_path", lambda state: None)
    return mod, lock


def test_the_heartbeat_moves_on_activity_not_on_a_status_call(gov):
    """LIVENESS = observed activity. Measured failure: heartbeat_at still equalled started_at
    after two hours of governed work, because only check_lock refreshed it."""
    mod, lock = gov
    lock.write_text(json.dumps({
        "session_id": "s1",
        "started_at": "2020-01-01T00:00:00Z",
        "heartbeat_at": "2020-01-01T00:00:00Z",
        "ttl_seconds": 3600,
    }))
    mod._touch_heartbeat({"session_id": "s1"})
    state = json.loads(lock.read_text())
    assert state["heartbeat_at"] != "2020-01-01T00:00:00Z", "doing something must move the heartbeat"
    assert state["started_at"] == "2020-01-01T00:00:00Z", "and must not rewrite history"


def test_a_heartbeat_never_resurrects_a_released_lock(gov):
    """The lock file IS the lock. Refreshing must not create one, or a released session would
    silently re-hold the repo on its next call."""
    mod, lock = gov
    assert not lock.exists()
    mod._touch_heartbeat({"session_id": "s1"})
    assert not lock.exists(), "a heartbeat must never create a lock"


def test_a_refused_close_releases_the_lock(gov):
    """The verdict still stands and the range still cannot be pushed — but the LOCK is bookkeeping,
    and holding it never fixed a finding."""
    mod, lock = gov
    lock.write_text(json.dumps({"session_id": "s1", "task_id": "t"}))
    note = mod._release_after_refusal({"session_id": "s1", "task_id": "t"})
    assert not lock.exists(), "an unfixable verdict must not keep holding the lock"
    assert "RELEASED" in note
    assert "CLEAN review receipt" in note, "the refusal must still say what blocks publishing"


def test_a_lock_without_an_owner_is_never_released_by_guesswork(gov):
    """get_session_id(None) resolves a PROCESS-scoped id, and this server is one shared process
    for every Hermes session — so a fallback here could release a PEER's lock."""
    mod, lock = gov
    lock.write_text(json.dumps({"task_id": "x"}))
    note = mod._release_after_refusal({"task_id": "x"})
    assert lock.exists(), "with no session_id there is no safe session to release"
    assert "NOT released" in note
    assert "peer" in note, "and the reason must say why"


def test_the_light_tier_spends_less_and_the_env_still_wins(monkeypatch):
    """Spend is a tier decision now (2026-10-13): the deep model stays for enforcement/governance
    and unusually large diffs; everything else is judged by the cheap one."""
    mod = _load()
    monkeypatch.setenv("ADVERSARIAL_REVIEW_LIGHT_MODEL", "")
    assert mod._light_reviewer_model() == mod.REVIEWER_LIGHT_MODEL_DEFAULT
    assert mod.REVIEWER_LIGHT_MODEL_DEFAULT != mod.REVIEWER_MODEL_DEFAULT, (
        "the light tier must actually be cheaper than the heavy tier, or the split saves nothing"
    )
    monkeypatch.setenv("ADVERSARIAL_REVIEW_LIGHT_MODEL", "someone/other-model")
    assert mod._light_reviewer_model() == "someone/other-model", "an operator's choice still wins"


def test_the_reviewer_request_is_bounded_and_deterministic(monkeypatch):
    """Cost control where it is actually spent: the request body. An unbounded reviewer is charged
    for prose nobody reads, and a sampling one can return a different verdict on identical
    material."""
    mod = _load()
    seen = {}

    class _Resp:
        def read(self):
            return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        seen["body"] = json.loads(req.data.decode())
        seen["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(mod.urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(mod, "_reviewer_api_key", lambda: "test-key-not-real")
    mod._call_reviewer_llm("prompt", model="m", timeout=42)

    assert seen["body"]["max_tokens"] == mod.REVIEWER_MAX_TOKENS, "output must be bounded"
    assert seen["body"]["temperature"] == mod.REVIEWER_TEMPERATURE, "and deterministic"
    assert seen["timeout"] == 42, "an explicit wait budget is honoured"
