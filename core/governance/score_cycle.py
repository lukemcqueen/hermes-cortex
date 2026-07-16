#!/usr/bin/env python3.12
import sys
import os

# Minimum Python 3.10 for union type syntax (str | None, list[float] | None)
if sys.version_info < (3, 10):
    # Check if pyenv is available but not first in PATH
    pyenv_root = os.environ.get("PYENV_ROOT", os.path.expanduser("~/.pyenv"))
    pyenv_python = os.path.join(pyenv_root, "shims", "python3")
    if os.path.isfile(pyenv_python):
        sys.exit(f"Python 3.10+ required (got {sys.version_info.major}.{sys.version_info.minor}). "
                 f"Run: eval \"$({pyenv_root}/bin/pyenv init -)\"")
    sys.exit(f"Python 3.10+ required (got {sys.version_info.major}.{sys.version_info.minor}). "
             f"Install Python 3.10+ and ensure it's first in PATH.")

"""
Cycle Logger — score a TDD cycle and log it to the DB in one shot.

Single-command integration point for change-test-loop, subagent-driven-development,
and any workflow skill that runs multi-iteration loops.

Usage:
    # From file (most convenient — write cycle data to a file, pass it in)
    python3 cycle_logger.py --task my-feature --cycle 1 \
      --spec-file spec.md \
      --code-file src/impl.py \
      --test-file tests/test_out.txt \
      --pass-pct 0.95

    # From inline values
    python3 cycle_logger.py --task my-feature --cycle 1 \
      --spec "Add two numbers" \
      --code "def add(a,b): return a+b" \
      --test-output "1 passed" \
      --pass-pct 1.0

    # From previous code (for progress detection — pass PREVIOUS code, not test output)
    python3 cycle_logger.py --task my-feature --cycle 2 \
      --spec-file spec.md \
      --code-file src/impl.py \
      --prev-code-file src/impl.prev.py \
      --test-file tests/test_out.txt \
      --pass-pct 0.95

    # Minimal — just score + log, let progress default to 10.0
    python3 cycle_logger.py --task my-feature --cycle 1 \
      --code "def add(a,b): return a+b"

    # JSON output (for programmatic use by other tools)
    python3 cycle_logger.py --task my-feature --cycle 1 \
      --code-file src/impl.py --json

Output includes:
    - cycle_id: the database row ID (for future feedback via loop-feedback)
    - All scores + decision
    - logged: true/false
"""

import argparse
import json
import os
import sys

from loop_scorer import full_score
from loop_db import LoopDB

DEFAULT_DB_PATH = os.path.expanduser("~/.hermes-cortex/data/loop-governance.db")


def read_or_none(path):
    """Read a file if provided, otherwise return None."""
    if path:
        with open(os.path.expanduser(path)) as f:
            return f.read()
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Score a TDD cycle and log to the loop-governance DB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cycle-logger --task feature-x --cycle 1 --code-file src/main.py --json
  cycle-logger --task bugfix --cycle 2 --spec-file spec.md --code-file impl.py
    --test-file test_output.txt --prev-code-file impl.py.prev --pass-pct 0.8
        """,
    )

    # Required
    parser.add_argument("--task", required=True,
                        help="Task identifier (e.g. 'feature-user-auth')")
    parser.add_argument("--cycle", type=int, required=True,
                        help="1-based cycle number within this task")

    # Data sources (file or inline for each)
    data = parser.add_argument_group("Data sources (specify --*-file or --* inline)")
    data.add_argument("--spec", default=None, help="Spec text inline")
    data.add_argument("--spec-file", default=None, help="Path to spec file")
    data.add_argument("--code", default=None, help="Code text inline")
    data.add_argument("--code-file", default=None, help="Path to code file")
    data.add_argument("--test-output", default=None, help="Test runner output inline")
    data.add_argument("--test-file", default=None, help="Path to test output file")
    data.add_argument("--prev-code", default="",
                       help="Previous cycle's code (for progress detection)")
    data.add_argument("--prev-code-file", default=None,
                       help="Path to previous cycle's code file")
    data.add_argument("--prev-output", default="",
                       help="[DEPRECATED] Use --prev-code instead")
    data.add_argument("--pass-pct", type=float, default=None,
                       help="Test pass rate 0.0-1.0 (e.g. 0.95 for 95%% pass)")

    # Options
    parser.add_argument("--db", default=DEFAULT_DB_PATH,
                        help=f"Database path (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON instead of human-readable")

    args = parser.parse_args()

    # Resolve inline vs file for each data source
    spec = args.spec or read_or_none(args.spec_file) or ""
    code = args.code or read_or_none(args.code_file) or ""
    test_output = args.test_output or read_or_none(args.test_file) or ""
    prev_code = args.prev_code or read_or_none(args.prev_code_file) or \
                args.prev_output or ""

    # Validate
    if not code.strip() and not spec.strip() and not test_output.strip():
        parser.error("At least one data source is required (--code, --spec, --test-output, or their --*-file variants)")

    # Score and log
    result = full_score(
        spec=spec,
        output=code,
        previous=prev_code,
        task_id=args.task,
        cycle_num=args.cycle,
        db_path=args.db,
    )

    # Get the cycle_id from the DB (full_score doesn't return it)
    cycle_id = None
    try:
        db = LoopDB(args.db)
        rows = db.conn.execute(
            "SELECT id FROM loop_cycles WHERE task_id = ? AND cycle_num = ? ORDER BY id DESC LIMIT 1",
            (args.task, args.cycle),
        ).fetchall()
        if rows:
            cycle_id = rows[0]["id"]
        db.close()
    except Exception:
        pass

    result["cycle_id"] = cycle_id
    result["task_id"] = args.task
    result["cycle_num"] = args.cycle
    result["logged"] = result.get("logged", False)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print("═" * 55)
        print(f"  Cycle #{cycle_id or '?'}  |  {args.task}  |  cycle {args.cycle}")
        print("═" * 55)
        print()
        print(f"  Completeness:  {result['completeness']:>5.1f}/10")
        print(f"  Quality:       {result['quality']:>5.1f}/10")
        print(f"  Progress:      {result['progress']:>5.1f}/10")
        print(f"  ─────────────────────")
        print(f"  Composite:     {result['composite']:>5.1f}/10")
        print(f"  Decision:      {result['decision']}")
        print(f"  No-progress:   {'YES ⚠' if result.get('no_progress') else 'no'}")
        print()
        print(f"  Logged to DB:  {'YES ✅' if result.get('logged') else 'NO ❌'}")
        if result.get('log_error'):
            print(f"  DB error:      {result['log_error']}")
        if result.get('warnings'):
            print()
            print(f"  ⚠  Warnings:")
            for w in result['warnings']:
                print(f"      {w}")
        print()
        if cycle_id:
            print(f"  💡 Feedback: loop-feedback accept {cycle_id} --note \"...\"")
            print(f"     Or:       loop-feedback override {cycle_id} --note \"...\"")
        print()


if __name__ == "__main__":
    main()
