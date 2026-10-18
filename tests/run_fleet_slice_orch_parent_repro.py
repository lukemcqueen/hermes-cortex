#!/usr/bin/env python3
"""Golden-master repro: v013 fleet-slice-under-orchestrator-parent (backlog f0c6afbf).

Re-runnable proof that the v013 check_tenant relaxation works end-to-end.
Per repo convention (cf. run_task_query_repo_scope_repro.py), this drives the
REAL hermetic schema battery against a scratch DB and the REAL unit suite, and
writes the FULL RAW output (unfiltered, with the runner's own exit code) to a
committed artifact under tests/artifacts/.

What it asserts (all from raw output, no filtering of pass/fail):
  1. The new regression runs and passes:
       'orchestrator personal story created'
       'fleet slice under orchestrator personal story stored scope=fleet'
       'fleet slice under non-orchestrator personal story still refused'
  2. The battery overall still reaches the expected pass count (pre-existing
     baseline was 95; the 3 new checks bring it to 98).
  3. The KNOWN pre-existing failure (unrelated, in baseline before v013) is
     still present and NAMED so a reader knows it is not this change:
       'blocked -> pending accepted'
  4. The unit suite still passes 64/64.
  5. The deployed task-db runner reports 'version 13' (live schema converged).

Usage:
  python3 tests/run_fleet_slice_orch_parent_repro.py [--write-artifact] [--db <name>]
Exit: 0 all expectations held; 1 an expectation was violated; 2 could not verify.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BATTERY = REPO / "tests" / "test-tasks-schema.sh"
ARTIFACT_REL = "tests/artifacts/v013-fleet-slice-schema-battery.txt"
ARTIFACT = REPO / ARTIFACT_REL

PASS_MARKERS = [
    "orchestrator personal story created",
    "fleet slice under orchestrator personal story stored scope=fleet",
    "fleet slice under non-orchestrator personal story still refused (scope coherence)",
]
KNOWN_PREEXISTING_FAIL = "blocked → pending accepted"
EXPECTED_PASS_COUNT = 98


def _clean_env() -> dict:
    env = dict(os.environ)
    # Run-tests.sh documents WHY cleansing is mandatory: inherited PYTHONPATH
    # shadows the fleet venv's own site-packages -> 28 tests vanish silently.
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    return env


def _run(args, env, capture=True) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, env=env, capture_output=capture, text=True, cwd=str(REPO)
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-artifact", action="store_true",
                    help="write the raw battery+unit output to %s" % ARTIFACT_REL)
    ap.add_argument("--db", default="tasks_fleetslice_repro",
                    help="scratch DB name (must NOT be 'mycortex')")
    args = ap.parse_args()

    if args.db == "mycortex":
        print("REFUSING: scratch DB cannot be 'mycortex'.", file=sys.stderr)
        return 2

    env = _clean_env()
    env["TASKS_TEST_DB"] = args.db
    failed_any = False
    chunks: list[str] = []

    # --- 1/2: schema battery (full raw output, its own exit code) ------------
    battery = _run(["bash", str(BATTERY)], env)
    battery_body = battery.stdout  # battery prints progress to stdout
    chunks.append(
        "===== schema battery: tests/test-tasks-schema.sh (raw) ====\n"
        f"% b: rc={battery.returncode}\n"
        f"% {battery_body}"
    )
    passes = sum(1 for line in battery_body.splitlines()
                 if line.strip().startswith("✅"))
    for m in PASS_MARKERS:
        ok = m in battery_body
        print(f"  {'✅' if ok else '❌'} battery contains: {m}")
        failed_any = failed_any or (not ok)
    ok = passes == EXPECTED_PASS_COUNT
    print(f"  {'✅' if ok else '❌'} battery pass count == {EXPECTED_PASS_COUNT} (got {passes})")
    failed_any = failed_any or (not ok)
    ok = KNOWN_PREEXISTING_FAIL in battery_body
    print(f"  {'✅' if ok else '❌'} known pre-existing failure still present: '{KNOWN_PREEXISTING_FAIL}'")
    failed_any = failed_any or (not ok)

    # --- 3: unit suite (raw) -------------------------------------------------
    unit = _run([str(REPO / "tests" / "run-tests.sh"),
                 "tests/test_task_db_unit.py", "-q"], env)
    unit_body = (unit.stdout or "") + "\n" + (unit.stderr or "")
    chunks.append(
        "\n===== unit suite: tests/run-tests.sh tests/test_task_db_unit.py (raw) ====\n"
        f"% u: rc={unit.returncode}\n% {unit_body}"
    )
    ok = "64 passed" in unit_body
    print(f"  {'✅' if ok else '❌'} unit suite reports 64 passed")
    failed_any = failed_any or (not ok)

    # --- 4: deployed runner converges on v13 ----------------------------------
    applied = _run(["python3", str(Path.home() / ".hermes-cortex/scripts/task-db.py"),
                    "--apply-schema"], env)
    applied_body = (applied.stdout or "") + (applied.stderr or "")
    chunks.append(
        "\n===== deployed runner: python3 ~/.hermes-cortex/scripts/task-db.py --apply-schema ====\n"
        f"% d: rc={applied.returncode}\n% {applied_body}"
    )
    ok = "version 13" in applied_body and "no-op" in applied_body
    print(f"  {'✅' if ok else '❌'} deployed runner reports schema version 13 (no-op)")
    failed_any = failed_any or (not ok)

    if args.write_artifact:
        ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        ARTIFACT.write_text("".join(chunks))
        print(f"  wrote {ARTIFACT_REL}")

    print(f"RESULT: {'ALL EXPECTATIONS HELD' if not failed_any else 'EXPECTATION VIOLATED'} "
          f"(rc-final={'0' if not failed_any else '1'})")
    return 0 if not failed_any else 1


if __name__ == "__main__":
    sys.exit(main())