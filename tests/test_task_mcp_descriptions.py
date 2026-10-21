#!/usr/bin/env python3
"""The task tools must say what ACTUALLY gates verification, and what to do about it.

Raised 2026-10-21 (operator, from the Pi agent): task_verify described itself only as
"ORCHESTRATOR-ONLY: verify a review slice" and task_report as "awaiting orchestrator verify". Both
invite the inference that moses/esther will pick the slice up — and NOTHING does. Verified
mechanism, not assumed: tasks.verify_slice (ops/services/tasks/schema/v009__task-model-v3.sql) is
the only review→completed path, it is enforced in the DB (SECURITY DEFINER, moses/esther allowlist
inside the function, no EXECUTE grant for other profiles), and the fleet cron inventory
(docs/cron-schedules.md) lists no slice-verification job. An agent that believes someone will act
stops working on a slice that then sits in review forever, so the wording an agent READS under a
refusal is the fix.

WHY A TEXT GUARD: the deliverable here IS the wording. The mechanism the wording cites is proven
in the schema and the cron inventory (named above); what this pins is that the description cannot
quietly regress to the passive phrasing.

COLLECTABLE, NOT EXECUTED AT IMPORT (fixed 2026-10-21, issue #212 / event #212): this file used to
run its checks at MODULE level and end with a bare `raise SystemExit(...)`. pytest executes a
module in order to collect it, so that SystemExit fired while IMPORTING this file and aborted
collection for the WHOLE suite — `INTERNALERROR` and "no tests ran" for every agent on the host,
on any range, with nothing in the run saying why. Measured before the fix:
`bash tests/run-tests.sh tests/ -q` -> rc=3, "no tests ran in 3.25s", INTERNALERROR pointing at
line 57 of this file. The checks now live in a function pytest collects, the script behaviour sits
behind __main__, and a missing subject file is a reported FAILURE rather than an exit at import —
so importing this module can never kill a run again.

Run: python3 tests/test_task_mcp_descriptions.py     (pytest also collects it)
"""
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "mcp-servers" / "task-mcp.py"

REQUIRED = {
    "task_verify names the DB enforcement": "SECURITY DEFINER",
    "task_verify names the refusal a worker actually sees":
        "permission denied for function verify_slice",
    "task_verify states nothing runs it automatically": "NOTHING RUNS THIS AUTOMATICALLY",
    "task_verify tells the agent what to DO instead": "hand the slice id",
    "task_report says review is not completion": "does NOT reach completed",
    "task_report tells the agent to follow up, not wait": "rather than wait",
}
FORBIDDEN = {
    "the passive claim that an orchestrator will verify": "awaiting orchestrator verify",
    "the bare label with no enforcement and no next step":
        "ORCHESTRATOR-ONLY: verify a review slice",
}


def check(text: str) -> list[str]:
    """Run every check against `text` and return the failures.

    Takes the text rather than reading the file itself, so the guard can be driven against a
    fixture: a check that only ever meets the healthy file is a happy path with a name, and
    cannot show that it would NOTICE a regression.
    """
    fails = []
    for why, needle in REQUIRED.items():
        if needle in text:
            print(f"  ✓ {why}")
        else:
            print(f"  ✗ {why} — missing {needle!r}")
            fails.append(why)
    for why, needle in FORBIDDEN.items():
        if needle in text:
            print(f"  ✗ {why} — still present: {needle!r}")
            fails.append(why)
        else:
            print(f"  ✓ {why} — gone")
    return fails


def test_task_tool_descriptions_say_what_gates_verification():
    """The shipped file carries the wording, and does not carry the passive claim.

    This is the test pytest collects. It asserts on the FILE, so the suite fails the moment
    the shipped descriptions regress; `check()` itself is driven both ways by the test below.
    """
    assert SRC.is_file(), f"{SRC} not found — cannot check the descriptions"
    fails = check(SRC.read_text(encoding="utf-8"))
    assert not fails, f"the task tool descriptions regressed: {fails}"


def test_the_guard_notices_a_regression_and_passes_on_a_healthy_text():
    """Drive the guard BOTH ways, so it is a check and not decoration.

    A green run only shows the guard does not misfire; only a demonstrated failure shows it
    would notice the phrasing it exists to pin coming back.
    """
    healthy = " ".join(REQUIRED.values())
    assert check(healthy) == [], "a text carrying every required phrase must pass"

    regressed = healthy + " awaiting orchestrator verify"
    assert check(regressed), "the forbidden passive phrasing must be reported"


def _main() -> int:
    if not SRC.is_file():
        print(f"RESULT: FAILED — {SRC} not found")
        return 1
    fails = check(SRC.read_text(encoding="utf-8"))
    print(f"RESULT: {'ALL PASS' if not fails else f'{len(fails)} FAILED'}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_main())
