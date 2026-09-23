#!/usr/bin/env python3
"""Probe the governance enforcer's gate logic ON THIS HOST — read-only, no lock.

Why this exists
---------------
Agents (especially weaker models) used to burn turns reading the enforcer
source and guessing what the gates wanted, or looping on blocks that gave no
copy-pasteable remedy. This script answers the question directly: *what does the
enforcer I am actually running do right now?* It exercises the REAL plugin module
- never a re-implementation - in a throwaway state directory, so it is safe to
run at any time, with or without a governance lock.

Use it to verify:
  * a deploy landed (run against the deployed copy vs the repo copy)
  * gate 1 (7 always-skills marker) timing and content verification
  * gate 2 (lock) message + the missing-MCP diagnostic
  * the read-only terminal classifier (what is lock-free vs write-class)
  * per-session skill credit surviving a plugin reload

Usage
-----
  probe-gate-logic.py                       # auto-detect the ACTIVE enforcer
  probe-gate-logic.py --enforcer <path>     # test a specific copy
  probe-gate-logic.py --json                # machine-readable summary

Exit code 0 = every assertion passed; 1 = at least one FAILED.

Cross-platform: Python 3.9+, Linux and macOS. No third-party imports.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

REQUIRED_SKILLS = [
    "task-start",
    "agent-flow",
    "reflexion-check",
    "change-checklist",
    "survey-before-action",
    "agent-contract",
    "test-driven-development",
]

READ_ONLY_LOCKFREE = [
    "ls -la",
    "git status --short",
    "ls | grep foo",
    "git status && git log --oneline -5",
    "journalctl -u hermes-gateway | tail -20",
    "ps aux | grep -v grep | wc -l",
]

READ_ONLY_WRITECLASS = [
    "ls > /tmp/out",
    "cat $(ls)",
    "echo `ls`",
    "sleep 5 &",
    "ls || ls /tmp",
    "ls | sh",
    "git status; mv /tmp/a /tmp/b",
    "cd /tmp && ls",
    "python3 -c 'print(1)'",
    "find . -exec rm {} +",
    "sort -o out.txt in.txt",
    "date -s tomorrow",
    "curl -s https://example.com -d a=b",
    "git branch newbranch",
    "env bash -c 'true'",
]


def resolve_enforcer(explicit: str | None) -> Path:
    """Resolve which enforcer copy is ACTIVE on this host."""
    candidates = []
    if explicit:
        candidates.append(Path(explicit).expanduser())
    if os.environ.get("HERMES_ENFORCER"):
        candidates.append(Path(os.environ["HERMES_ENFORCER"]).expanduser())
    home = Path.home()
    candidates.append(home / ".hermes" / "plugins" / "governance-enforcer" / "__init__.py")
    candidates.append(home / "hermes-cortex" / "plugins" / "governance-enforcer" / "__init__.py")
    for path in candidates:
        if path.is_file():
            return path
    raise SystemExit(
        "Could not find a governance enforcer on this host. Tried:\n  "
        + "\n  ".join(str(c) for c in candidates)
    )


def load_enforcer(path: Path):
    spec = importlib.util.spec_from_file_location("gov_probe_target", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--enforcer", help="path to governance-enforcer/__init__.py")
    parser.add_argument("--json", action="store_true", help="emit JSON summary")
    args = parser.parse_args()

    enforcer_path = resolve_enforcer(args.enforcer)
    deployed = (Path.home() / ".hermes" / "plugins" / "governance-enforcer" / "__init__.py")
    which = "DEPLOYED (active)" if enforcer_path == deployed else f"repo/other: {enforcer_path}"

    failures: list[str] = []
    lines: list[str] = []

    tmp = tempfile.mkdtemp(prefix="gate-probe-")
    enforcer = load_enforcer(enforcer_path)
    # Redirect all state so we never touch the live governance directory.
    enforcer.GOVERNANCE_STATE_DIR = Path(tmp)
    enforcer._secondary_lock_path = lambda: Path(tmp) / ".secondary"

    captured: dict = {}
    enforcer.register(
        type("Ctx", (), {"register_hook": lambda self, name, fn: captured.__setitem__(name, fn)})()
    )
    hook = captured.get("pre_tool_call")
    if hook is None:
        raise SystemExit("Enforcer did not register a pre_tool_call hook")

    def check(label: str, ok: bool) -> None:
        lines.append(f"  {'PASS' if ok else 'FAIL'}  {label}")
        if not ok:
            failures.append(label)

    lines.append(f"Enforcer under test: {enforcer_path}")
    lines.append(f"Copy: {which}")
    lines.append(f"State dir (throwaway): {tmp}")
    lines.append("")

    # ── Gate 1: marker timing and content verification ────────────────────
    lines.append("Gate 1 — 7 always-skills marker")
    sid = "probe_session_alpha"
    check("marker absent before any skill_view", enforcer._check_skills_loaded_marker(sid) is False)
    for index, name in enumerate(REQUIRED_SKILLS, start=1):
        hook(tool_name="skill_view", args={"name": name}, session_id=sid)
        marker_ok = enforcer._check_skills_loaded_marker(sid)
        if index < len(REQUIRED_SKILLS):
            check(f"marker still absent after {index}/7 ({name})", marker_ok is False)
        else:
            check("marker created exactly on the 7th skill (serial calls work)", marker_ok is True)
    # Repeat loads must not unmake the marker
    hook(tool_name="skill_view", args={"name": "task-start"}, session_id=sid)
    check("repeat skill_view keeps the marker valid", enforcer._check_skills_loaded_marker(sid) is True)
    # A session with no skills is still blocked
    check(
        "a different session is not credited by another session's loads",
        enforcer._check_skills_loaded_marker("probe_session_beta") is False,
    )
    # Bare-touch bypass stays closed
    marker = enforcer._session_marker_path(sid)
    marker.write_text("")
    check("hand-written empty marker rejected", enforcer._check_skills_loaded_marker(sid) is False)
    marker.write_text(f"session:{sid}|skills:wrongfingerprint")
    check("fingerprint-mismatched marker rejected", enforcer._check_skills_loaded_marker(sid) is False)
    marker.write_text(f"session:{sid}|skills:{enforcer._skills_fingerprint()}")
    check("correct session+fingerprint marker accepted", enforcer._check_skills_loaded_marker(sid) is True)
    # No session id → fail closed
    check(
        "no session id fails closed (does not inherit another session's proof)",
        enforcer._check_skills_loaded_marker("") is False,
    )

    # ── Gate 1 block message ──────────────────────────────────────────────
    lines.append("")
    lines.append("Gate 1 — block message")
    fresh = "probe_session_gamma"
    block = hook(tool_name="write_file", args={"path": os.path.join(tmp, "x.md"), "content": "x"}, session_id=fresh)
    msg = (block or {}).get("message", "")
    check("write blocked with no skills", bool(block) and block.get("action") == "block")
    check("message names the exact double-underscore tool name", "mcp__loop_governance__begin_change" in msg)
    check("message states it is gate 1 of 2", "GATE 1 of 2" in msg)
    check("message says one batched turn is fine", "ONE TURN" in msg)
    check("message tells the agent NOT to read the enforcer source", "this message IS the procedure" in msg)

    # ── Gate 2: lock ──────────────────────────────────────────────────────
    lines.append("")
    lines.append("Gate 2 — governance lock")
    hook(tool_name="skill_view", args={"name": "x"}, session_id=sid)  # no-op, marker already valid
    lock_block = hook(tool_name="write_file", args={"path": os.path.join(tmp, "y"), "content": "y"}, session_id=sid)
    lmsg = (lock_block or {}).get("message", "")
    check("write blocked with skills but no lock", bool(lock_block) and lock_block.get("action") == "block")
    check("lock message states gate 2 of 2", "GATE 2 of 2" in lmsg)
    check("lock message gives the exact begin_change call", "mcp__loop_governance__begin_change" in lmsg)
    check("lock message explains the missing-MCP case", "hermes mcp list" in lmsg)
    check("lock message forbids hand-written locks", "hand-write" in lmsg.lower())

    # ── Read-only terminal classifier ─────────────────────────────────────
    lines.append("")
    lines.append("Read-only terminal classifier")
    for command in READ_ONLY_LOCKFREE:
        check(f"lock-free: {command!r}", enforcer._is_readonly_terminal_command(command) is True)
    for command in READ_ONLY_WRITECLASS:
        check(f"write-class: {command!r}", enforcer._is_readonly_terminal_command(command) is False)

    # ── Skill credit survives a plugin reload ─────────────────────────────
    lines.append("")
    lines.append("Per-session skill credit")
    credit_sid = "probe_session_credit"
    enforcer._session_skills_loaded.setdefault(credit_sid, set()).add("codebase-design")
    enforcer._persist_session_skills(credit_sid)
    enforcer._session_skills_loaded.clear()          # simulate plugin reload
    check(
        "credit rehydrates after a plugin reload",
        enforcer._session_skills(credit_sid) == {"codebase-design"},
    )
    credit_file = enforcer._skills_credit_path(credit_sid)
    original_fp = enforcer._skills_fingerprint
    enforcer._session_skills_loaded.clear()
    enforcer._skills_fingerprint = lambda: "different-fingerprint"
    check("credit invalidated when the skills fingerprint changes", enforcer._session_skills(credit_sid) == set())
    enforcer._skills_fingerprint = original_fp
    credit_file.write_text("{corrupt")
    enforcer._session_skills_loaded.clear()
    check("corrupt credit journal fails closed", enforcer._session_skills(credit_sid) == set())

    lines.append("")
    summary = {
        "enforcer": str(enforcer_path),
        "copy": which,
        "checks": len(lines),
        "failures": failures,
        "result": "PASS" if not failures else "FAIL",
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("\n".join(lines))
        print(f"\n=== RESULT: {summary['result']} ({len(failures)} failure(s)) ===")
        if failures:
            for item in failures:
                print(f"  - {item}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
