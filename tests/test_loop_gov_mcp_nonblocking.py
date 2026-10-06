#!/usr/bin/env python3
"""Regression tests: ONE session's slow call must not starve every other
session on the shared loop-governance MCP server, and the adversarial
reviewer must fit inside the MCP client's call ceiling.

Failure (2026-10-06, fleet operator: "the governance MCP server itself is now
timing out on every call (420s each) — a symptom of the child's stuck
end_change calls wedging the loop-gov server"):

`call_tool` is async but dispatched its handler SYNCHRONOUSLY --
`return handler(args)`. `_end_change` -> `_adversarial_review_gate` ->
`_call_reviewer` blocks in `subprocess.run(..., timeout=900)` (agent backend)
or `urllib.request.urlopen(..., timeout=300)` (llm backend). One MCP server
process serves every session of its parent (gateway / cron worker), and the
dispatcher's per-request tasks only interleave at await points -- so a
blocking handler starves ALL of them.

Verified live on an orchestrator host: the loop-gov-mcp.py process serving a
cron worker was observed wedged in `poll_schedule_timeout` (that is
`subprocess.run` waiting on its own child) with its `pi` adversarial reviewer
child running 2m11s+. Meanwhile every other call queued behind it hit the
client ceiling (_DEFAULT_TOOL_TIMEOUT = 300 s, hermes-agent
tools/mcp_tool_common.py) -- and the agent reviewer timeout was 900 s, i.e.
longer than any caller can wait.

Pinned here:
  A. a slow handler must NOT block a concurrent call (off-loaded off the loop)
  A-control: the PRE-FIX dispatch shape DOES block it, under the same
     structure -- so a green A means the fix discriminates, not that the
     probe is measuring nothing
  B. the reviewer timeout is clamped BELOW the client ceiling, and BOTH
     reviewer backends actually resolve their timeout through it
  C. the shared in-repo secondary marker (.hermes-cortex/.governance-lock, a
     SINGLE fixed path for the whole repo) is only removed by its OWNER --
     otherwise session A's close unmarks session B's still-live lock

Run:  python3 tests/test_loop_gov_mcp_nonblocking.py
      (also pytest-discoverable)
"""
import asyncio
import importlib.util
import json
import os
import tempfile
import threading
import time
from pathlib import Path

_MCP_PATH = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"
_spec = importlib.util.spec_from_file_location("loop_gov_mcp_nonblocking", _MCP_PATH)
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

SLOW_S = 3.0                 # how long the simulated reviewer-equivalent handler blocks
BLOCKED_IF_OVER_S = 1.0      # a starved concurrent call waits out the whole SLOW_S
CLIENT_CEILING_S = 300       # hermes-agent tools/mcp_tool_common.py _DEFAULT_TOOL_TIMEOUT
CONTROL_MUST_BLOCK_S = SLOW_S - 0.5


class _Params:
    """Stands in for CallToolRequestParams (only .name/.arguments are read)."""

    def __init__(self, name, arguments=None):
        self.name = name
        self.arguments = arguments or {}


def _ok(text):
    return mcp.CallToolResult(content=[mcp.TextContent(type="text", text=text)])


def _sandbox() -> Path:
    home = Path(tempfile.mkdtemp(prefix="loop-gov-nonblocking-"))
    mcp.HOME = home
    mcp.SESSION_FILE = home / ".hermes" / "session.id"
    mcp.LOOP_DB = home / ".hermes-cortex" / "data" / "loop-governance.db"
    mcp.CONFIG_PATH = home / ".hermes-cortex" / "data" / "loop-governance-config.json"
    mcp.CACHE_DB = home / ".hermes-cortex" / "data" / "session-embeddings.db"
    mcp.GOVERNANCE_STATE_DIR = home / ".hermes-cortex" / "state"
    mcp.FORCE_AUDIT_PATH = mcp.GOVERNANCE_STATE_DIR / "force-acquire-audit.json"
    mcp.GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    mcp._require_dogfood = lambda: None
    mcp._PROCESS_SESSION_ID = ""
    return home


# ── A / A-control: a blocking handler must not starve a concurrent call ──
#
# Faithful to production: the "other session" is a SEPARATE thread submitting to
# the one server loop, exactly as a peer process' request lands on the shared
# daemon. Measuring from the same loop cannot work -- when the handler blocks
# the loop, nothing on that loop (not even the probe's own sleep) runs until
# the block ends, which is the defect being pinned.

def _install_slow_cycle_stats(started: "threading.Event"):
    """Monkeypatch a REAL dispatch-map handler to simulate the reviewer's
    blocking work (the map is built at call time from module globals)."""
    def _slow(args):
        started.set()
        time.sleep(SLOW_S)
        return _ok("slow-done")

    mcp._cycle_stats = _slow


def _fast_call_latency(real_dispatch: bool) -> float:
    """Serve the module on a background loop; from THIS thread start a slow
    call, then submit a cheap call and time how long it waits.

    real_dispatch=True  -> exercises the SHIPPED call_tool dispatch.
    real_dispatch=False -> CONTROL: the pre-fix shape (`return handler(args)`),
                           i.e. a sync handler awaited on the loop.
    """
    loop = asyncio.new_event_loop()
    serving = threading.Thread(target=loop.run_forever, daemon=True)
    serving.start()
    try:
        if real_dispatch:
            slow_coro = mcp.call_tool(None, _Params("cycle_stats", {}))
            fast_coro = mcp.call_tool(None, _Params("check_lock", {}))
        else:
            async def _legacy_slow():       # pre-fix: sync call on the loop
                return mcp._cycle_stats({})

            async def _legacy_fast():       # same cheap handler body
                return mcp._check_lock({})

            slow_coro, fast_coro = _legacy_slow(), _legacy_fast()

        started = threading.Event()
        _install_slow_cycle_stats(started)
        slow_fut = asyncio.run_coroutine_threadsafe(slow_coro, loop)
        assert started.wait(timeout=10), "slow handler never started"
        time.sleep(0.2)                     # ensure it is INSIDE the blocking section

        t0 = time.monotonic()
        fast_fut = asyncio.run_coroutine_threadsafe(fast_coro, loop)
        fast_fut.result(timeout=60)
        elapsed = time.monotonic() - t0

        slow_fut.result(timeout=60)
        return elapsed
    finally:
        loop.call_soon_threadsafe(loop.stop)
        serving.join(timeout=5)
        loop.close()


def test_slow_handler_does_not_block_concurrent_call():
    _sandbox()
    fast_real = _fast_call_latency(real_dispatch=True)
    assert fast_real <= BLOCKED_IF_OVER_S, (
        f"a concurrent call was starved for {fast_real:.2f}s while another "
        f"handler blocked for {SLOW_S}s -- the handler is still running ON the "
        f"event loop, so every other session on this shared server queues "
        f"behind it (client ceiling is {CLIENT_CEILING_S}s)"
    )


def test_control_legacy_dispatch_still_blocks():
    """Discrimination guard: the pre-fix dispatch shape MUST reproduce the
    wedge, otherwise test_slow_handler_does_not_block_concurrent_call is
    asserting a probe that cannot fail."""
    _sandbox()
    fast_legacy = _fast_call_latency(real_dispatch=False)
    assert fast_legacy >= CONTROL_MUST_BLOCK_S, (
        f"CONTROL did not reproduce the wedge: the concurrent call returned in "
        f"{fast_legacy:.2f}s while a sync handler blocked for {SLOW_S}s -- the "
        f"probe is not measuring loop starvation"
    )


# ── B: reviewer timeout must fit under the client ceiling ──

def test_reviewer_timeout_clamped_below_client_ceiling():
    ceiling = getattr(mcp, "REVIEWER_TIMEOUT_CEILING", None)
    assert ceiling is not None, (
        "REVIEWER_TIMEOUT_CEILING is not defined -- a reviewer timeout longer "
        "than the MCP client's call ceiling is not a timeout, it is a hang the "
        "caller can never observe"
    )
    assert ceiling < CLIENT_CEILING_S, (
        f"REVIEWER_TIMEOUT_CEILING={ceiling}s is not below the MCP client "
        f"ceiling of {CLIENT_CEILING_S}s"
    )

    # 1. No override: the shipped defaults must already fit.
    os.environ.pop("ADVERSARIAL_REVIEW_AGENT_TIMEOUT", None)
    os.environ.pop("ADVERSARIAL_REVIEW_TIMEOUT", None)
    for env_name, default in (("ADVERSARIAL_REVIEW_AGENT_TIMEOUT", 900),
                              ("ADVERSARIAL_REVIEW_TIMEOUT", 300)):
        resolved = mcp._reviewer_timeout(env_name, default)
        assert resolved <= ceiling, (
            f"{env_name} default resolved to {resolved}s, above the "
            f"{ceiling}s ceiling -- the historical default ({default}s) must be "
            f"brought under the ceiling"
        )

    # 2. An oversized operator override cannot exceed the ceiling.
    os.environ["ADVERSARIAL_REVIEW_AGENT_TIMEOUT"] = "900"
    try:
        assert mcp._reviewer_timeout("ADVERSARIAL_REVIEW_AGENT_TIMEOUT", 900) <= ceiling, (
            "an operator override of 900s was honoured -- it must be clamped, "
            "or the close can never be waited on"
        )
    finally:
        os.environ.pop("ADVERSARIAL_REVIEW_AGENT_TIMEOUT", None)

    # 3. A sane override is still honoured (the clamp is a ceiling, not a constant).
    os.environ["ADVERSARIAL_REVIEW_TIMEOUT"] = "120"
    try:
        assert mcp._reviewer_timeout("ADVERSARIAL_REVIEW_TIMEOUT", 240) == 120, (
            "a sub-ceiling operator override was ignored"
        )
    finally:
        os.environ.pop("ADVERSARIAL_REVIEW_TIMEOUT", None)


def test_both_reviewer_backends_route_through_the_clamp():
    """The helper existing is not the fix -- the backends must USE it."""
    src = _MCP_PATH.read_text()
    for fn in ("_call_reviewer_llm", "_call_reviewer_agent"):
        assert f"def {fn}" in src, f"{fn} not found in {_MCP_PATH.name}"
        body = src.split(f"def {fn}", 1)[1][:5000]
        assert "_reviewer_timeout(" in body, (
            f"{fn} does not resolve its timeout through _reviewer_timeout() -- "
            f"the clamp is unwired and the backend can still block past the "
            f"client ceiling"
        )


# ── C: the shared in-repo marker is only removed by its owner ──

def _lock_state(sid: str) -> dict:
    now = mcp._now_iso()
    return {
        "task_id": f"task-{sid}",
        "description": "test",
        "repo_slug": "proj",
        "started_at": now,
        "session_id": sid,
        "ttl_seconds": 3600,
        "heartbeat_at": now,
    }


def test_secondary_marker_only_owner_removes_it():
    home = _sandbox()
    repo = home / "proj"
    (repo / ".git").mkdir(parents=True)
    mcp.HOME = home
    mcp.SESSION_FILE = home / ".hermes" / "session.id"

    mcp._write_lock(_lock_state("A"), {"session_id": "A"})
    mcp._write_lock(_lock_state("B"), {"session_id": "B"})

    marker = repo / ".hermes-cortex" / ".governance-lock"
    assert marker.exists(), "begin_change did not write the in-repo secondary marker"
    assert json.loads(marker.read_text()).get("session_id") == "B", (
        "second writer should own the shared marker"
    )

    # A closes while B's lock is still live: the shared marker must survive.
    mcp._release_lock({"session_id": "A"})
    assert marker.exists(), (
        "session A's end_change removed the SHARED in-repo marker while session "
        "B's lock was still active -- B is silently unmarked (the enforcer's "
        "Phase-3 fallback then sees no lock for the repo)"
    )

    # B closes: now it may remove its own marker.
    mcp._release_lock({"session_id": "B"})
    assert not marker.exists(), "the owner's release left its own marker behind"


def test_a_session_can_close_its_own_lock_while_another_holds_one():
    """The headline requirement: a governance cycle must be closable by the
    session that owns it, regardless of another session's live lock."""
    home = _sandbox()
    repo = home / "proj"
    (repo / ".git").mkdir(parents=True)
    mcp.HOME = home
    mcp.SESSION_FILE = home / ".hermes" / "session.id"

    mcp._write_lock(_lock_state("A"), {"session_id": "A"})
    mcp._write_lock(_lock_state("B"), {"session_id": "B"})

    a_lock = mcp.GOVERNANCE_STATE_DIR / ".governance-A.json"
    b_lock = mcp.GOVERNANCE_STATE_DIR / ".governance-B.json"
    assert a_lock.exists() and b_lock.exists(), "both sessions must hold their own lock"

    mcp._release_lock({"session_id": "A"})
    assert not a_lock.exists(), "A could not release its OWN lock"
    assert b_lock.exists(), "A's release removed B's lock -- sessions couple"


# ── script runner ──

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
