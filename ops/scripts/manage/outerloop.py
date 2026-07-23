#!/usr/bin/env python3
"""
outerloop — Governance CLI for Evidence → Verdict → Ledger → Answerability.

Implements PRD-005 REQ-007: Every completed run produces an evidence package,
a human verdict, a ledger entry, and a reconstructable answerability chain.

Commands:
    outerloop evidence package --run-id <id>       Package evidence for a run
    outerloop verdict issue --evidence-id <id>      Issue ship/block verdict
    outerloop ledger why <evidence-id>              Reconstruct decision chain
    outerloop ledger list                           List all ledger entries
    outerloop evidence list                         List all evidence packages

Data: ~/.hermes-cortex/state/outerloop.db (SQLite)

Exit codes:
    0 — Success
    1 — Error (missing data, validation failure)
"""

import argparse
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────

HOME = Path.home()
STATE_DIR = HOME / ".hermes-cortex" / "state"
DB_PATH = STATE_DIR / "outerloop.db"
REGISTRY_PATH = STATE_DIR / "agent-registry.json"
CORTEX_REPO = HOME / "hermes-cortex"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS evidence_packages (
    id              TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL,
    agent           TEXT NOT NULL,
    task            TEXT NOT NULL,
    correlation_id  TEXT,
    description     TEXT,
    traces          TEXT,       -- JSON: Langfuse trace IDs, logs
    outputs         TEXT,       -- JSON: command outputs, results
    cost            REAL,       -- token cost estimate
    findings        TEXT,       -- JSON: adversarial findings, issues
    checks_passed   INTEGER DEFAULT 0,
    checks_failed   INTEGER DEFAULT 0,
    sha             TEXT,       -- git SHA at time of run
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS verdicts (
    id              TEXT PRIMARY KEY,
    evidence_id     TEXT NOT NULL REFERENCES evidence_packages(id),
    decision        TEXT NOT NULL CHECK (decision IN ('ship', 'block', 'escalate', 'defer')),
    rationale       TEXT NOT NULL,
    decided_by      TEXT,       -- agent or human name
    decided_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ledger_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    evidence_id     TEXT NOT NULL REFERENCES evidence_packages(id),
    event_type      TEXT NOT NULL,  -- 'evidence_created', 'verdict_issued', 're_opened'
    description     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_run_id ON evidence_packages(run_id);
CREATE INDEX IF NOT EXISTS idx_verdicts_evidence ON verdicts(evidence_id);
CREATE INDEX IF NOT EXISTS idx_ledger_evidence ON ledger_events(evidence_id);
"""


# ── DB helpers ──────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA_SQL)
    return db


# ── Evidence Packaging ─────────────────────────────────────────

def collect_evidence_from_gov_cycles(run_id: str) -> dict:
    """Collect evidence from loop-governance DB cycles matching the run_id."""
    gov_db = HOME / ".hermes-cortex" / "state" / "governance.db"
    evidence = {
        "gov_cycles": [],
        "gov_scores": [],
        "total_cycles": 0,
        "avg_score": 0.0,
    }

    if not gov_db.exists():
        return evidence

    try:
        conn = sqlite3.connect(str(gov_db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM scored_cycles WHERE task_id LIKE ? ORDER BY timestamp DESC LIMIT 20",
            (f"%{run_id}%",)
        ).fetchall()

        scores = []
        for row in rows:
            evidence["gov_cycles"].append({
                "id": row["id"],
                "task_id": row["task_id"],
                "decision": row.get("decision", "unknown"),
                "timestamp": row.get("timestamp", ""),
            })
            composite = row.get("composite", 0.0)
            if composite:
                scores.append(composite)

        evidence["total_cycles"] = len(evidence["gov_cycles"])
        evidence["avg_score"] = sum(scores) / len(scores) if scores else 0.0

        # Get the most recent cycle for deep detail
        if rows:
            latest = rows[0]
            evidence["gov_scores"].append({
                "completeness": latest.get("completeness", 0),
                "quality": latest.get("quality", 0),
                "progress": latest.get("progress", 0),
                "composite": latest.get("composite", 0),
                "decision": latest.get("decision", "unknown"),
                "outcome_note": latest.get("outcome_note", ""),
            })

        conn.close()
    except Exception as e:
        evidence["error"] = str(e)

    return evidence


def get_current_git_sha() -> str:
    """Get current git SHA."""
    try:
        import subprocess
        r = subprocess.run(
            ["git", "-C", str(CORTEX_REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def cmd_evidence_package(args):
    """Package evidence for a governance run."""
    db = get_db()
    run_id = args.run_id
    evidence_id = str(uuid.uuid4())[:12]

    # Collect evidence from various sources
    gov_data = collect_evidence_from_gov_cycles(run_id)

    # Collect agent identity
    agent_name = os.environ.get("AGENT_NAME", os.environ.get("USER", "unknown"))
    agent_version = "1.0.0"

    # Build the evidence package
    package = {
        "evidence_id": evidence_id,
        "run_id": run_id,
        "agent": agent_name,
        "version": agent_version,
        "task": args.description or run_id,
        "correlation_id": args.correlation_id or "",
        "sha": get_current_git_sha(),
        "traces": json.loads(args.traces or "[]"),
        "findings": json.loads(args.findings or "[]"),
        "gov_data": gov_data,
        "checks_passed": args.passed or gov_data.get("total_cycles", 0),
        "checks_failed": args.failed or 0,
        "cost": args.cost or 0.0,
        "outputs": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Store in DB
    db.execute("""
        INSERT INTO evidence_packages
            (id, run_id, agent, task, correlation_id, description,
             traces, outputs, cost, findings, checks_passed, checks_failed, sha)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        evidence_id, run_id, agent_name, args.description or run_id,
        package["correlation_id"], package["task"],
        json.dumps(package["traces"]), json.dumps(package.get("outputs", [])),
        package["cost"], json.dumps(package["findings"]),
        package["checks_passed"], package["checks_failed"], package["sha"],
    ))

    # Log event
    db.execute("""
        INSERT INTO ledger_events (evidence_id, event_type, description)
        VALUES (?, 'evidence_created', ?)
    """, (evidence_id, f"Evidence package created for run '{run_id}'"))

    db.commit()

    print(json.dumps(package, indent=2) if args.json else
          f"📦 Evidence Package: {evidence_id}")
    if not args.json:
        print(f"   Run:        {run_id}")
        print(f"   Agent:      {agent_name}")
        print(f"   SHA:        {package['sha']}")
        print(f"   Gov cycles: {gov_data['total_cycles']}")
        print(f"   Checks:     {package['checks_passed']} passed, {package['checks_failed']} failed")
        print(f"   Findings:   {len(package['findings'])}")
        print(f"\n   Next: outerloop verdict issue --evidence-id {evidence_id} --decision <ship|block> --rationale \"...\"")
        print(f"   Query: outerloop ledger why {evidence_id}")


def cmd_evidence_list(args):
    """List all evidence packages."""
    db = get_db()
    rows = db.execute(
        "SELECT id, run_id, agent, task, checks_passed, checks_failed, sha, created_at "
        "FROM evidence_packages ORDER BY created_at DESC LIMIT ?",
        (args.limit or 20,)
    ).fetchall()

    if not rows:
        print("No evidence packages found.")
        return

    print(f"{'ID':<14} {'Run':<30} {'Agent':<10} {'Pass':<5} {'Fail':<5} {'SHA':<10}")
    print("-" * 80)
    for r in rows:
        print(f"{r['id']:<14} {r['run_id'][:28]:<30} {r['agent']:<10} "
              f"{r['checks_passed']:<5} {r['checks_failed']:<5} {r['sha'][:8]:<10}")
    print(f"\n{len(rows)} package(s)")


# ── Verdicts ────────────────────────────────────────────────────

def cmd_verdict_issue(args):
    """Issue a ship/block verdict on an evidence package."""
    db = get_db()

    # Verify evidence exists
    ev = db.execute("SELECT id, run_id FROM evidence_packages WHERE id = ?",
                    (args.evidence_id,)).fetchone()
    if not ev:
        print(f"❌ Evidence package not found: {args.evidence_id}")
        print("   Use: outerloop evidence package --run-id <id> to create one first")
        sys.exit(1)

    if args.decision not in ("ship", "block", "escalate", "defer"):
        print(f"❌ Invalid decision: {args.decision}")
        print("   Must be one of: ship, block, escalate, defer")
        sys.exit(1)

    if not args.rationale:
        print("❌ Rationale is required (--rationale)")
        sys.exit(1)

    verdict_id = f"v-{uuid.uuid4().hex[:12]}"
    decided_by = args.by or os.environ.get("AGENT_NAME", os.environ.get("USER", "unknown"))

    db.execute("""
        INSERT INTO verdicts (id, evidence_id, decision, rationale, decided_by)
        VALUES (?, ?, ?, ?, ?)
    """, (verdict_id, args.evidence_id, args.decision, args.rationale, decided_by))

    # Log event
    db.execute("""
        INSERT INTO ledger_events (evidence_id, event_type, description)
        VALUES (?, 'verdict_issued', ?)
    """, (args.evidence_id,
          f"Verdict: {args.decision}. By: {decided_by}. Rationale: {args.rationale[:100]}..."))

    db.commit()

    if args.json:
        print(json.dumps({
            "verdict_id": verdict_id,
            "evidence_id": args.evidence_id,
            "decision": args.decision,
            "rationale": args.rationale,
            "decided_by": decided_by,
        }, indent=2))
    else:
        icon = {"ship": "✅", "block": "🔴", "escalate": "🟡", "defer": "🔵"}[args.decision]
        print(f"{icon} Verdict: {args.decision.upper()}")
        print(f"   Evidence:  {args.evidence_id}")
        print(f"   Run:       {ev['run_id']}")
        print(f"   Rationale: {args.rationale}")
        print(f"   By:        {decided_by}")


# ── Ledger / Answerability ─────────────────────────────────────

def cmd_ledger_why(args):
    """Reconstruct the answerability chain for an evidence ID."""
    db = get_db()
    evidence_id = args.evidence_id

    # Get evidence package
    ev = db.execute("SELECT * FROM evidence_packages WHERE id = ?",
                    (evidence_id,)).fetchone()
    if not ev:
        # Try searching by run_id prefix
        evs = db.execute(
            "SELECT * FROM evidence_packages WHERE run_id LIKE ? ORDER BY created_at DESC LIMIT 1",
            (f"%{evidence_id}%",)
        ).fetchone()
        if evs:
            evidence_id = evs["id"]
            ev = evs

    if not ev:
        print(f"❌ No evidence found matching: {evidence_id}")
        sys.exit(1)

    # Get verdict
    verdict = db.execute(
        "SELECT * FROM verdicts WHERE evidence_id = ? ORDER BY decided_at DESC LIMIT 1",
        (evidence_id,)
    ).fetchone()

    # Get event history
    events = db.execute(
        "SELECT * FROM ledger_events WHERE evidence_id = ? ORDER BY created_at ASC",
        (evidence_id,)
    ).fetchall()

    if args.json:
        result = {
            "evidence": dict(ev),
            "verdict": dict(verdict) if verdict else None,
            "events": [dict(e) for e in events],
        }
        print(json.dumps(result, indent=2, default=str))
        return

    # ── Answerability Chain ──
    print("=" * 60)
    print("🔍 ANSWERABILITY CHAIN")
    print("=" * 60)

    # Clause 1: Which agent?
    print(f"\n🧑‍💼 Which agent?")
    print(f"   Agent:   {ev['agent']}")
    print(f"   Task:    {ev['task']}")
    print(f"   Run:     {ev['run_id']}")
    print(f"   SHA:     {ev['sha']}")
    print(f"   Created: {ev['created_at']}")

    # Clause 2: With what authority?
    print(f"\n🔑 With what authority?")
    try:
        traces = json.loads(ev['traces']) if ev['traces'] else []
        if traces:
            print(f"   Traces:  {', '.join(traces)}")
        else:
            print(f"   Traces:  (none recorded)")
    except (json.JSONDecodeError, TypeError):
        print(f"   Traces:  {ev['traces']}")

    # Clause 3: Against what task?
    print(f"\n📋 Against what task?")
    print(f"   Task:       {ev['task']}")
    print(f"   Corr ID:    {ev['correlation_id'] or '(none)'}")
    print(f"   Checks:     {ev['checks_passed']} passed, {ev['checks_failed']} failed")
    print(f"   Findings:   {ev['findings']}")
    try:
        findings = json.loads(ev['findings']) if ev['findings'] else []
        if findings:
            print(f"   Details:")
            for f in findings[:5]:
                sev = f.get("severity", "?")
                tech = f.get("technique", "?")
                target = f.get("target", "?")
                print(f"     - [{sev}] {tech}: {target}")
    except (json.JSONDecodeError, TypeError):
        pass

    # Clause 4: Evidenced by what?
    print(f"\n📊 Evidenced by what?")
    if verdict:
        icon = {"ship": "✅", "block": "🔴", "escalate": "🟡", "defer": "🔵"}.get(verdict["decision"], "?")
        print(f"{icon} Verdict:  {verdict['decision'].upper()}")
        print(f"   Rationale: {verdict['rationale']}")
        print(f"   By:        {verdict['decided_by']}")
        print(f"   At:        {verdict['decided_at']}")
    else:
        print(f"   ❓ No verdict recorded yet")

    # Event timeline
    if events:
        print(f"\n📜 Event Timeline:")
        for e in events:
            print(f"   {e['created_at']} — {e['event_type']}: {e['description']}")

    print("=" * 60)


def cmd_ledger_list(args):
    """List all ledger entries."""
    db = get_db()
    rows = db.execute("""
        SELECT le.id, le.evidence_id, le.event_type, le.description, le.created_at,
               ep.run_id, ep.agent
        FROM ledger_events le
        LEFT JOIN evidence_packages ep ON le.evidence_id = ep.id
        ORDER BY le.created_at DESC LIMIT ?
    """, (args.limit or 50,)).fetchall()

    if not rows:
        print("No ledger entries.")
        return

    print(f"{'Type':<22} {'Evidence':<14} {'Run':<26} {'Description':<40}")
    print("-" * 105)
    for r in rows:
        type_str = r['event_type'][:20]
        evid = r['evidence_id'][:12] if r['evidence_id'] else '?'
        run = (r['run_id'] or '?')[:24]
        desc = (r['description'] or '')[:38]
        print(f"{type_str:<22} {evid:<14} {run:<26} {desc:<40}")


# ── Main ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Outerloop Governance CLI — Evidence → Verdict → Ledger → Answerability"
    )
    sub = parser.add_subparsers(dest="command")

    # evidence package
    pkg = sub.add_parser("evidence", help="Evidence package commands")
    pkg_sub = pkg.add_subparsers(dest="evidence_cmd")

    pkg_package = pkg_sub.add_parser("package", help="Package evidence for a run")
    pkg_package.add_argument("--run-id", required=True, help="Run identifier")
    pkg_package.add_argument("--description", help="Description of the run")
    pkg_package.add_argument("--correlation-id", help="Correlation ID")
    pkg_package.add_argument("--traces", help="JSON array of trace IDs")
    pkg_package.add_argument("--findings", help="JSON array of findings objects")
    pkg_package.add_argument("--passed", type=int, default=0, help="Checks passed")
    pkg_package.add_argument("--failed", type=int, default=0, help="Checks failed")
    pkg_package.add_argument("--cost", type=float, default=0.0, help="Token cost estimate")
    pkg_package.add_argument("--json", action="store_true", help="JSON output")

    pkg_list = pkg_sub.add_parser("list", help="List evidence packages")
    pkg_list.add_argument("--limit", type=int, default=20, help="Max results")

    # verdict issue
    ver = sub.add_parser("verdict", help="Verdict commands")
    ver_sub = ver.add_subparsers(dest="verdict_cmd")

    ver_issue = ver_sub.add_parser("issue", help="Issue a verdict on evidence")
    ver_issue.add_argument("--evidence-id", required=True, help="Evidence package ID")
    ver_issue.add_argument("--decision", required=True,
                           choices=["ship", "block", "escalate", "defer"],
                           help="Decision")
    ver_issue.add_argument("--rationale", required=True, help="Why this decision")
    ver_issue.add_argument("--by", help="Who decided (default: AGENT_NAME)")
    ver_issue.add_argument("--json", action="store_true", help="JSON output")

    # ledger commands
    led = sub.add_parser("ledger", help="Ledger and answerability commands")
    led_sub = led.add_subparsers(dest="ledger_cmd")

    led_why = led_sub.add_parser("why", help="Reconstruct answerability chain")
    led_why.add_argument("evidence_id", help="Evidence ID or run ID prefix")
    led_why.add_argument("--json", action="store_true", help="JSON output")

    led_list = led_sub.add_parser("list", help="List ledger entries")
    led_list.add_argument("--limit", type=int, default=50, help="Max entries")

    args = parser.parse_args()

    if args.command == "evidence":
        if args.evidence_cmd == "package":
            cmd_evidence_package(args)
        elif args.evidence_cmd == "list":
            cmd_evidence_list(args)
        else:
            print("Usage: outerloop evidence package|list [options]")
            sys.exit(1)

    elif args.command == "verdict":
        if args.verdict_cmd == "issue":
            cmd_verdict_issue(args)
        else:
            print("Usage: outerloop verdict issue --evidence-id <id> --decision <ship|block> --rationale \"...\"")
            sys.exit(1)

    elif args.command == "ledger":
        if args.ledger_cmd == "why":
            cmd_ledger_why(args)
        elif args.ledger_cmd == "list":
            cmd_ledger_list(args)
        else:
            print("Usage: outerloop ledger why <evidence-id>")
            print("       outerloop ledger list")
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
