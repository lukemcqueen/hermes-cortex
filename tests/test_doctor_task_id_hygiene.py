#!/usr/bin/env python3
"""Guard for the doctor's task-id hygiene signal (issue #188).

The doctor must TELL a host its ledger holds ids no classifier can group, and name
the repair path — without ever rewriting a ledger itself. This drives all four
branches of that check against fixture ledgers, in a subprocess with HOME redirected
so nothing can touch the real DB.

Run: python3 tests/test_doctor_task_id_hygiene.py
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECKS_DIR = REPO / "ops" / "scripts" / "manage"   # holds the cortex_doctor package
NL = chr(10)
MALFORMED = f"precommit-repo-HEAD{NL}unknown/update"

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)


PROBE = '''
# Import as a PACKAGE: checks.py uses relative imports (from .immutability import …),
# so loading the file by path raises "attempted relative import with no known parent".
import sys
sys.path.insert(0, sys.argv[1])
from cortex_doctor import checks as mod

class Stub:
    def __init__(self):
        self.entries = []
    def add(self, name, status, detail="", fix=""):
        self.entries.append((status, detail, fix))

res = Stub()
mod.check_task_id_hygiene(res)
for status, detail, fix in res.entries:
    print(f"STATUS={status}")
    print(f"DETAIL={detail}")
    print(f"FIX={fix}")
'''


def run_check(rows: list[str] | None) -> dict:
    """rows=None means 'no ledger at all'."""
    tmp = Path(tempfile.mkdtemp(prefix="taskidhyg-"))
    try:
        home = tmp / "home"
        data = home / ".hermes-cortex" / "data"
        data.mkdir(parents=True)
        if rows is not None:
            con = sqlite3.connect(data / "loop-governance.db")
            con.execute("CREATE TABLE loop_cycles (id INTEGER PRIMARY KEY, task_id TEXT)")
            con.executemany("INSERT INTO loop_cycles (task_id) VALUES (?)", [(r,) for r in rows])
            con.commit()
            con.close()
        probe = tmp / "probe.py"
        probe.write_text(PROBE)
        proc = subprocess.run(
            [sys.executable, str(probe), str(CHECKS_DIR)],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "HOME": str(home)},
        )
        out = proc.stdout
        if proc.returncode != 0:
            return {"error": (proc.stderr or out)[-400:]}
        return {
            "status": next((l.split("=", 1)[1] for l in out.splitlines()
                            if l.startswith("STATUS=")), ""),
            "detail": next((l.split("=", 1)[1] for l in out.splitlines()
                            if l.startswith("DETAIL=")), ""),
            "fix": next((l.split("=", 1)[1] for l in out.splitlines()
                         if l.startswith("FIX=")), ""),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_malformed_ids_warn_and_name_the_repair() -> None:
    r = run_check([MALFORMED, "clean-task/one", "precommit-hermes-cortex-main/fix"])
    check("error" not in r, f"the probe failed: {r.get('error')}")
    check(r.get("status") == "WARN",
          f"a ledger holding a newline id must WARN, got {r.get('status')!r}")
    check("1 task id" in r.get("detail", "") and "control character" in r.get("detail", ""),
          f"the detail must count the offending ids: {r.get('detail')!r}")
    check("normalize-precommit-task-ids.py" in r.get("fix", ""),
          f"the remedy must name the repair tool: {r.get('fix')!r}")
    check("dry run" in r.get("fix", ""),
          "the remedy must say to dry-run first (this rewrites an audit trail)")


def test_clean_ledger_passes() -> None:
    r = run_check(["clean-task/one", "precommit-hermes-cortex-main/fix"])
    check(r.get("status") == "PASS",
          f"a clean ledger must PASS, got {r.get('status')!r}: {r.get('detail')!r}")
    check("spaces" not in r.get("detail", ""),
          "no space note belongs on a ledger without spaces")


def test_space_only_ids_pass_with_a_note_not_a_warning() -> None:
    """An agent-authored 'orch-backlog-driver run' is not this defect.

    Warning about it would be permanent noise on hosts that have one and no tool
    can safely rewrite it, which trains readers to ignore the check.
    """
    r = run_check(["orch-backlog-driver run", "clean-task/one"])
    check(r.get("status") == "PASS",
          f"space-only ids must not warn, got {r.get('status')!r}: {r.get('detail')!r}")
    check("agent-authored" in r.get("detail", ""),
          f"the space case must be NAMED as not-this-defect: {r.get('detail')!r}")


def test_absent_ledger_skips() -> None:
    r = run_check(None)
    check(r.get("status") == "SKIP",
          f"no ledger must SKIP, got {r.get('status')!r}: {r.get('detail')!r}")


def main() -> int:
    test_malformed_ids_warn_and_name_the_repair()
    test_clean_ledger_passes()
    test_space_only_ids_pass_with_a_note_not_a_warning()
    test_absent_ledger_skips()
    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS: task-id hygiene check warns on un-groupable ids, names the repair, and stays quiet otherwise")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
