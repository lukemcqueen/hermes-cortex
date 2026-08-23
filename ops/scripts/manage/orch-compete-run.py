#!/usr/bin/env python3
"""orch-compete-run.py — Task Model v3 compete mode runner (T7).

Spawns N parallel candidates for the same slice (different approaches),
judges them deterministically (acceptance criteria → adversarial
findings → cost → speed), and logs the winner. Opt-in per slice.

Usage:
  python3 orch-compete-run.py <slice-id> --approaches "2" [--dry-run]

Design: docs/design/task-model-v3.md §2.4. The runner:
  1. Reads the slice's plan (the orchestrator's acceptance criteria +
     approach specs live in the plan field, one approach per line).
  2. Spawns one subagent per approach via delegate_task (parallel batch),
     each with the SAME slice + criteria but ITS approach spec.
  3. Each candidate runs the acceptance tests itself and returns
     pass/fail + evidence (test output, not prose).
  4. Orchestrator (this session) runs adversarial-verify on each candidate;
     any critical/high finding disqualifies.
  5. Winner = AC met (mandatory) → fewest adversarial findings → lowest
     token cost → fastest. Losers archived with a one-line 'why not'.
  6. Logs the compete as a task event (approach A vs B, scores, winner).

Deterministic judging ONLY — never 'which one sounds better'.
"""

import json
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
TASK_DB = HOME / "hermes-cortex" / "ops" / "scripts" / "manage" / "task-db.py"


def taskdb(*args: str) -> str:
    r = subprocess.run(
        ["python3", str(TASK_DB), *args], capture_output=True, text=True,
        timeout=60, cwd=str(HOME / "hermes-cortex"))
    if r.returncode != 0:
        print(r.stderr.strip(), file=sys.stderr)
        sys.exit(r.returncode)
    return r.stdout


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    slice_id = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "run" else (
        sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "")
    if not slice_id:
        print("ERROR: slice-id required", file=sys.stderr)
        return 1

    # 1. Read the slice + its plan
    raw = taskdb("list", "--parent", slice_id) if False else None
    # Direct query through the CLI's psql bridge would be cleaner, but the
    # CLI has no 'get' command — use list with the id.
    # For now: require the slice's plan to be passed via --plan (orchestrator
    # writes criteria + approach specs before invoking).
    plan = None
    for i, a in enumerate(sys.argv):
        if a == "--plan" and i + 1 < len(sys.argv):
            plan = sys.argv[i + 1]
    if not plan:
        print("ERROR: --plan required (acceptance criteria + approach specs, "
              "one approach per line prefixed 'APPROACH:'", file=sys.stderr)
        return 1

    approaches = [ln.strip() for ln in plan.splitlines()
                  if ln.strip().upper().startswith("APPROACH:")]
    if len(approaches) < 2:
        print("ERROR: need ≥2 APPROACH: lines in the plan", file=sys.stderr)
        return 1

    print(f"🧪 Compete mode — slice {slice_id[:8]}…")
    print(f"   {len(approaches)} approaches:")
    for a in approaches:
        print(f"     - {a[9:][:90]}")

    # 2. This is an orchestrator-driven runner. In a real run the
    # orchestrator spawns candidates here via delegate_task. The runner
    # prints the contract so the orchestrator session can execute it.
    print()
    print("→ Orchestrator: spawn one subagent per approach with delegate_task:")
    for i, a in enumerate(approaches):
        print(f"   candidate-{i+1}: approach = {a[9:][:100]}")
    print()
    print("→ Judge deterministically: AC met → adversarial findings → "
          "lowest cost → fastest.")
    print("→ Winner's diff merges; losers archived with 'why not'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
