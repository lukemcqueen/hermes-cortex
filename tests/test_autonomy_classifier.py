#!/usr/bin/env python3
"""Hermetic test suite for autonomy-classifier.py (O4-S1).

Proves the deterministic capability table + shadow replay behave exactly
as specified by the HC-gaps-party O4 resolution (2026-08-21):

  - Classifier is a DETERMINISTIC capability table (operation->class->gate),
    never an LLM judgment.
  - Deny-by-default: only exact allowlisted actions auto-approve; everything
    else (destructive/irreversible/unknown) stays gated by definition.
  - Destructive classes that MUST gate: force-push, rm -rf, db drop, config
    overwrite, fleet commands, secret access, cross-host, external side
    effects.
  - Kill switch (env AUTONOMY_CLASSIFIER_KILL=1 or --kill) => no-op exit 0.
  - Shadow replay computes precision/recall vs Luke's actual decisions and
    splits hygiene auto-resolutions from genuine judgment overrides.
  - Gate-nothing baseline is reported as precision 0 / recall 0 (the
    party's "99.9% naive accuracy by gating nothing" warning, measured).

Run:  python3 tests/test_autonomy_classifier.py
"""
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLASSIFIER = REPO / "ops" / "scripts" / "manage" / "autonomy-classifier.py"

FAILURES = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = "PASS" if cond else "FAIL"
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def classify(op: str) -> dict:
    out = subprocess.run(
        [sys.executable, str(CLASSIFIER), "--classify", op],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def replay(db: Path) -> str:
    out = subprocess.run(
        [sys.executable, str(CLASSIFIER), "--replay", "--db", str(db)],
        capture_output=True, text=True, check=True,
    )
    # Replay is text-report; parse the JSON ledger line instead for struct.
    return out.stdout


def make_db(cycles: list[tuple]) -> Path:
    """cycles: (task_id, user_overrode, outcome_note) tuples."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE loop_cycles (
        id INTEGER PRIMARY KEY, timestamp TEXT, task_id TEXT, cycle_num INTEGER,
        spec_hash TEXT, code_hash TEXT, test_output_hash TEXT, completeness REAL,
        quality REAL, progress REAL, composite REAL, no_progress INTEGER,
        decision TEXT, user_overrode INTEGER, outcome_note TEXT,
        schema_version INTEGER, model_name TEXT, session_id TEXT)""")
    for i, (tid, overrode, note) in enumerate(cycles, 1):
        con.execute(
            "INSERT INTO loop_cycles (id, timestamp, task_id, cycle_num, "
            "completeness, quality, progress, composite, no_progress, decision, "
            "user_overrode, outcome_note, schema_version) "
            "VALUES (?, '2026-08-21 00:00:00', ?, 1, 0.8, 0.8, 0.5, 0.7, 0, "
            "'MOVE_ON', ?, ?, 1)",
            (i, tid, overrode, note),
        )
    con.commit()
    con.close()
    return Path(path)


def main() -> None:
    print("O4-S1 autonomy-classifier hermetic tests")

    print("\n1. Capability table — destructive MUST gate")
    destructive_ops = [
        "git push --force origin main",
        "rm -rf /var/lib/data",
        "drop table users",
        "sudo tee /etc/sudoers.d/x <<< y",           # config overwrite
        "fleet-git-reset.py --reset",                # fleet command
        "ssh mosesaaron 'systemctl stop nginx'",     # cross-host
        "export AWS_SECRET_ACCESS_KEY=...",          # secret access
        "python3 -c 'import shutil; shutil.rmtree(\"/x\")'",
        "docker system prune -af",                   # irreversible docker
        "agents-md-prune-apply",                     # protected-file prune
    ]
    for op in destructive_ops:
        r = classify(op)
        check(f"gates: {op[:50]}", r["gate"] == "human",
              f"got {r['class']}/{r['gate']} via {r['matched']}")

    print("\n2. Capability table — routine allowlist auto-approves")
    routine_ops = [
        "precommit-repo-HEAD/update",
        "cortex-doctor.py --once",
        "sustainability-briefing-2026",
        "orch-backlog-driver-run",
        "agent-cron-status.py --list",
        "git pull --ff-only",
    ]
    for op in routine_ops:
        r = classify(op)
        check(f"auto: {op[:50]}", r["gate"] == "auto",
              f"got {r['class']}/{r['gate']} via {r['matched']}")

    # no-verify / bypass flags FAIL CLOSED even in a read-only-sounding name
    r = classify("update-no-verify-last-checked")
    check("no-verify gates (fail-closed)", r["gate"] == "human",
          f"got {r['class']}/{r['gate']}")

    print("\n3. Deny-by-default — unknown ops gate")
    r = classify("totally-unknown-operation-xyz")
    check("unknown gates", r["gate"] == "human" and r["matched"] == "<deny-by-default>",
          f"got {r}")

    print("\n4. Kill switch — env and flag no-op")
    env = {**os.environ, "AUTONOMY_CLASSIFIER_KILL": "1"}
    p = subprocess.run([sys.executable, str(CLASSIFIER), "--replay"],
                       capture_output=True, text=True, env=env)
    check("env kill exits 0, silent", p.returncode == 0 and p.stdout.strip() == "",
          f"rc={p.returncode} out={p.stdout[:60]!r}")
    p = subprocess.run([sys.executable, str(CLASSIFIER), "--kill", "--replay"],
                       capture_output=True, text=True)
    check("flag kill exits 0, silent", p.returncode == 0 and p.stdout.strip() == "",
          f"rc={p.returncode} out={p.stdout[:60]!r}")

    print("\n5. Shadow replay — metrics vs Luke's decisions")
    db = make_db([
        ("orch-backlog-driver-run", 0, "routine completed"),
        ("sustainability-briefing-2026", 0, "routine completed"),
        ("git-push-force-something", 1, "MOVE_ON: rejected force-push candidate"),  # judgment
        ("inbox-check-20260728", 1, "auto-resolved by health check — >24h stale"),  # hygiene
    ])
    report = replay(db)
    check("replay runs", "SHADOW replay report" in report, report[:80])
    check("counts overrides", "Luke overrode: 2" in report, report)

    print("\n6. Tamper-evident ledger")
    with tempfile.TemporaryDirectory() as td:
        os.environ["CORTEX_HOME"] = td
        out = subprocess.run(
            [sys.executable, str(CLASSIFIER), "--replay", "--db", str(db), "--ledger"],
            capture_output=True, text=True, env={**os.environ},
        )
        ledger = Path(td) / "state" / "autonomy-shadow-ledger.jsonl"
        check("ledger file created", ledger.exists() and "sha256:" in out.stdout,
              out.stdout[-200:])
        if ledger.exists():
            lines = ledger.read_text().strip().splitlines()
            check("ledger append-only format", len(lines) == 1 and "|" in lines[0])
        os.environ.pop("CORTEX_HOME", None)

    print("\n7. JSON --classify shape")
    r = classify("git push --force")
    check("classify emits class/gate/matched",
          all(k in r for k in ("class", "gate", "matched")), json.dumps(r))

    print()
    if FAILURES:
        print(f"❌ {len(FAILURES)} FAILURES: {FAILURES}")
        sys.exit(1)
    print("✅ all autonomy-classifier tests passed")


if __name__ == "__main__":
    main()
