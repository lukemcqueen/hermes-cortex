#!/usr/bin/env python3
"""Dedup behavior suite for agent-no-verify-audit.py.

Regression test for the 2026-08-20 Telegram spam: the scoring-backlog and
escape-hatch sections printed the SAME reminder every 10-minute tick while
state was unchanged, so the no_agent cron delivered identical messages to
Telegram repeatedly (Luke report). Each section must fire only when its
CONTENT changes:

  A: old-format state + backlog(2 stale) + debt 5  -> both fire, state records
  B: identical env on next tick                    -> MUST stay silent
  C: debt 5->4                                     -> escape hatch re-fires only
  D: stable state again                            -> MUST stay silent
  E: backlog set changes (cycle replaced)          -> backlog re-fires
  F: backlog cleared                               -> silent + empty baseline
  G: same 2 cycles re-appear                       -> re-accumulation re-fires
  H: new --no-verify events                        -> section 1 still fires
  I: fresh env, no backlog                         -> silent, no crash
  J: fresh env with backlog                        -> fires once, then silent

Run:  python3 tests/test_no_verify_audit_dedup.py
Optional: NVA_AUDIT_PATH=/path/to/agent-no-verify-audit.py to test a
specific copy (e.g. the deployed one).
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import sys

SCRIPT = os.environ.get(
    "NVA_AUDIT_PATH",
    os.path.expanduser("~/hermes-cortex/ops/scripts/manage/agent-no-verify-audit.py"),
)
SANDBOX = "/tmp/nva-dedup-test"

STATE = f"{SANDBOX}/state.json"
DEBT = f"{SANDBOX}/debt.json"
LOG = f"{SANDBOX}/log.json"
LOOP_DB = f"{SANDBOX}/loop.db"

OLD_TS_A = "2026-08-19 08:06:15"
OLD_TS_B = "2026-08-19 10:31:53"


def load_mod():
    spec = importlib.util.spec_from_file_location("nva_audit", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.STATE_FILE = STATE
    mod.DEBT_FILE = DEBT
    mod.LOG_FILE = LOG
    mod.LOOP_DB = LOOP_DB
    return mod


def write(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f)


def init_loop(rows):
    if os.path.exists(LOOP_DB):
        os.remove(LOOP_DB)
    conn = sqlite3.connect(LOOP_DB)
    conn.execute("CREATE TABLE loop_cycles (task_id TEXT, timestamp TEXT, decision TEXT)")
    conn.executemany(
        "INSERT INTO loop_cycles (task_id, timestamp, decision) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()


def setup(state=None, debt=None, log=None, loop_rows=None):
    shutil.rmtree(SANDBOX, ignore_errors=True)
    os.makedirs(SANDBOX)
    if state is not None:
        write(STATE, state)
    if debt is not None:
        write(DEBT, debt)
    if log is not None:
        write(LOG, log)
    init_loop(loop_rows or [])


def read_state():
    with open(STATE) as f:
        return json.load(f)


def run(mod):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mod.main()
    return buf.getvalue().strip()


results = []


def expect(name, got, must_contain=None, must_be_empty=False):
    ok = bool((must_be_empty and got == "") or (must_contain and must_contain in got))
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name} -> {got[:90]!r}" if got else f"{'PASS' if ok else 'FAIL'}  {name} -> (silent)")


def expect_bool(name, ok, detail=""):
    results.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name} -> {detail}")


def main():
    mod = load_mod()

    # ── A: old-format state, backlog(2 stale) + debt 5 → both fire ──
    setup(
        state={"last_timestamp": None, "last_index": -1},
        debt={"consecutive_no_verify": 5},
        log=[],
        loop_rows=[("curate-skills-mcp-watchdog", OLD_TS_A, "PENDING"),
                   ("skill-sidekiq-job-operations", OLD_TS_B, "PENDING")],
    )
    out = run(mod)
    expect("A1 backlog fires first time", out, must_contain="SCORING BACKLOG: 2")
    expect("A2 escape hatch fires", out, must_contain="ESCAPE HATCH EXHAUSTED: 5")
    st = read_state()
    expect_bool("A3 state records backlog sig (2 entries)", len(st.get("last_backlog", [])) == 2, st.get("last_backlog"))
    expect_bool("A4 state records debt", st.get("last_debt") == 5, st.get("last_debt"))

    # ── B: identical env → silent ──
    out = run(mod)
    expect("B identical backlog+debt stays silent", out, must_be_empty=True)

    # ── C: debt changes 5→4 → escape hatch fires again, backlog stays silent ──
    write(DEBT, {"consecutive_no_verify": 4})
    out = run(mod)
    expect("C1 debt change re-fires", out, must_contain="ESCAPE HATCH EXHAUSTED: 4")
    expect_bool("C2 unchanged backlog silent", "SCORING BACKLOG" not in out, out[:90])
    st = read_state()
    expect_bool("C3 debt updated", st.get("last_debt") == 4, st.get("last_debt"))

    # ── D: still silent ──
    out = run(mod)
    expect("D stable state silent", out, must_be_empty=True)

    # ── E: set CHANGES (one cycle replaced by a new one, count stays 2) → fires ──
    init_loop([("curate-skills-mcp-watchdog", OLD_TS_A, "PENDING"),
               ("new-cycle-gamma", OLD_TS_B, "PENDING")])
    out = run(mod)
    expect("E backlog set change re-fires", out, must_contain="SCORING BACKLOG: 2")
    st = read_state()
    expect_bool("E2 sig updated (gamma in sig)", any("new-cycle-gamma" in s for s in st.get("last_backlog", [])), st.get("last_backlog"))

    # ── F: all scored → silent + empty baseline recorded ──
    init_loop([])
    out = run(mod)
    expect("F cleared backlog silent", out, must_be_empty=True)
    st = read_state()
    expect_bool("F2 empty baseline recorded", st.get("last_backlog") == [], st.get("last_backlog"))

    # ── G: same 2 cycles re-appear → re-accumulation fires again ──
    init_loop([("curate-skills-mcp-watchdog", OLD_TS_A, "PENDING"),
               ("skill-sidekiq-job-operations", OLD_TS_B, "PENDING")])
    out = run(mod)
    expect("G re-accumulation fires", out, must_contain="SCORING BACKLOG: 2")

    # ── H: new --no-verify events (section 1) still fire + advance index ──
    setup(
        state={"last_timestamp": None, "last_index": -1},
        debt={"consecutive_no_verify": 0},
        log=[{"timestamp": "2026-08-20T01:00:00Z", "commit": "abc123def456", "message": "bypass one"},
             {"timestamp": "2026-08-20T02:00:00Z", "commit": "def456abc123", "message": "bypass two"}],
        loop_rows=[("curate-skills-mcp-watchdog", OLD_TS_A, "PENDING")],
    )
    out = run(mod)
    expect("H1 new events fire", out, must_contain="2 new --no-verify event(s)")
    idx = read_state().get("last_index")
    expect_bool("H2 index advanced", idx == 1, idx)

    # ── I: fresh run (no state file at all) with no backlog → silent, no crash ──
    setup(state=None, debt={"consecutive_no_verify": 0}, log=[], loop_rows=[])
    out = run(mod)
    expect("I fresh empty env silent", out, must_be_empty=True)

    # ── J: fresh run with backlog present → fires once (defaults) ──
    setup(state=None, debt={"consecutive_no_verify": 0}, log=[],
          loop_rows=[("cycle-alpha", OLD_TS_A, "PENDING"), ("cycle-beta", OLD_TS_B, "PENDING")])
    out = run(mod)
    expect("J1 fresh env backlog fires", out, must_contain="SCORING BACKLOG: 2")
    out = run(mod)
    expect("J2 then silent", out, must_be_empty=True)

    print()
    print(f"RESULT: {sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
