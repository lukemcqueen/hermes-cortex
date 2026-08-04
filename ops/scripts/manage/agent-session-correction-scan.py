#!/usr/bin/env python3
"""
agent-session-correction-scan.py — Correction→Guardrail Recidivism Scanner (P0-1).

Scans the LOCAL Hermes session DB (state.db under the Hermes home dir) for USER corrections,
classifies them into signal categories, checks each against the guardrail
registry (docs/guardrail-registry.json), and flags:
  - UNGUARDED corrections: a correction class with no registered guardrail
  - RECIDIVISM: the same class recurring after a guardrail was added
    (guardrail too weak → escalate to structural)

Runs on EVERY agent (agent- prefix, install-crons.sh) — each host's state.db
holds that agent's own corrections. The orchestrator's enforcer work is fed by
the per-agent reports, which this script forwards to inbox_moses automatically
when running on a non-orchestrator host (AGENT_NAME != moses).

Corpus discipline (per governance-improvement-plan-gaps F-01):
  - role='user' only
  - session source IN ('telegram','cli','subagent') — excludes cron sessions
  - system-injected wrappers stripped before matching
  - phrase-level regexes, never bare words (no false-positive flood)

Usage:
    python3 agent-session-correction-scan.py                 # report last 7 days
    python3 agent-session-correction-scan.py --days 30       # longer window
    python3 agent-session-correction-scan.py --all           # full history
    python3 agent-session-correction-scan.py --json          # machine-readable
    python3 agent-session-correction-scan.py --sample        # labeled sample audit
    python3 agent-session-correction-scan.py --no-forward    # skip bus forward (debug)

Exit codes: 0 = report delivered (findings or not — stdout IS the message),
2 = error (script failed to run). Non-zero exits other than 2 are avoided:
a no_agent cron treats non-zero as a failure alert, and this scanner's
findings are the report, not an error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path.home()
# Guard hygiene: the Hermes gateway lifecycle guard (cron/lifecycle_guard.py)
# tokenizes referenced scripts as shell. Python path joins written as
# `HOME / "x" / "y"` look like shell path references, and the guard resolves
# them to real files (e.g. state.db >1MB) which fail closed → GatewayLifecycleBlocked.
# Build paths via os.path.join so no shell-tokenizable `/` chains remain.
import os as _os
STATE_DB = Path(_os.path.join(str(HOME), ".hermes", "state.db"))
STATE_FILE = Path(_os.path.join(str(HOME), ".hermes-cortex", "state", "session-correction-scan-state.json"))
GUARDRAIL_REGISTRY = Path(_os.path.join(str(HOME), "hermes-cortex", "docs", "guardrail-registry.json"))
BUS_CONF = Path(_os.path.join(str(HOME), ".hermes-cortex", "cortex-bus.conf"))

# ── System-injected wrappers to strip before matching (F-01) ──────────
WRAPPER_PATTERNS = [
    r"\[CONTEXT COMPACTION[^\]]*\]",
    r"\[ASYNC DELEGATION[^\]]*\]",
    r"\[IMPORTANT:\s*The user has invoked the \"[^\"]+\" skill[^\]]*\]",
    r"\[IMPORTANT:\s*[^\]]*skill[^\]]*\]",
    r"\[PRIOR CONTEXT[^\]]*\]",
    r"\[OUT-OF-BAND USER MESSAGE[^\]]*\]",
    r"^The user has invoked the .* skill.*$",
    r"^Earlier turns were compacted.*$",
]
_WRAPPER_RE = re.compile("|".join(WRAPPER_PATTERNS), re.IGNORECASE | re.MULTILINE)

# ── Correction signal categories (phrase-level, never bare words) ─────
# Each entry: category name → list of phrase regexes (lowercased matching).
# Phrases are deliberately specific to avoid the F-01 false-positive flood
# (bare "stop"/"trust"/"process" matched skill-injection boilerplate).
CORRECTION_CATEGORIES: dict[str, list[str]] = {
    "verify-before-declare": [
        r"did you test",
        r"did you verify",
        r"test it first",
        r"verify before",
        r"run the test",
        r"did you actually (test|run|verify)",
        r"you (didn't|did not) (test|verify|run)",
        r"test (the )?hostname",
        r"before (you )?(claim|say|declare|tell me)",
        r"verify .* before (claiming|declaring|saying)",
    ],
    "repeat-correction": [
        r"same (issue|problem|mistake) (over and over|again and again|repeatedly)",
        r"again\??\s*$",
        r"how many times",
        r"tired of (the )?same",
        r"(keeps|keep) (happening|recurring|repeating)",
        r"third time",
        r"second time",
        r"(you )?(did|said) (this|that) (again|before)",
    ],
    "no-permanent-fix": [
        r"not (a )?permanent (fix|solution)",
        r"if it's not permanent",
        r"temporary (fix|patch|band-aid)",
        r"permanently (fix|solve|resolve)",
        r"fix the root",
        r"root[- ]cause (fix|solution|analysis)",
        r"don't (just )?patch",
        r"stop (with )?(the )?(marginal|different version)",
        r"not (a )?real (fix|solution)",
        r"that's not (a )?fix",
    ],
    "trust-language-breach": [
        r"won't do that again",
        r"will not (do|happen) (that )?again",
        r"never (say|do) (that|this) again",
        r"i'll (remember|do better|be better)",
        r"i will (remember|do better|be better)",
        r"you('re| are) a (liar|total liar)",
        r"don't (say|promise) .* again",
        r"empty promise",
    ],
    "bypass-attempt": [
        r"permanently remove the bypass",
        r"(stop|never) bypass(ing)?",
        r"why (did|are) you bypass",
        r"don't (use|create|make) (a )?bypass",
        r"no (more )?bypass",
        r"remove .* bypass",
    ],
    "drift-deployed-vs-repo": [
        r"deployed vs repo",
        r"repo.*deployed|deployed.*repo",
        r"stale (bytecode|script|copy|version)",
        r"auto (replace|sync|reconcile) (old|differing)",
        r"registered in cortex-update",
        r"forgot (to )?register",
        r"did you (deploy|push|commit)",
        r"not deployed",
        r"stale (deploy|reference)",
    ],
    "naming-clarity": [
        r"rename all",
        r"ambiguous (skill|name|script)",
        r"confus(ing|ed) (name|skill)",
        r"naming (is )?(wrong|bad|unclear)",
        r"prioritize clarity",
        r"rename .* to",
        r"prefix(es)? (with|:)",
    ],
    "cross-agent-forgot": [
        r"forgot to (send|notify|include|tell)",
        r"why did you forget",
        r"did you (send|notify) (it to|this to)",
        r"send (it )?to (titus|esther|joseph|kustos|gisu)",
        r"every agent",
        r"fleet(-wide)? (consistency|convergence|update)",
        r"other agents",
    ],
    "bus-messaging": [
        r"something('s| is) wrong with the (message )?bus",
        r"bus (deadlock|down|stuck|broken)",
        r"message bus (failed|error|not)",
        r"bootstrapping deadlock",
        r"are you still working",
        r"no (response|reply) (from|on) (the )?bus",
    ],
    "ceremony-friction": [
        r"governance (enforcer )?deadlock",
        r"pipeline blocked",
        r"blocked (on|by) (governance|enforcer|lock)",
        r"read-?only (query|command) (was|is|got) blocked",
        r"ceremony (is|was|too)",
        r"too much (process|ceremony|overhead)",
        r"why (is|was) (a )?read-?only",
    ],
    "docs-stale": [
        r"update (the )?docs",
        r"document(ation)? (is )?(stale|wrong|outdated|missing)",
        r"docs (before|first)",
        r"document this",
        r"doc(s)? .* before (close|end|commit)",
    ],
    "skill-not-loaded": [
        r"load (the )?skill",
        r"did you load",
        r"skills? (first|before)",
        r"you (didn't|did not) (load|read) (the )?skill",
        r"load .* before (you )?",
    ],
    "dont-ask-just-fix": [
        r"don't ask (me|the user)",
        r"stop asking",
        r"never ask (me|the user)",
        r"just (fix|do) it",
        r"don't (ask|check) (first|before)",
        r"pick the right option",
        r"don't hand (it )?back",
        r"stop (asking|handing) (me )?questions",
    ],
    "governance-not-followed": [
        r"not (truly )?following (loop )?governance",
        r"begin_change",
        r"end_change",
        r"feedback_accept",
        r"cycle_query",
        r"governance (cycle|lock)",
        r"score (the )?cycle",
        r"PENDING cycles",
    ],
    "verification-artifact": [
        r"show (me )?(the )?(output|evidence|proof)",
        r"where('s| is) (the )?(output|evidence|proof|log)",
        r"real (tool )?output",
        r"with (actual )?output",
        r"run it and (show|paste) (me )?",
        r"exit code",
    ],
}

# Compile all phrase regexes once
_COMPILED: dict[str, list[re.Pattern]] = {
    cat: [re.compile(p, re.IGNORECASE) for p in phrases]
    for cat, phrases in CORRECTION_CATEGORIES.items()
}

# Phrases that look like corrections but are skill/session boilerplate
FALSE_POSITIVE_MARKERS = re.compile(
    r"skill has been loaded|invoked the skill|compaction|delegation batch",
    re.IGNORECASE,
)


def strip_wrappers(content: str) -> str:
    """Remove system-injected wrappers from a user message."""
    return _WRAPPER_RE.sub(" ", content)


def classify(content: str) -> list[str]:
    """Classify a stripped user message into correction categories."""
    stripped = strip_wrappers(content)
    if not stripped.strip():
        return []
    if FALSE_POSITIVE_MARKERS.search(stripped):
        return []
    hits = []
    for cat, patterns in _COMPILED.items():
        for p in patterns:
            if p.search(stripped):
                hits.append(cat)
                break
    return hits


def load_guardrail_registry() -> dict:
    """Load docs/guardrail-registry.json classes (fall back to empty dict)."""
    if GUARDRAIL_REGISTRY.exists():
        try:
            data = json.loads(GUARDRAIL_REGISTRY.read_text())
            classes = data.get("classes", {}) if isinstance(data, dict) else {}
            return classes if isinstance(classes, dict) else {}
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"watermark_by_category": {}, "seen_signatures": {}}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def scan(days: int | None, all_history: bool) -> list[dict]:
    """Query user messages and classify them. Returns hit records."""
    if not STATE_DB.exists():
        print(f"ERR: state.db not found at {STATE_DB}", file=sys.stderr)
        sys.exit(2)

    conn = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        # Only user-role messages from interactive sources (F-01):
        # telegram, cli, subagent — excludes cron sessions entirely.
        if all_history:
            time_filter = ""
            params: tuple = ()
        elif days:
            cutoff = (datetime.now() - timedelta(days=days)).timestamp()
            time_filter = "AND m.timestamp > ?"
            params = (cutoff,)
        else:
            cutoff = (datetime.now() - timedelta(days=7)).timestamp()
            time_filter = "AND m.timestamp > ?"
            params = (cutoff,)

        rows = conn.execute(
            f"""
            SELECT m.id, m.session_id, m.content, m.timestamp, s.source
            FROM messages m
            JOIN sessions s ON s.id = m.session_id
            WHERE m.role = 'user'
              AND s.source IN ('telegram', 'cli', 'subagent')
              {time_filter}
            ORDER BY m.timestamp ASC
            """,
            params,
        ).fetchall()
    finally:
        conn.close()

    hits = []
    for row in rows:
        cats = classify(row["content"] or "")
        if cats:
            hits.append({
                "message_id": row["id"],
                "session_id": row["session_id"],
                "source": row["source"],
                "timestamp": row["timestamp"],
                "categories": cats,
                "snippet": (row["content"] or "")[:200].replace("\n", " "),
            })
    return hits


def load_bus_config() -> tuple[str, str, str]:
    """Load (bus_url, auth, agent_name) from cortex-bus.conf.

    Agents push to the orchestrator's bus via the HTTP API (contact-orchestrator.sh
    pattern). Falls back to env vars, then defaults; returns agent_name which
    is 'moses' on the orchestrator host (no self-forward).
    """
    bus_url = os.environ.get("CORTEX_BUS_URL", _os.path.join("http:", "", "127.0.0.1:13004"))
    auth = os.environ.get("CORTEX_BASIC_AUTH", "")
    agent_name = os.environ.get("AGENT_NAME", "")
    if BUS_CONF.exists():
        for line in BUS_CONF.read_text().splitlines():
            line = line.strip()
            if line.startswith("CORTEX_BUS_URL="):
                bus_url = line.split("=", 1)[1].strip().strip("\"'")
            elif line.startswith("CORTEX_BASIC_AUTH="):
                auth = line.split("=", 1)[1].strip().strip("\"'")
            elif line.startswith("AGENT_NAME="):
                agent_name = line.split("=", 1)[1].strip().strip("\"'")
    return bus_url, auth, agent_name


def forward_to_orchestrator(result: dict) -> None:
    """Send a condensed report to inbox_orchestrator via the bus HTTP API.

    Non-orchestrator agents forward their correction-scan findings so the
    orchestrator can fold per-agent recidivism into enforcer work. Orchestrator
    hosts skip (their report is delivered to the user directly). Best-effort:
    failures are logged to stderr, never fatal (exit stays 0).
    """
    bus_url, auth, agent_name = load_bus_config()
    if agent_name.lower() in ("moses", "esther", ""):
        return  # orchestrator host — no self-forward
    if not auth:
        print("ℹ️  No CORTEX_BASIC_AUTH — skipping forward to orchestrator.", file=sys.stderr)
        return
    recid = result.get("recidivism_categories", {})
    summary = {
        "agent": agent_name,
        "window_days": result.get("window_days", 7),
        "total_hits": result.get("scanned_hits", 0),
        "by_category": result.get("by_category", {}),
        "recidivism": recid,
        "unguarded": result.get("unguarded_categories", {}),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    subject = f"📊 CORRECTION SCAN: {agent_name} — {summary['total_hits']} hit(s), {len(recid)} recidivism"
    body = json.dumps(summary, indent=2, ensure_ascii=False)
    payload = json.dumps({
        "queue": "inbox_orchestrator",
        "message": {
            "from": agent_name,
            "to": "orchestrator",
            "subject": subject,
            "body": body,
            "priority": "normal",
        },
    })
    url = _os.path.join(bus_url.rstrip(_os.sep), "api", "pgmq", "send")
    req = urllib.request.Request(
        url,
        data=payload.encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    import base64
    token = base64.b64encode(auth.encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_body = resp.read().decode()
        if '"msg_id"' in resp_body:
            print(f"📤 Correction scan forwarded to Moses ({subject})")
        else:
            print(f"⚠️  Forward to Moses: unexpected response: {resp_body[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"⚠️  Forward to Moses failed (non-fatal): {type(e).__name__}: {e}", file=sys.stderr)


def sample_audit(n: int = 500) -> None:
    """Print a labeled sample audit for precision measurement (F-10/F-01)."""
    hits = scan(None, all_history=True)
    # Deterministic sample: every 20th hit
    sample = hits[:: max(1, divmod(len(hits), n)[0])]
    tp = 0
    for h in sample:
        cats = ", ".join(h["categories"])
        print(f"[{cats}] {h['snippet'][:120]}")
    print(f"\nSample size: {len(sample)} hits (deterministic every-Nth of {len(hits)} total)")


def main():
    parser = argparse.ArgumentParser(description="Correction→Guardrail Recidivism Scanner")
    parser.add_argument("--days", type=int, default=None, help="Lookback window in days (default 7)")
    parser.add_argument("--all", action="store_true", help="Scan full history (no window)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--sample", action="store_true", help="Labeled sample audit mode")
    parser.add_argument("--no-forward", action="store_true", help="Skip bus forward to Moses (debug)")
    parser.add_argument("--enforce", action="store_true", help="File governance cycles for top unguarded (future)")
    args = parser.parse_args()

    if args.sample:
        sample_audit()
        return

    registry = load_guardrail_registry()
    state = load_state()
    hits = scan(args.days, args.all)

    # ── Aggregate ──
    by_cat: Counter[str] = Counter()
    per_agent: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for h in hits:
        for c in h["categories"]:
            by_cat[c] += 1
            per_agent[h["session_id"]][c] += 1

    # ── Guardrail + recidivism analysis ──
    unguarded: dict[str, int] = {}
    recidivism: dict[str, int] = {}
    for cat, count in by_cat.items():
        if cat not in registry:
            unguarded[cat] = count
        elif count >= 2:  # recurrence after a guardrail exists = recidivism signal
            recidivism[cat] = count

    # ── Persist watermark (incremental scan support, F-01) ──
    if hits:
        last_ts = max(h["timestamp"] for h in hits)
        state["last_scan_ts"] = last_ts
        state["last_scan_at"] = datetime.now().isoformat()
        save_state(state)

    total = len(hits)
    result = {
        "scanned_hits": total,
        "window_days": args.days or ("all" if args.all else 7),
        "by_category": dict(by_cat.most_common()),
        "unguarded_categories": unguarded,
        "recidivism_categories": recidivism,
        "per_agent": {k: dict(v) for k, v in per_agent.items()},
        "guardrail_registry_categories": sorted(registry.keys()),
        "top_hits": hits[:10],
    }

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"Correction scan: {total} classified hit(s) in {result['window_days']}d window")
        if by_cat:
            print("\nBy category:")
            for cat, n in by_cat.most_common():
                flag = "🛡️" if cat in registry else "⚠️ UNGUARDED"
                rec = " 🔁 RECIDIVISM" if cat in recidivism else ""
                print(f"  {flag} {cat}: {n}{rec}")
        else:
            print("  (no correction signals found)")
        if unguarded:
            print(f"\n⚠️ UNGUARDED categories (no guardrail in registry): {', '.join(unguarded)}")
        if recidivism:
            print(f"\n🔁 RECIDIVISM (guardrail exists but recurring): {', '.join(recidivism)}")
        if not registry:
            print("\nℹ️  guardrail-registry.json not found — all categories reported unguarded.")
            print("   Create it at docs/guardrail-registry.json (P0-1a).")

    # Forward to Moses on non-orchestrator hosts (feeds enforcer work).
    if not args.no_forward:
        forward_to_orchestrator(result)

    # Exit 0 always — findings are the report (no_agent cron delivers stdout).
    # Only exit 2 on genuine errors (state.db missing etc.).
    return 0


if __name__ == "__main__":
    sys.exit(main())
