#!/usr/bin/env python3
"""A queue-driven update must be VISIBLE to the operator.

Luke 2026-10-02: an UPDATE_REQUEST from the queue ran cortex-update silently —
the requester got an UPDATE_RESULT, the human watching the fleet got nothing.

Hermetic: the update, the doctor and the notifier are stubbed, so this pins the
NOTIFICATION CONTENT without running an update or sending a message.

Run: python3 tests/test_update_notification.py
"""
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_FAIL = []


def _check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        _FAIL.append(label)


def _load():
    # The handler imports hermes_paths, which lives in the scripts dir — the real
    # invocation has it on the path. Mirror that here.
    import os
    for p in (REPO / "ops/scripts", Path(os.path.expanduser("~/.hermes-cortex/scripts"))):
        if p.is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location(
        "agent_message_handler", REPO / "ops/scripts/agent/agent-message-handler.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load agent-message-handler.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_notification():
    h = _load()

    captured = []
    setattr(h, "notify_telegram", lambda message, subject="": captured.append((subject, message)))
    setattr(h, "run_cortex_update",
            lambda: {"success": True, "output": "deployed", "stderr": "", "exit_code": 0})
    setattr(h, "run_doctor",
            lambda: {"healthy": True, "version": "1.2.3",
                     "summary": {"pass": 418, "warn": 10, "fail": 0}})

    msg = {"from": "moses", "subject": "UPDATE_REQUEST",
           "body": json.dumps({"target_sha": "abc1234", "target_version": "1.2.3",
                               "run_doctor": True})}
    res = h.process_update_request(msg, "corr-1")
    _check("the update result still comes back (behaviour unchanged)",
           isinstance(res, dict) and "git_sha_after" in res)
    _check("a notification was sent for a queue-driven update", len(captured) == 1, f"got {len(captured)}")
    if captured:
        subj, text = captured[0]
        print("    ---- notification as sent ----")
        for line in text.splitlines():
            print("    " + line)
        _check("names the requester and subject", "moses" in text and "UPDATE_REQUEST" in text)
        _check("names the target SHA/version", "abc1234" in text and "1.2.3" in text)
        _check("shows the git movement", "git:" in text and "→" in text)
        _check("carries the doctor counts", "0 fail" in text and "10 warn" in text)
        _check("reports success clearly", "✅ OK" in text)
        _check("keeps the original subject for threading", subj == "UPDATE_REQUEST", subj)

    # A FAILED update must say so, and surface the error.
    captured.clear()
    setattr(h, "run_cortex_update",
            lambda: {"success": False, "output": "", "stderr": "boom", "exit_code": 1})
    setattr(h, "run_doctor",
            lambda: {"healthy": False, "version": "1.2.3",
                     "summary": {"pass": 1, "warn": 0, "fail": 3}})
    h.process_update_request(msg, "corr-2")
    text = captured[0][1] if captured else ""
    _check("a failed update is reported as FAILED", "❌ FAILED" in text)
    _check("the failure reason is surfaced", "cortex-update failed" in text, text[:200])


if __name__ == "__main__":
    print("Queue-driven update visibility")
    test_notification()
    print()
    if _FAIL:
        print(f"{len(_FAIL)} FAILED: {', '.join(_FAIL)}")
        sys.exit(1)
    print("ALL PASS")
