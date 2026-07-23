#!/usr/bin/env python3
"""
escalate-to-human.py — Escalate decisions to human for review.

When outerloop issues a block/escalate verdict, or budget enforcer
flags an agent over budget, this script packages the evidence as a
human-readable message and records the escalation.

Usage:
    escalate-to-human.py --evidence-id <id>           Escalate evidence to human
    escalate-to-human.py --budget --agent moses       Escalate budget breach
    escalate-to-human.py --list                       List pending escalations
    escalate-to-human.py --resolve <id> --decision ship  Resolve an escalation
    escalate-to-human.py --json                       Machine-readable output

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
ESCAPE_DB = STATE_DIR / "escalations.db"
COST_DB = HOME / ".hermes" / "cron" / "cron-costs.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS escalations (
    id              TEXT PRIMARY KEY,
    source          TEXT NOT NULL,   -- 'outerloop' | 'budget' | 'adversarial' | 'manual'
    source_id       TEXT,            -- evidence_id, agent name, etc.
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    evidence        TEXT,            -- JSON: full evidence package
    severity        TEXT NOT NULL CHECK (severity IN ('info','low','medium','high','critical')),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','reviewed','resolved','dismissed')),
    human_decision  TEXT,            -- 'ship' | 'block' | 'escalate' | 'defer'
    human_notes     TEXT,
    sent_to         TEXT,            -- delivery channel
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_esc_status ON escalations(status);
CREATE INDEX IF NOT EXISTS idx_esc_source ON escalations(source);
"""


def get_db():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(ESCAPE_DB))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA_SQL)
    return db


def get_outerloop_evidence(evidence_id: str) -> dict | None:
    """Fetch evidence from outerloop DB."""
    ol_db = STATE_DIR / "outerloop.db"
    if not ol_db.exists():
        return None
    conn = sqlite3.connect(str(ol_db))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM evidence_packages WHERE id = ?", (evidence_id,)
    ).fetchone()
    if not row:
        # Try by run_id prefix
        row = conn.execute(
            "SELECT * FROM evidence_packages WHERE run_id LIKE ? ORDER BY created_at DESC LIMIT 1",
            (f"%{evidence_id}%",)
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def build_escalation_message(esc: dict) -> str:
    """Build a human-readable escalation message."""
    sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}
    icon = sev_icon.get(esc["severity"], "❓")

    lines = [
        f"{icon} **ESCALATION: {esc['title']}**",
        f"",
        f"**Source:** {esc['source']}",
        f"**Severity:** {esc['severity'].upper()}",
        f"**ID:** {esc['id']}",
        f"",
        f"**Description:**",
        f"{esc['description']}",
    ]

    # Add evidence summary
    evidence = json.loads(esc["evidence"]) if isinstance(esc["evidence"], str) and esc["evidence"] else {}
    if evidence:
        lines.extend([
            f"",
            f"**Evidence from {esc['source']}:**",
        ])
        if "run_id" in evidence:
            lines.append(f"  • Run: {evidence['run_id']}")
        if "agent" in evidence:
            lines.append(f"  • Agent: {evidence['agent']}")
        if "checks_passed" in evidence:
            lines.append(f"  • Checks: {evidence['checks_passed']} passed / {evidence.get('checks_failed', 0)} failed")
        if "findings" in evidence:
            try:
                findings = json.loads(evidence["findings"]) if isinstance(evidence["findings"], str) else evidence["findings"]
                if isinstance(findings, list) and len(findings) > 0:
                    lines.append(f"  • Findings: {len(findings)} issue(s)")
                    for f in findings[:5]:
                        fsev = f.get("severity", "?")
                        ftech = f.get("technique", "?")
                        ftarget = f.get("target", "?")
                        lines.append(f"    - [{fsev}] {ftech}: {ftarget}")
            except (json.JSONDecodeError, TypeError):
                pass

    # Add status
    lines.extend([
        f"",
        f"**Status:** {esc['status'].upper()}",
        f"**Created:** {esc['created_at'][:19]}",
    ])

    if esc.get("human_decision"):
        lines.append(f"**Decision:** {esc['human_decision'].upper()} (by human)")
    if esc.get("human_notes"):
        lines.append(f"**Notes:** {esc['human_notes']}")
    if esc.get("resolved_at"):
        lines.append(f"**Resolved:** {esc['resolved_at'][:19]}")

    lines.append(f"")
    lines.append(f"To resolve: `outerloop verdict issue --evidence-id <id> --decision <ship|block> --rationale \"...\"`")

    return "\n".join(lines)


# ── CLI Commands ────────────────────────────────────────────────

def cmd_escalate(args):
    """Escalate an issue to human."""
    db = get_db()
    esc_id = str(uuid.uuid4())[:12]

    source_id = ""
    title = ""
    description = ""
    severity = "medium"
    evidence_data = {}
    sent_to = args.to or "origin"

    if args.evidence_id:
        # Escalate from outerloop evidence
        ev = get_outerloop_evidence(args.evidence_id)
        if not ev:
            print(f"❌ Evidence not found: {args.evidence_id}")
            sys.exit(1)
        source_id = args.evidence_id
        title = f"Outerloop Verdict Required"
        description = f"Evidence package {args.evidence_id} needs human review"

        # Try to get verdict
        ol_db = STATE_DIR / "outerloop.db"
        if ol_db.exists():
            conn_ol = sqlite3.connect(str(ol_db))
            conn_ol.row_factory = sqlite3.Row
            verdict = conn_ol.execute(
                "SELECT * FROM verdicts WHERE evidence_id = ? ORDER BY decided_at DESC LIMIT 1",
                (args.evidence_id,)
            ).fetchone()
            if verdict:
                description = f"Verdict: {verdict['decision']}. Rationale: {verdict['rationale']}"
                if verdict['decision'] in ("block", "escalate"):
                    severity = "high"
            conn_ol.close()

        evidence_data = dict(ev)
        source = "outerloop"

    elif args.budget:
        # Escalate budget breach
        agent = args.agent or args.budget
        title = f"Budget Breach: {agent}"
        description = f"Agent '{agent}' has exceeded its daily token budget"
        severity = "high"
        source_id = agent or ""
        source = "budget"
        evidence_data = {"agent": agent}

    else:
        # Manual escalation
        title = args.title or "Manual Escalation"
        description = args.description or ""
        severity = args.severity or "medium"
        source = "manual"

    db.execute("""
        INSERT INTO escalations (id, source, source_id, title, description, evidence, severity, sent_to)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (esc_id, source, source_id, title, description, json.dumps(evidence_data), severity, sent_to))
    db.commit()

    message = build_escalation_message({
        "id": esc_id, "source": source, "source_id": source_id,
        "title": title, "description": description,
        "evidence": json.dumps(evidence_data),
        "severity": severity, "status": "pending",
        "human_decision": None, "human_notes": None,
        "created_at": datetime.now(timezone.utc).isoformat(), "resolved_at": None,
    })

    output = {
        "escalation_id": esc_id,
        "title": title,
        "severity": severity,
        "message": message,
    }

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(message)

    return esc_id


def cmd_list(args):
    """List pending escalations."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM escalations ORDER BY "
        "CASE status WHEN 'pending' THEN 0 WHEN 'reviewed' THEN 1 ELSE 2 END, "
        "CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, "
        "created_at DESC"
    ).fetchall()

    if args.json:
        print(json.dumps([dict(r) for r in rows], indent=2, default=str))
        return

    if not rows:
        print("No escalations.")
        return

    print(f"{'ID':<14} {'Severity':<10} {'Status':<12} {'Title':<30} {'Source':<14}")
    print("-" * 82)
    for r in rows:
        sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡"}.get(r["severity"], "⚪")
        status_icon = {"pending": "⏳", "reviewed": "👁️", "resolved": "✅", "dismissed": "🚫"}.get(r["status"], "❓")
        print(f"{r['id']:<14} {sev_icon} {r['severity']:<8} {status_icon} {r['status']:<10} "
              f"{r['title'][:28]:<30} {r['source'][:12]:<14}")


def cmd_resolve(args):
    """Resolve an escalation with a human decision."""
    db = get_db()

    row = db.execute("SELECT * FROM escalations WHERE id = ?", (args.resolve,)).fetchone()
    if not row:
        print(f"❌ Escalation not found: {args.resolve}")
        sys.exit(1)

    db.execute("""
        UPDATE escalations SET status = 'resolved', human_decision = ?,
               human_notes = ?, resolved_at = datetime('now')
        WHERE id = ?
    """, (args.decision, args.notes or "", args.resolve))
    db.commit()

    sev_icon = {"ship": "✅", "block": "🔴", "escalate": "🟡", "defer": "🔵"}.get(args.decision, "❓")
    print(f"{sev_icon} Escalation {args.resolve} resolved: {args.decision}")
    print(f"   Notes: {args.notes or '(none)'}")


# ── Main ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Escalate decisions to human for review (HITL)"
    )
    parser.add_argument("--evidence-id", help="Escalate outerloop evidence")
    parser.add_argument("--budget", action="store_true", help="Escalate budget breach")
    parser.add_argument("--agent", help="Agent name (for budget escalation)")
    parser.add_argument("--title", help="Title for manual escalation")
    parser.add_argument("--description", help="Description for manual escalation")
    parser.add_argument("--severity", choices=["info","low","medium","high","critical"],
                        help="Severity for manual escalation")
    parser.add_argument("--to", help="Delivery target (default: origin)")
    parser.add_argument("--list", action="store_true", help="List pending escalations")
    parser.add_argument("--resolve", help="Escalation ID to resolve")
    parser.add_argument("--decision", choices=["ship","block","escalate","defer"],
                        help="Human decision for resolution")
    parser.add_argument("--notes", help="Human notes for resolution")
    parser.add_argument("--json", action="store_true", help="JSON output")

    args = parser.parse_args()

    if args.list:
        cmd_list(args)
    elif args.resolve:
        if not args.decision:
            print("❌ --decision required for --resolve (ship|block|escalate|defer)")
            sys.exit(1)
        cmd_resolve(args)
    elif args.evidence_id or args.budget or args.title:
        cmd_escalate(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
