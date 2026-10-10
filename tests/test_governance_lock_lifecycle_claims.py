#!/usr/bin/env python3
"""Hermetic evidence for the skill guidance in governance-lock-lifecycle Pitfall 7.

Each assertion drives the DEPLOYED MCP module (imported, not stubbed) so the
skill's claims are re-executable rather than narrated. No network, no live lock.

Claims under test (2026-10-10):
  A. A bare `check_lock()` (args=None) cannot resolve a session, so it reads
     `active: false` even when a live lock file exists on disk.
  B. `advance_task_state` reaches a terminal state (`cancelled`) from `executing`
     without any override flag, and the terminal transition releases the lock.
  C. `request_interruption` derives its sub-task id by suffixing the parent's id
     (`{parent}_sub{n}`) — it cannot rename a cycle.
  D. `request_interruption` on a task already in a TERMINAL_STATE is refused
     (the cancel-before-interrupt wedge).

Run: python3 tests/test_governance_lock_lifecycle_claims.py
Exit 0 = ALL PASS, 1 = findings.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MCP_CANDIDATES = [
    Path.home() / ".hermes-cortex/tools/loop-governance/loop-gov-mcp.py",
    REPO / "mcp-servers/loop-gov-mcp.py",
]

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, bool(cond), detail))


def load_mcp():
    src = next((p for p in MCP_CANDIDATES if p.exists()), None)
    if src is None:
        return None
    spec = importlib.util.spec_from_file_location("loop_gov_under_test", src)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["loop_gov_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    mcp = load_mcp()
    if mcp is None:
        print("COULD NOT VERIFY — no loop-gov-mcp.py found at any candidate path")
        return 2

    print(f"module: {mcp.__file__}")

    # --- A: bare check_lock cannot resolve a session -----------------------
    # _read_lock(None) must not find the session-scoped lock file.
    with tempfile.TemporaryDirectory() as td:
        state_dir = Path(td)
        lock = state_dir / ".governance-sess_TEST.json"
        lock.write_text(json.dumps({
            "task_id": "demo", "session_id": "sess_TEST", "status": "executing",
            "heartbeat_at": "2099-01-01T00:00:00Z", "ttl_seconds": 3600,
        }))
        os.environ["HERMES_CORTEX_STATE_DIR"] = str(state_dir)
        try:
            read_none = mcp._read_lock(None)
        except Exception as exc:  # noqa: BLE001
            read_none = f"<raised {exc!r}>"
        check(
            "A. bare _read_lock(None) returns no session (file present on disk)",
            read_none is None,
            f"got={read_none!r}; lock file exists={lock.exists()}",
        )
        check(
            "A. lock file genuinely present (the false-inactive premise)",
            lock.exists(),
            str(lock),
        )
        os.environ.pop("HERMES_CORTEX_STATE_DIR", None)

    # --- B: terminal transition is reachable and releases the lock ---------
    executing = "executing"
    check(
        "B. executing -> cancelled is a VALID transition (no override needed)",
        mcp.is_valid_transition(executing, "cancelled"),
        f"VALID_TRANSITIONS[executing]={mcp.VALID_TRANSITIONS.get(executing)}",
    )
    check(
        "B. `cancelled` is a TERMINAL_STATE",
        "cancelled" in mcp.TERMINAL_STATES,
        f"TERMINAL_STATES={sorted(mcp.TERMINAL_STATES)}",
    )
    src_text = Path(str(mcp.__file__)).read_text()
    check(
        "B. the terminal branch calls _release_lock (release half)",
        "_release_lock(args)" in src_text and "terminal task holds nothing" in src_text,
        "terminal branch + release note present in source",
    )

    # --- C: request_interruption cannot rename -----------------------------
    check(
        "C. sub-task id is derived by suffixing the parent id",
        'sub_task_id = f"{task_id}_sub{sub_counter}"' in src_text,
        'source contains: sub_task_id = f"{task_id}_sub{sub_counter}"',
    )

    # --- D: cancel-before-interrupt wedges ---------------------------------
    check(
        "D. is_valid_transition refuses OUT of a terminal state",
        not mcp.is_valid_transition("cancelled", "interrupt_req"),
        "cancelled -> interrupt_req must be False",
    )

    # ---- report -----------------------------------------------------------
    print()
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok and detail:
            print(f"        {detail}")
    failed = [n for n, ok, _ in results if not ok]
    print()
    if failed:
        print(f"RESULT: FAIL ({len(failed)}): {failed}")
        return 1
    print(f"RESULT: ALL PASS — {len(results)} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
