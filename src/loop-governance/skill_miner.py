#!/usr/bin/env python3
"""
Skill Miner — automated skill extraction for Hermes Cortex agents.

Runs locally on each agent's machine. Mines available local data sources
for reusable patterns, scores them with nomic-embed-text, and sends
high-confidence findings to Moses via the agent inbox.

Moses collects all inbox findings, reviews, and pushes to hermes-cortex.

Data sources (whatever is available on this machine):
  1. Loop governance DB — high-scoring TDD cycles
  2. Session history — patterns from past conversations
  3. Local memory — agent MEMORY.md, USER.md files
  4. (Optional) Agent inbox messages from other agents

Output:
  - High-confidence findings sent to Moses via agent inbox
  - Local report saved to ~/.hermes/data/skill-miner-report.json
"""

import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Configurable paths ─────────────────────────────────────────
HOME = Path.home()
REPO_ROOT = HOME / "hermes-cortex"
HERMES_DATA = HOME / ".hermes" / "data"
SESSION_DIR = HOME / ".hermes-cortex" / "sessions"
MEMORY_DIR = HOME / ".hermes-cortex" / "memory"
LOOP_DB = HERMES_DATA / "loop-governance.db"
REPORT_FILE = HERMES_DATA / "skill-miner-report.json"
INBOX_URL = os.environ.get("AGENT_INBOX_URL", "https://your-domain.com:13004")
INBOX_SEND_PATH = os.environ.get("AGENT_INBOX_SEND", INBOX_URL.rstrip("/") + "/send")
INBOX_AUTH = os.environ.get("MOSES_INBOX_AUTH", "")

# Read auth from config file if not set via env
if not INBOX_AUTH:
    config_path = HOME / ".hermes" / "moses-inbox.conf"
    if config_path.exists():
        try:
            for line in config_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("MOSES_INBOX_AUTH="):
                    val = line.split("=", 1)[1].strip().strip("'\"")
                    if val:
                        INBOX_AUTH = val
                        break
        except Exception:
            pass

# ── Embedding (nomic-embed-text via local Ollama) ─────────────
OLLAMA_URL = "http://localhost:11434/api/embeddings"
NOMIC_MODEL = "nomic-embed-text"


def send_headers() -> dict:
    """Build HTTP headers for inbox API requests, including auth if configured."""
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if INBOX_AUTH:
        encoded = base64.b64encode(INBOX_AUTH.encode()).decode()
        headers["Authorization"] = "Basic " + encoded
    return headers


def embed(text: str) -> list[float] | None:
    try:
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


# ── Data Sources ───────────────────────────────────────────────

def mine_loop_db() -> list[dict]:
    """Extract patterns from scored TDD cycles (if DB exists)."""
    findings = []
    if not LOOP_DB.exists():
        return findings

    try:
        import sqlite3
        conn = sqlite3.connect(str(LOOP_DB))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT task_id, COUNT(*) as cycles,
                   MIN(composite) as min_score,
                   MAX(composite) as max_score,
                   SUM(CASE WHEN user_overrode = 0 THEN 1 ELSE 0 END) as accepted
            FROM loop_cycles
            GROUP BY task_id
            HAVING cycles >= 2 AND max_score >= 7.0
            ORDER BY (max_score - min_score) DESC
            LIMIT 10
        """).fetchall()

        for row in rows:
            r = dict(row)
            findings.append({
                "type": "tdd_pattern",
                "task": r["task_id"],
                "cycles": r["cycles"],
                "improvement": round(r["max_score"] - r["min_score"], 1),
                "confidence": "high" if r["accepted"] > 0 else "medium",
                "score": 0,  # filled by scoring below
            })
        conn.close()
    except Exception:
        pass
    return findings


def mine_sessions() -> list[dict]:
    """Extract patterns from recent session history (PII-scrubbed)."""
    findings = []
    if not SESSION_DIR.exists():
        return findings

    try:
        for f in sorted(SESSION_DIR.glob("*.md"))[-20:]:
            text = f.read_text(encoding="utf-8", errors="replace")
            # PII sanitization before analysis
            text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', '[EMAIL]', text)
            text = re.sub(r'\b(?:\d[ -]*?){13,16}\b', '[CARD]', text)
            text = re.sub(r'(api[_-]?key|token|password|secret)\s*[=:]\s*["\'][^"\']+["\']',
                         r'\1 = "[REDACTED]"', text, flags=re.I)
            text = re.sub(r'\b(\d{3}[.-]?\d{3}[.-]?\d{4})\b', '[PHONE]', text)

            # Look for success patterns
            clues = []
            if re.search(r"(solved|fixed|resolved|implemented|deployed)", text, re.I):
                clues.append("resolution found")
            if re.search(r"(lesson|learn|remember|recurring)", text, re.I):
                clues.append("has lesson material")
            if re.search(r"(skill|pattern|workflow|recipe)", text, re.I):
                clues.append("skill-worthy pattern")
            if re.search(r"(improve|refactor|optimize|migrate)", text, re.I):
                clues.append("improvement opportunity")

            if clues:
                findings.append({
                    "type": "session_pattern",
                    "file": f.name,
                    "clues": clues,
                    "confidence": "medium" if len(clues) >= 2 else "low",
                    "score": 0,
                })
    except Exception:
        pass
    return findings


def mine_memory() -> list[dict]:
    """Extract patterns from agent memory files."""
    findings = []
    if not MEMORY_DIR.exists():
        return findings

    try:
        for f in MEMORY_DIR.glob("*"):
            if not f.is_file():
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            if len(text.strip()) < 20:
                continue  # skip empty files

            # Score based on content density
            lines = text.strip().split("\n")
            key_terms = sum(1 for term in ["protocol", "workflow", "pattern", "lesson", "config", "fix"]
                           if term in text.lower())

            if key_terms >= 2 or len(lines) >= 5:
                findings.append({
                    "type": "memory_pattern",
                    "file": f.name,
                    "size": len(text),
                    "key_terms": key_terms,
                    "confidence": "medium" if key_terms >= 3 else "low",
                    "score": 0,
                })
    except Exception:
        pass
    return findings


def mine_custom_skills() -> list[dict]:
    """Detect skills installed locally that aren't in the hermes-cortex repo.

    Agents develop their own skills. If they're not in the repo, they're
    invisible to the fleet. This finds them and surfaces them for review.
    """
    findings = []
    local_skills = Path.home() / ".hermes-cortex" / "skills" / "software-development"
    repo_skills = REPO_ROOT / "src" / "skills" / "software-development"

    if not local_skills.exists():
        return findings

    # Get list of skills in the repo (for cross-reference)
    repo_skill_names = set()
    if repo_skills.exists():
        for d in repo_skills.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                repo_skill_names.add(d.name)

    # Scan local skills for ones not in the repo
    for skill_dir in sorted(local_skills.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name in repo_skill_names:
            continue  # already in repo, skip

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            text = skill_md.read_text(encoding="utf-8", errors="replace")

            # Extract metadata
            name = ""
            desc = ""
            version = ""
            for line in text.split("\n")[:20]:
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()[:80]
                elif line.startswith("version:"):
                    version = line.split(":", 1)[1].strip()

            findings.append({
                "type": "custom_skill",
                "skill": skill_dir.name,
                "name": name or skill_dir.name,
                "description": desc,
                "version": version,
                "confidence": "medium",
                "score": 0,
                "content": text,  # full SKILL.md for Moses to evaluate
            })
        except Exception:
            continue

    return findings


# ── Scoring ────────────────────────────────────────────────────

def score_finding(finding: dict) -> float:
    """Score a finding 0-10 using nomic embedding + heuristics."""
    conf = {"high": 7.0, "medium": 5.0, "low": 2.0}
    base = conf.get(finding.get("confidence", "low"), 2.0)

    # Nomic boost: embed the finding text and check semantic density
    text_for_embed = json.dumps(finding, default=str)[:1000]
    emb = embed(text_for_embed)
    if emb:
        magnitude = sum(x * x for x in emb) ** 0.5
        base += min(3.0, magnitude / 10.0)  # semantic richness bonus

    # Type-specific boosts
    if finding.get("type") == "tdd_pattern":
        base += min(2.0, finding.get("improvement", 0) * 0.3)
    if finding.get("type") == "session_pattern":
        base += min(1.0, len(finding.get("clues", [])) * 0.3)
    if finding.get("type") == "memory_pattern":
        base += min(1.0, finding.get("key_terms", 0) * 0.2)

    return round(min(10.0, base), 1)


# ── Inbox Notification ─────────────────────────────────────────

def send_to_moses(findings: list[dict]):
    """Send top findings to Moses via agent inbox."""
    agent_name = os.environ.get("HERMES_AGENT", os.environ.get("USER", "unknown"))

    top = sorted(findings, key=lambda x: x.get("score", 0), reverse=True)[:5]
    if not top:
        return

    body_parts = [
        f"🤖 skill-miner report from {agent_name}",
        f"",
        f"Top {len(top)} findings (of {len(findings)} total):",
        f"",
    ]
    for f in top:
        icon = "✅" if f["score"] >= 7.0 else "📝"
        t = f.get("type", "?").ljust(18)
        item = f.get("task", f.get("file", f.get("confidence", "?")))
        body_parts.append(f"  {icon} [{t}] {item} — score={f['score']}")

        # For custom skills, include full SKILL.md content
        if f.get("type") == "custom_skill" and f.get("content"):
            content = f["content"]
            if len(content) > 3000:
                content = content[:3000] + "\n... [truncated — full file on agent machine]"
            body_parts.append(f"```markdown\n{content}\n```")

    try:
        data = urllib.parse.urlencode({
            "from": agent_name,
            "topic": "moses",
            "subject": f"skill-miner: {len(top)} findings from {agent_name}",
            "priority": "normal",
            "body": "\n".join(body_parts),
        }).encode()
        req = urllib.request.Request(INBOX_SEND_PATH, data, send_headers())
        urllib.request.urlopen(req, timeout=5)
        print(f"  ✓ Sent {len(top)} findings to Moses via inbox")
    except Exception as e:
        print(f"  ⚠ Could not reach inbox ({e}) — findings saved locally")


# ── Main ───────────────────────────────────────────────────────

def main():
    print(f"═ Skill Miner — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ═")
    print()

    all_findings = []

    print("  Mining loop governance DB…")
    all_findings.extend(mine_loop_db())

    print("  Mining session history…")
    all_findings.extend(mine_sessions())

    print("  Mining agent memory…")
    all_findings.extend(mine_memory())

    print("  Checking for custom skills not in repo…")
    all_findings.extend(mine_custom_skills())

    for f in all_findings:
        f["score"] = score_finding(f)

    all_findings.sort(key=lambda x: x["score"], reverse=True)

    auto = [f for f in all_findings if f["score"] >= 7.0]
    review = [f for f in all_findings if 4.0 <= f["score"] < 7.0]
    discard = [f for f in all_findings if f["score"] < 4.0]

    print(f"\n  Results: {len(auto)} auto-apply, {len(review)} review, {len(discard)} discarded")
    print()

    for f in all_findings[:10]:
        icon = "✅" if f["score"] >= 7.0 else "📝" if f["score"] >= 4.0 else "⏭"
        item = f.get("task", f.get("file", "?"))
        print(f"  {icon} [{f['type']:<18}] {item:<30} score={f['score']}")

    # Send top findings to Moses
    print()
    send_to_moses(all_findings)

    # Save local report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": os.environ.get("HERMES_AGENT", os.environ.get("USER", "unknown")),
        "total": len(all_findings),
        "auto_apply": len(auto),
        "needs_review": len(review),
        "discarded": len(discard),
        "findings": all_findings,
    }
    HERMES_DATA.mkdir(parents=True, exist_ok=True)
    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"  Local report: {REPORT_FILE}")
    print()


if __name__ == "__main__":
    main()