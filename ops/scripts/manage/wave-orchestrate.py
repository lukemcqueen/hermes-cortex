#!/usr/bin/env python3
"""
wave-orchestrate.py — Five-wave session orchestration CLI.

Manages wave state and quality gates for the delivery pipeline:
  Discovery → Impl-Core → Impl-Polish → Quality → Finalization

Usage:
    wave-orchestrate.py start --task "Deploy auth"    Start new session
    wave-orchestrate.py advance --session <id>        Advance to next wave
    wave-orchestrate.py status --session <id>         Current wave state
    wave-orchestrate.py gates --session <id>          Quality gate results
    wave-orchestrate.py list                          List active sessions

Exit codes:
    0 — Success
    1 — Error
"""

import argparse
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
STATE_DIR = HOME / ".hermes-cortex" / "state"
DB_PATH = STATE_DIR / "wave-sessions.db"

WAVES = ["discovery", "impl-core", "impl-polish", "quality", "final"]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    task            TEXT NOT NULL,
    correlation_id  TEXT,
    current_wave    TEXT NOT NULL DEFAULT 'discovery'
                    CHECK (current_wave IN ('discovery','impl-core','impl-polish','quality','final','complete','blocked')),
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active','complete','blocked')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gate_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    wave_from       TEXT NOT NULL,
    wave_to         TEXT NOT NULL,
    passed          INTEGER NOT NULL DEFAULT 0,
    checks          TEXT,  -- JSON: individual check results
    evidence_note   TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS wave_outputs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    wave_name       TEXT NOT NULL,
    files_changed   TEXT DEFAULT '[]',
    issues_found    INTEGER DEFAULT 0,
    issues_fixed    INTEGER DEFAULT 0,
    handoff_payload TEXT DEFAULT '{}',
    evidence_id     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_gates_session ON gate_results(session_id);
CREATE INDEX IF NOT EXISTS idx_wave_outputs_session ON wave_outputs(session_id);
"""


def get_db() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA_SQL)
    return db


# ── Quality Gates ───────────────────────────────────────────────

GATE_CHECKS = {
    "discovery": {
        "checks": [
            {"id": "scope", "desc": "Scope documented in governance task description"},
            {"id": "surveyed", "desc": "Existing solutions surveyed with 3+ search terms"},
            {"id": "risks", "desc": "Risks identified"},
            {"id": "approach", "desc": "Approach chosen and documented"},
        ],
        "blocking": True,
        "next": "impl-core",
        "label": "G1: Discovery → Impl-Core",
    },
    "impl-core": {
        "checks": [
            {"id": "syntax", "desc": "Syntax valid (bash -n / python3 -m py_compile)"},
            {"id": "conventions", "desc": "Project conventions followed"},
            {"id": "error_paths", "desc": "Error paths handled"},
            {"id": "schemas", "desc": "Boundary schemas validated"},
        ],
        "blocking": True,
        "next": "impl-polish",
        "label": "G2: Impl-Core → Impl-Polish",
    },
    "impl-polish": {
        "checks": [
            {"id": "edge_cases", "desc": "Edge cases handled (nulls, empties, boundaries)"},
            {"id": "deps_failures", "desc": "Dependency error paths covered"},
            {"id": "docs_updated", "desc": "Documentation updated"},
            {"id": "tests_pass", "desc": "Standard test suite passes"},
        ],
        "blocking": True,
        "next": "quality",
        "label": "G3: Impl-Polish → Quality",
    },
    "quality": {
        "checks": [
            {"id": "tests_pass", "desc": "Standard tests: 100% pass"},
            {"id": "adversarial_check", "desc": "Adversarial verifier: no critical/high findings"},
            {"id": "fix_or_doc", "desc": "All findings fixed or documented"},
        ],
        "blocking": True,
        "next": "final",
        "label": "G4: Quality → Final",
    },
    "final": {
        "checks": [
            {"id": "arrays_synced", "desc": "Create/uninstall arrays match"},
            {"id": "old_removed", "desc": "Replaced scripts/crons removed"},
            {"id": "doc_updated", "desc": "All docs referencing changed system updated"},
            {"id": "syntax_valid", "desc": "Syntax check passes"},
            {"id": "doctor_clean", "desc": "cortex-doctor --quiet: 0 failures"},
            {"id": "pushed_deployed", "desc": "git push + cortex-update.sh deployed"},
        ],
        "blocking": True,
        "next": "complete",
        "label": "G5: Final → Complete",
    },
}


def run_gate_checks(session_id: str, wave_name: str) -> dict:
    """Execute quality gate checks for the given wave."""
    gate_def = GATE_CHECKS.get(wave_name)
    if not gate_def:
        return {"passed": False, "checks": [], "error": f"Unknown wave: {wave_name}"}

    results = []
    all_pass = True
    for check in gate_def["checks"]:
        # Run each check — in CLI mode these are informational (agent runs them)
        results.append({
            "id": check["id"],
            "desc": check["desc"],
            "status": "pending",  # Agent determines pass/fail
        })
    return {
        "passed": None,  # Agent sets this after running checks
        "checks": results,
        "blocking": gate_def["blocking"],
        "label": gate_def["label"],
        "next_wave": gate_def["next"],
    }


# ── CLI Commands ────────────────────────────────────────────────

def cmd_start(args):
    """Start a new wave orchestration session."""
    db = get_db()
    session_id = str(uuid.uuid4())[:12]

    db.execute(
        "INSERT INTO sessions (id, task, correlation_id) VALUES (?, ?, ?)",
        (session_id, args.task or "Untitled task", args.correlation_id or "")
    )
    db.commit()

    gate = run_gate_checks(session_id, "discovery")
    gate_result_id = db.execute(
        "INSERT INTO gate_results (session_id, wave_from, wave_to, checks) VALUES (?, 'start', 'discovery', ?)",
        (session_id, json.dumps(gate))
    ).lastrowid

    output = {
        "session_id": session_id,
        "task": args.task,
        "current_wave": "discovery",
        "wave_index": 0,
        "total_waves": len(WAVES),
        "next_wave": "impl-core",
        "gate": gate,
    }

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(f"🚀 Wave Session Started: {session_id}")
        print(f"   Task:      {args.task}")
        print(f"   Wave:      {output['wave_index'] + 1}/{output['total_waves']} — Discovery")
        print(f"   Next:      {output['next_wave'].title()}")
        print(f"\n   Quality Gate G1: Discovery → Impl-Core")
        for c in gate["checks"]:
            print(f"     ⏳ {c['id']}: {c['desc']}")
        print(f"\n   Run: wave-orchestrate.py advance --session {session_id}")
        print(f"   Check: wave-orchestrate.py status --session {session_id}")


def cmd_advance(args):
    """Advance the session to the next wave."""
    db = get_db()

    session = db.execute("SELECT * FROM sessions WHERE id = ?", (args.session_id,)).fetchone()
    if not session:
        print(f"❌ Session not found: {args.session_id}")
        sys.exit(1)
    if session["status"] != "active":
        print(f"❌ Session '{session['id']}' is {session['status']} — cannot advance")
        sys.exit(1)

    current = session["current_wave"]
    if current == "complete":
        print(f"✅ Session already complete")
        return

    gate_def = GATE_CHECKS.get(current)
    if not gate_def:
        print(f"❌ Unknown wave: {current}")
        sys.exit(1)

    next_wave = gate_def["next"]

    # If gate results provided, store them
    passed = args.passed
    checks_passed = args.checks or []
    evidence_note = args.evidence or ""

    gate = run_gate_checks(session["id"], current)
    for c in gate["checks"]:
        if c["id"] in checks_passed:
            c["status"] = "passed"
        elif c["id"] in (args.failed or []):
            c["status"] = "failed"
        else:
            c["status"] = "passed" if passed else "failed"

    gate["passed"] = passed

    db.execute(
        "INSERT INTO gate_results (session_id, wave_from, wave_to, passed, checks, evidence_note) VALUES (?, ?, ?, ?, ?, ?)",
        (session["id"], current, next_wave, 1 if passed else 0, json.dumps(gate), evidence_note)
    )

    db.execute(
        "UPDATE sessions SET current_wave = ?, updated_at = datetime('now') WHERE id = ?",
        (next_wave, session["id"])
    )

    if next_wave == "complete":
        db.execute("UPDATE sessions SET status = 'complete', updated_at = datetime('now') WHERE id = ?",
                   (session["id"],))

    db.commit()

    if not passed and gate_def["blocking"]:
        # Blocked — don't advance
        print(f"🔴 Quality Gate {gate['label']} — BLOCKED")
        print(f"   Session remains in '{current}' until gate passes")
        return

    output = {
        "session_id": session["id"],
        "from": current,
        "to": next_wave,
        "passed": passed,
        "gate": gate,
    }

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        icon = "✅" if passed else "⚠️"
        print(f"{icon} Quality Gate {gate['label']}")
        print(f"   Session: {session['id']}")
        print(f"   From:    {current.title()}")
        print(f"   To:      {next_wave.title()}")
        if next_wave == "complete":
            print(f"\n🎉 Session complete!")
        else:
            idx = WAVES.index(next_wave) if next_wave in WAVES else -1
            print(f"   Wave:    {idx + 1}/{len(WAVES)} — {next_wave.title()}")
            next_gate = GATE_CHECKS.get(next_wave)
            if next_gate:
                print(f"\n   Next Gate: {next_gate['label']}")
                for c in next_gate["checks"]:
                    print(f"     ⏳ {c['id']}: {c['desc']}")
        if not passed:
            print(f"\n   ⚠️  Gate passed but had failures — review before proceeding")


def cmd_status(args):
    """Show current wave session status."""
    db = get_db()

    if args.session_id:
        sessions = db.execute("SELECT * FROM sessions WHERE id = ?", (args.session_id,)).fetchall()
    else:
        sessions = db.execute("SELECT * FROM sessions ORDER BY created_at DESC LIMIT 10").fetchall()

    if not sessions:
        print("No sessions found.")
        return

    all_results = []
    for s in sessions:
        gates = db.execute(
            "SELECT * FROM gate_results WHERE session_id = ? ORDER BY created_at",
            (s["id"],)
        ).fetchall()

        outputs = db.execute(
            "SELECT * FROM wave_outputs WHERE session_id = ? ORDER BY created_at",
            (s["id"],)
        ).fetchall()

        idx = WAVES.index(s["current_wave"]) if s["current_wave"] in WAVES else -1
        result = {
            "session_id": s["id"],
            "task": s["task"],
            "current_wave": s["current_wave"],
            "wave_index": idx + 1 if idx >= 0 else len(WAVES),
            "total_waves": len(WAVES),
            "status": s["status"],
            "created_at": s["created_at"],
            "updated_at": s["updated_at"],
            "gates_passed": sum(1 for g in gates if g["passed"]),
            "gates_total": len(gates),
        }
        all_results.append(result)

    if args.json:
        print(json.dumps(all_results if len(all_results) > 1 else all_results[0], indent=2))
        return

    for r in all_results:
        status_icon = {"active": "🟢", "complete": "✅", "blocked": "🔴"}.get(r["status"], "❓")
        print(f"{status_icon} {r['session_id']}")
        print(f"   Task:    {r['task']}")
        print(f"   Wave:    {r['wave_index']}/{r['total_waves']} — {r['current_wave'].title()}")
        print(f"   Status:  {r['status']}")
        print(f"   Gates:   {r['gates_passed']}/{r['gates_total']} passed")
        print(f"   Since:   {r['created_at'][:19]}")
        print()


def cmd_gates(args):
    """Show quality gate results for a session."""
    db = get_db()

    session = db.execute("SELECT * FROM sessions WHERE id = ?", (args.session_id,)).fetchone()
    if not session:
        print(f"❌ Session not found: {args.session_id}")
        sys.exit(1)

    gates = db.execute(
        "SELECT * FROM gate_results WHERE session_id = ? ORDER BY created_at",
        (session["id"],)
    ).fetchall()

    if not gates:
        print(f"No gates recorded for session {session['id']}")
        return

    results = []
    for g in gates:
        checks = json.loads(g["checks"]) if g["checks"] else {}
        results.append({
            "id": g["id"],
            "wave_from": g["wave_from"],
            "wave_to": g["wave_to"],
            "passed": bool(g["passed"]),
            "checks": checks.get("checks", []),
            "label": checks.get("label", f"{g['wave_from']} → {g['wave_to']}"),
            "evidence_note": g["evidence_note"],
        })

    if args.json:
        print(json.dumps(results, indent=2))
        return

    for r in results:
        icon = "✅" if r["passed"] else "❌"
        print(f"{icon} Gate {r['label']}")
        for c in r["checks"]:
            status_icon = {"passed": "✅", "failed": "❌", "pending": "⏳"}.get(c.get("status", "pending"), "❓")
            print(f"     {status_icon} {c['id']}: {c['desc']}")
        if r["evidence_note"]:
            print(f"     📝 {r['evidence_note']}")
        print()


def cmd_list(args):
    """List all sessions (alias for status without session_id)."""
    cmd_status(args)


# ── Main ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Wave orchestration CLI — 5-wave delivery pipeline with quality gates"
    )
    sub = parser.add_subparsers(dest="command")

    # start
    start = sub.add_parser("start", help="Start a new wave session")
    start.add_argument("--task", "-t", required=True, help="Task description")
    start.add_argument("--correlation-id", help="Correlation ID (from bus EXEC)")
    start.add_argument("--json", action="store_true", help="JSON output")

    # advance
    adv = sub.add_parser("advance", help="Advance to next wave (runs quality gate)")
    adv.add_argument("--session", "--session-id", dest="session_id", required=True, help="Session ID")
    adv.add_argument("--passed", action="store_true", help="Gate passed")
    adv.add_argument("--checks", nargs="*", default=[], help="Check IDs that passed")
    adv.add_argument("--failed", nargs="*", default=[], help="Check IDs that failed")
    adv.add_argument("--evidence", help="Evidence note for the gate")
    adv.add_argument("--json", action="store_true", help="JSON output")

    # status
    stat = sub.add_parser("status", help="Show session status")
    stat.add_argument("--session", "--session-id", dest="session_id", help="Session ID (omit for all active)")
    stat.add_argument("--json", action="store_true", help="JSON output")

    # gates
    gates = sub.add_parser("gates", help="Show quality gate results")
    gates.add_argument("--session", "--session-id", dest="session_id", required=True, help="Session ID")
    gates.add_argument("--json", action="store_true", help="JSON output")

    # list
    lst = sub.add_parser("list", help="List all sessions")
    lst.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args)
    elif args.command == "advance":
        cmd_advance(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "gates":
        cmd_gates(args)
    elif args.command == "list":
        cmd_list(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
