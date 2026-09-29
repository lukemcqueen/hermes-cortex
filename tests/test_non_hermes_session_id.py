"""Regression tests: non-Hermes governance callers (Claude Code) — 2026-09-29.

Luke's report: Claude Code on a separate repo (titus) "couldn't use governance
properly". Two root causes, both covered here:

  A. get_session_id() for a caller WITHOUT the enforcer's per-call injection
     used to fall back to the HOST-GLOBAL ~/.hermes/session.id cache and the
     Hermes marker files — every session on the box resolved to the SAME id,
     so begin_change from one Claude invocation blocked the next, and any
     session could release another's lock. Now: a process-scoped id, stable
     within one MCP child (= one Claude session), disjoint across processes,
     and NEVER adopts a Hermes marker or the shared cache.

  B. (installer) install-claude-governance.sh registers the governance MCP
     servers at USER scope in ~/.claude.json so every repo gets them
     (.mcp.json stays as the per-repo override). Tested by
     test_claude_governance_installer.sh.

Run:  python3 tests/test_non_hermes_session_id.py
"""
import importlib.util
import json
import os
import tempfile
from pathlib import Path

_MCP_PATH = Path(__file__).resolve().parents[1] / "mcp-servers" / "loop-gov-mcp.py"
_spec = importlib.util.spec_from_file_location("loop_gov_mcp_session", _MCP_PATH)
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

_FAIL = []


def _check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        _FAIL.append(name)
        print(f"  FAIL  {name} — {detail}")


def test_hermes_injection_unchanged():
    """Priority 0 (enforcer per-call injection) still wins and is stable."""
    sid = mcp.get_session_id({"session_id": "sess_hermes_abc"})
    _check("hermes: injected id returned verbatim", sid == "sess_hermes_abc")
    sid2 = mcp.get_session_id({"session_id": "sess_hermes_def"})
    _check("hermes: a new injected id wins on the next call",
           sid2 == "sess_hermes_def", f"got {sid2}")


def test_non_hermes_gets_process_scoped_id():
    """No injection → process id, NOT the host-global cache or a Hermes marker."""
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state"
        state.mkdir()
        # A STALE Hermes marker + a poisoned shared cache — the old code would
        # adopt one of these and collide with whatever session wrote them.
        (state / ".hermes-session-current.id").write_text("sess_stale_hermes")
        (Path(td) / "shared-session.id").write_text("sess_shared_cache")

        mcp._PROCESS_SESSION_ID = ""  # fresh process
        mcp.SESSION_FILE = Path(td) / "shared-session.id"  # poisoned cache

        a = mcp.get_session_id(None)
        b = mcp.get_session_id(None)
        _check("non-hermes: id is stable across calls in one process", a == b and a)
        _check("non-hermes: does NOT adopt the stale Hermes marker",
               a != "sess_stale_hermes", a)
        _check("non-hermes: does NOT adopt the shared host cache",
               a != "sess_shared_cache", a)
        _check("non-hermes: id has the sess_ prefix", a.startswith("sess_"))


def test_two_processes_get_disjoint_ids():
    """Different projects stay disjoint; a mid-session MCP-child RESTART in
    the same project keeps the SAME id (adversarial ADV-2872-2: an
    in-memory-only id would orphan the lock on restart)."""
    def fresh_process(slug):
        spec = importlib.util.spec_from_file_location(
            f"lgm_{os.urandom(4).hex()}", _MCP_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod._derive_slug = lambda: slug  # control the project identity
        return mod

    with tempfile.TemporaryDirectory() as td:
        stateA = Path(td) / "stateA"; stateA.mkdir()
        stateB = Path(td) / "stateB"; stateB.mkdir()

        # Session in project alpha: two fresh processes (original + restart).
        m1 = fresh_process("alpha"); m1.GOVERNANCE_STATE_DIR = stateA
        id1 = m1.get_session_id(None)
        m2 = fresh_process("alpha"); m2.GOVERNANCE_STATE_DIR = stateA
        id2 = m2.get_session_id(None)
        _check("restart in same project keeps the SAME id (lock survives)",
               id1 == id2 and id1, f"{id1} vs {id2}")

        # Session in a different project: must be disjoint.
        m3 = fresh_process("beta"); m3.GOVERNANCE_STATE_DIR = stateB
        id3 = m3.get_session_id(None)
        _check("different project gets a DISJOINT id", id3 != id1, f"{id1} vs {id3}")

        # Persistence file exists per project.
        _check("per-project session file written",
               (stateA / ".session-alpha.id").read_text().strip() == id1)


def main():
    print("A. Hermes per-call injection (unchanged)")
    test_hermes_injection_unchanged()
    print("B. Non-Hermes caller isolation")
    test_non_hermes_gets_process_scoped_id()
    print("C. Process disjointness")
    test_two_processes_get_disjoint_ids()
    print()
    if _FAIL:
        print(f"{len(_FAIL)} FAILED: {', '.join(_FAIL)}")
        raise SystemExit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
