#!/usr/bin/env python3
"""autonomy-classifier.py — O4-S1 shadow-mode autonomy classifier (HC gaps party 2026-08-21).

Deterministic capability table (operation -> class -> gate). NEVER an LLM
judgment. Deny-by-default: only exact allowlisted operations auto-approve;
destructive/irreversible operations stay gated by definition + human confirm.

Shadow mode: this script only CLASSIFIES and REPORTS. It enforces nothing.
The replay mode reads the loop-governance DB (golden cycles + Luke's feedback)
and computes precision/recall on the destructive class vs his actual decisions,
per the party resolution:
  "O4 ships in shadow mode first — replay the classifier against the golden
   cycles + feedback entries (precision/recall vs Luke's actual decisions).
   ... Expand the allowlist only on >=99% precision on the destructive class."

Usage:
  autonomy-classifier.py --classify <operation>   # single classification (test)
  autonomy-classifier.py --replay [--db PATH]     # shadow replay + metrics
  autonomy-classifier.py --replay --ledger        # + append tamper-evident ledger line

Kill switch:  AUTONOMY_CLASSIFIER_KILL=1 (env) or --kill -> exit 0, no output.
              Fail-closed: if the switch is set, ALL classification is off.

Exit codes:
  0 — clean (report produced, or killed)
  2 — usage/DB error

Metrics (documented):
  needed_human  = cycles where user_overrode == 1 (Luke corrected the loop)
  auto          = cycles the classifier would auto-approve (routine allowlist)
  gated         = cycles the classifier would gate (destructive/unknown)
  Precision(destructive) = |gated ∩ needed_human| / |gated|
  Recall(destructive)    = |gated ∩ needed_human| / |needed_human|
  The naive baseline (gate nothing) has precision 0 and recall 0 — gating
  nothing catches no overrides; that is the party's "99.9% naive accuracy"
  warning, measured.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

CORTEX_HOME = Path(os.environ.get("CORTEX_HOME", str(Path.home() / ".hermes-cortex")))
DEFAULT_DB = CORTEX_HOME / "data" / "loop-governance.db"
LEDGER = CORTEX_HOME / "state" / "autonomy-shadow-ledger.jsonl"

# ---------------------------------------------------------------------------
# Capability table — deterministic, deny-by-default.
# Order matters: DESTRUCTIVE is checked FIRST (fail-closed), then ROUTINE,
# then anything unmatched is GATED (unknown = destructive by default).
# ---------------------------------------------------------------------------

DESTRUCTIVE_PATTERNS: list[str] = [
    # force / bypass / override
    r"force", r"bypass", r"no-verify", r"skip[-_]?score", r"override",
    r"no[-_]?agents?" ,  # skip-governance style flags
    # git history / destructive git
    r"push\s*--?force", r"push\s+-f\b", r"force-push", r"reset\s*--?hard",
    r"clean\s*-f", r"filter-branch", r"rewrite", r"rebase\s*--?i", r"cherry-pick",
    r"branch\s*-[dD]", r"update-ref", r"delete.*(branch|tag)", r"prune",
    # filesystem / data loss
    r"rm\s*-rf", r"rm\s*-r\b", r"destroy", r"wipe", r"purge", r"truncate",
    r"drop\s+(table|database|schema|column)", r"delete\s+from",
    r"mkfs|fdisk|mkswap", r"format\s", r"dd\s+of=",
    # config / protected-file overwrite
    r"overwrite", r"overwrite-config", r"agents\.md\s*$", r"prune-apply",
    r"chattr|chown|chmod\s+-R", r"sudoers", r"nginx\s*\.conf", r"blocked_ips",
    # fleet / cross-host / external side effects
    r"fleet-git-reset", r"kill-switch", r"killswitch", r"dispatch", r"\bEXEC\b",
    r"ssh\s+", r"scp\s", r"rsync", r"deploy", r"publish", r"release", r"submit",
    r"cronjob\s+(create|update|remove|delete)", r"crontab\s+-",
    r"usermod|groupmod|useradd|groupadd|passwd",
    r"ufw\s+(enable|disable|allow|deny|reject|reset)", r"iptables",
    r"docker\s+(system\s+prune|rmi|rm\b|compose\s+down\s+-v)",
    # secrets
    r"secret", r"credential", r"token", r"api[-_]?key", r"password",
]

ROUTINE_PATTERNS: list[str] = [
    # governance scoring cycles (read-only scoring, already gated by enforcer)
    r"^precommit", r"^commit-", r"pre-commit", r"score",
    # read-only checks / diagnostics / audits
    r"doctor", r"diagnostic", r"health", r"audit", r"check", r"verify",
    r"scan", r"remediate", r"survey",
    # reporting / digests / briefings (read-only)
    r"report", r"digest", r"briefing", r"cost", r"bible", r"dream", r"lesson",
    r"skill-lifecycle", r"learning", r"session", r"regression-gate",
    # polling / bus reads
    r"inbox", r"bus-tick", r"poll", r"status", r"list", r"watch",
    # pulls (non-force) / update coordination
    r"pull", r"update-no-verify", r"cortex-pull", r"update-check",
    # orchestrator backlog driver (report loop)
    r"backlog",
]

KILL_ENV = "AUTONOMY_CLASSIFIER_KILL"


def classify(operation: str) -> dict:
    """Classify an operation string -> {class, gate, matched_pattern}.

    Deny-by-default: destructive patterns checked first; then routine
    allowlist; anything unmatched is GATED (destructive/unknown).
    """
    op = (operation or "").lower()
    for pat in DESTRUCTIVE_PATTERNS:
        if re.search(pat, op):
            return {"class": "destructive", "gate": "human", "matched": pat}
    for pat in ROUTINE_PATTERNS:
        if re.search(pat, op):
            return {"class": "routine", "gate": "auto", "matched": pat}
    return {"class": "destructive", "gate": "human", "matched": "<deny-by-default>"}


# ---------------------------------------------------------------------------
# Shadow replay
# ---------------------------------------------------------------------------

def replay(db_path: Path, with_ledger: bool = False) -> dict:
    if not db_path.exists():
        raise FileNotFoundError(f"loop-governance DB not found: {db_path}")

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = con.cursor()
    rows = cur.execute(
        "SELECT id, task_id, decision, user_overrode, outcome_note "
        "FROM loop_cycles"
    ).fetchall()
    con.close()

    total = len(rows)
    needed_human = 0          # user_overrode == 1 (Luke corrected the loop)
    auto = 0                  # classifier would auto-approve
    gated = 0                 # classifier would gate
    caught = 0                # gated AND needed_human
    missed: list[dict] = []   # auto (would pass) AND needed_human  -> FN
    # Override-kind split: hygiene overrides are stale-leak auto-resolutions
    # (the PENDING-cycle watchdog resolving an abandoned session) — they
    # record NO operation judgment and must not count as destructive-class
    # evidence. Judgment overrides are genuine human calls on the operation.
    # Phrase-level markers only — bare words like "stale" appear inside
    # quoted regex descriptions in judgment notes (e.g. 'stale' regex match).
    HYGIENE_MARKERS = (
        "auto-resolved", "stale leak", ">24h stale", "abandoned",
        "orphan", "ended without scoring",
    )
    hygiene_overrides = 0
    judgment_overrides = 0
    judgment_caught = 0

    for cid, task_id, decision, overrode, note in rows:
        op = task_id or ""
        cls = classify(op)
        is_human = overrode == 1
        if is_human:
            needed_human += 1
            n = (note or "").lower()
            if any(m in n for m in HYGIENE_MARKERS):
                hygiene_overrides += 1
            else:
                judgment_overrides += 1
        if cls["gate"] == "auto":
            auto += 1
            if is_human:
                missed.append({"cycle": cid, "task_id": task_id,
                               "decision": decision, "note": (note or "")[:120]})
        else:
            gated += 1
            if is_human:
                caught += 1
                n = (note or "").lower()
                if not any(m in n for m in HYGIENE_MARKERS):
                    judgment_caught += 1

    precision = caught / gated if gated else 0.0
    recall = caught / needed_human if needed_human else 0.0
    jprecision = judgment_caught / gated if gated else 0.0
    jrecall = judgment_caught / judgment_overrides if judgment_overrides else 0.0

    result = {
        "db": str(db_path),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_cycles": total,
        "needed_human_overrides": needed_human,
        "override_kinds": {
            "hygiene_auto_resolved": hygiene_overrides,
            "judgment": judgment_overrides,
        },
        "classifier_auto": auto,
        "classifier_gated": gated,
        "destructive_class": {
            "true_positives": caught,
            "false_negatives": len(missed),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "judgment_precision": round(jprecision, 4),
            "judgment_recall": round(jrecall, 4),
            "gate_nothing_baseline_precision": 0.0,
            "gate_nothing_baseline_recall": 0.0,
        },
        "missed_overrides": missed,
    }

    if with_ledger:
        line = json.dumps(result, sort_keys=True)
        h = hashlib.sha256(line.encode()).hexdigest()[:16]
        prev = ""
        if LEDGER.exists():
            prev = LEDGER.read_text().strip().splitlines()[-1].split("|")[-1]
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}|{h}|{prev}|{line}\n")
        result["ledger"] = {"path": str(LEDGER), "hash": h, "prev_hash": prev}

    return result


def format_report(r: dict) -> str:
    d = r["destructive_class"]
    k = r.get("override_kinds", {})
    lines = [
        "O4-S1 autonomy classifier — SHADOW replay report",
        f"  DB:            {r['db']}",
        f"  generated:     {r['generated_at']}",
        f"  total cycles:  {r['total_cycles']}",
        f"  Luke overrode: {r['needed_human_overrides']} "
        f"(judgment {k.get('judgment', 0)} / hygiene-auto-resolved {k.get('hygiene_auto_resolved', 0)})",
        f"  classifier:    {r['classifier_auto']} auto-approve / {r['classifier_gated']} gated",
        f"  destructive class:",
        f"    TP (gated ∩ overridden): {d['true_positives']}",
        f"    FN (auto but overridden): {d['false_negatives']}",
        f"    precision: {d['precision']:.2%}   (target >=99% to expand allowlist)",
        f"    recall:    {d['recall']:.2%}",
        f"    judgment-only precision: {d['judgment_precision']:.2%}",
        f"    judgment-only recall:    {d['judgment_recall']:.2%}",
        f"    gate-nothing baseline: precision 0.00%, recall 0.00%",
    ]
    if d["false_negatives"]:
        lines.append("  MISSED overrides (would have auto-approved):")
        for m in r["missed_overrides"]:
            lines.append(f"    cycle {m['cycle']} {m['task_id']!r} ({m['decision']})")
    if r.get("ledger"):
        lines.append(f"  ledger:        {r['ledger']['path']} (sha256:{r['ledger']['hash']})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="O4-S1 shadow-mode autonomy classifier")
    ap.add_argument("--classify", metavar="OPERATION", help="classify one operation string")
    ap.add_argument("--replay", action="store_true", help="shadow replay vs loop-governance DB")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="loop-governance DB path")
    ap.add_argument("--ledger", action="store_true", help="append tamper-evident ledger line")
    ap.add_argument("--kill", action="store_true", help="kill switch: no-op exit 0")
    args = ap.parse_args(argv)

    if args.kill or os.environ.get(KILL_ENV) == "1":
        return 0  # kill switch — fail closed, no classification

    if args.classify:
        r = classify(args.classify)
        print(json.dumps(r, indent=2))
        return 0

    if args.replay:
        try:
            rep = replay(Path(args.db), with_ledger=args.ledger)
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        print(format_report(rep))
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
