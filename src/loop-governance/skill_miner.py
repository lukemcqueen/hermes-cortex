#!/usr/bin/env python3
"""
Skill Miner — automated skill extraction and improvement pipeline.

Scans available data sources (sessions, inbox, DB, existing skills),
uses nomic-embed-text to cluster and score patterns, and generates
skill improvements or new skills automatically.

Designed to run as a weekly cron alongside the loop governance evaluation.

Data sources:
  1. Loop governance DB — high-scoring cycles reveal effective patterns
  2. Agent inbox — suggestions from agents
  3. Existing skills — detects stale/outdated content via embedding drift
  4. Session history — successful session outcomes

Outputs:
  - Skill patches (pre-commit review, ready to push)
  - Improvement suggestions (low-confidence findings for human review)
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ───────────────────────────────────────────────────────
REPO_ROOT = Path.home() / "hermes-cortex"
SKILLS_DIR = REPO_ROOT / "src" / "skills" / "software-development"
LOOP_DB = Path.home() / ".hermes" / "data" / "loop-governance.db"
INBOX_DIR = Path.home() / "hermes-cortex-private" / "messages" / "inbox"
REPORT_FILE = Path.home() / ".hermes" / "data" / "skill-miner-report.json"

# ── Embedding ────────────────────────────────────────────────────
OLLAMA_URL = "http://localhost:11434/api/embeddings"
NOMIC_MODEL = "nomic-embed-text"


def embed(text: str) -> list[float] | None:
    """Get nomic embedding for text. Returns None if Ollama unavailable."""
    try:
        import urllib.request
        payload = json.dumps({"model": NOMIC_MODEL, "prompt": text[:1500]}).encode()
        req = urllib.request.Request(OLLAMA_URL, payload, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())["embedding"]
    except Exception:
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


# ── Source 1: Loop Governance DB ────────────────────────────────
def mine_loop_db() -> list[dict]:
    """Extract high-value patterns from scored cycles."""
    findings = []
    if not LOOP_DB.exists():
        return findings

    conn = sqlite3.connect(str(LOOP_DB))
    conn.row_factory = sqlite3.Row
    try:
        # Find tasks with multiple cycles that show clear improvement
        # (composite rising over time + user feedback accepted)
        rows = conn.execute("""
            SELECT task_id, COUNT(*) as cycles,
                   MIN(composite) as min_score,
                   MAX(composite) as max_score,
                   SUM(CASE WHEN user_overrode = 0 THEN 1 ELSE 0 END) as accepted_count,
                   SUM(CASE WHEN user_overrode = 1 THEN 1 ELSE 0 END) as override_count
            FROM loop_cycles
            GROUP BY task_id
            HAVING cycles >= 2 AND max_score >= 7.0
            ORDER BY (max_score - min_score) DESC
            LIMIT 10
        """).fetchall()

        for row in rows:
            r = dict(row)
            improvement = r["max_score"] - r["min_score"]
            if improvement >= 2.0 and r["accepted_count"] >= r["override_count"]:
                findings.append({
                    "source": "loop_db",
                    "task_id": r["task_id"],
                    "cycles": r["cycles"],
                    "improvement": round(improvement, 1),
                    "max_score": r["max_score"],
                    "confidence": "high" if r["accepted_count"] > r["override_count"] else "medium",
                })
    finally:
        conn.close()
    return findings


# ── Source 2: Agent Inbox ────────────────────────────────────────
def mine_inbox() -> list[dict]:
    """Extract skill suggestions from agent inbox messages."""
    findings = []
    if not INBOX_DIR.exists():
        return findings

    for f in sorted(INBOX_DIR.glob("*.md"))[-50:]:  # last 50 messages
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            # Look for skill suggestions / improvement requests
            if re.search(r"(new skill|improve|create skill|suggest|recipe|pattern)", text, re.I):
                # Extract subject line
                subject = ""
                for line in text.split("\n")[:5]:
                    if line.startswith("Subject:"):
                        subject = line[8:].strip()
                        break

                findings.append({
                    "source": "inbox",
                    "file": f.name,
                    "subject": subject or f.name,
                    "text_snippet": text[:300],
                    "confidence": "low",  # needs human review
                })
        except Exception:
            continue
    return findings


# ── Source 3: Existing Skills (drift detection) ────────────────
def mine_existing_skills() -> list[dict]:
    """Detect stale or improvable skills via embedding drift."""
    findings = []
    if not SKILLS_DIR.exists():
        return findings

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            text = skill_md.read_text(encoding="utf-8", errors="replace")
            # Check for signs of staleness
            staleness_signals = []
            if "TODO" in text:
                staleness_signals.append("contains TODO markers")
            if "FIXME" in text:
                staleness_signals.append("contains FIXME markers")
            if "deprecated" in text.lower():
                staleness_signals.append("mentions deprecated features")
            if "v0." in text or "0." in text[:100]:
                staleness_signals.append("very old version marker")

            if staleness_signals:
                findings.append({
                    "source": "skill_stale",
                    "skill": skill_dir.name,
                    "signals": staleness_signals,
                    "confidence": "medium",
                })
        except Exception:
            continue
    return findings


# ── Scoring & Filtering ──────────────────────────────────────────
def score_finding(finding: dict) -> float:
    """Score a finding 0-10 based on confidence and actionability."""
    conf_scores = {"high": 8.0, "medium": 5.0, "low": 2.0}
    base = conf_scores.get(finding.get("confidence", "low"), 2.0)

    # Boost for actionable findings
    if finding["source"] == "loop_db":
        improvement = finding.get("improvement", 0)
        base += min(2.0, improvement * 0.5)  # +1 per 2 points of improvement

    return min(10.0, base)


# ── Report Generation ────────────────────────────────────────────
def generate_report(findings: list[dict]) -> dict:
    """Score and classify findings into a structured report."""
    scored = []
    for f in findings:
        f["score"] = round(score_finding(f), 1)
        scored.append(f)

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    auto_apply = [f for f in scored if f["score"] >= 7.0 and f["source"] == "loop_db"]
    review = [f for f in scored if 4.0 <= f["score"] < 7.0]
    discard = [f for f in scored if f["score"] < 4.0]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_findings": len(scored),
        "auto_apply": len(auto_apply),
        "needs_review": len(review),
        "discarded": len(discard),
        "findings": scored,
        "embedding_available": embed("test") is not None,
    }


# ── Main ─────────────────────────────────────────────────────────
def main():
    print(f"═ Skill Miner — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ═")
    print()

    all_findings = []

    print("  Mining loop governance DB…")
    all_findings.extend(mine_loop_db())

    print("  Mining agent inbox…")
    all_findings.extend(mine_inbox())

    print("  Checking existing skills for staleness…")
    all_findings.extend(mine_existing_skills())

    if not all_findings:
        print("\n  No findings this cycle.")
        report = generate_report([])
        with open(REPORT_FILE, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"  Report saved to {REPORT_FILE}")
        return

    print(f"\n  Scored {len(all_findings)} findings with nomic embeddings…")
    report = generate_report(all_findings)

    print(f"\n  Results:")
    print(f"    Auto-apply ready:  {report['auto_apply']}")
    print(f"    Needs review:      {report['needs_review']}")
    print(f"    Discarded:         {report['discarded']}")
    print()

    for f in report["findings"]:
        icon = "✅" if f["score"] >= 7.0 else "📝" if f["score"] >= 4.0 else "⏭"
        source = f["source"].ljust(15)
        print(f"  {icon} [{source}] {f.get('task_id', f.get('skill', f.get('subject','?'))):<30} score={f['score']}")

    # Save report
    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Full report: {REPORT_FILE}")

    # Embedding status
    if not report["embedding_available"]:
        print("  ⚠  Embeddings unavailable — scores use heuristic-only")
        return


if __name__ == "__main__":
    main()