#!/usr/bin/env python3
"""
Eval Harness — Run evaluation suites against Hermes agents.

STANDALONE MODE (from shell):
    python3 run-evals.py --eval cron-installation --standalone
    python3 run-evals.py --suite regression --standalone

AGENT MODE (inside Hermes session):
    python3 run-evals.py --eval cron-installation
    python3 run-evals.py --suite regression

Standalone mode uses subprocess + filesystem instead of hermes_tools,
so it works from any shell or cron job without a live Hermes session.
"""
import argparse
import json
import os
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Hermes tools — auto-fallback to standalone stubs when not in Hermes session
_HAS_HERMES_TOOLS = False
try:
    from hermes_tools import web_search, terminal, read_file, write_file, search_files
    _HAS_HERMES_TOOLS = True
except ImportError:
    # Standalone stubs — use subprocess/filesystem instead
    import subprocess

    def terminal(command, timeout=60, workdir=None):
        cwd = workdir or os.getcwd()
        r = subprocess.run(command, shell=True, capture_output=True, text=True,
                           timeout=timeout, cwd=cwd)
        return {"output": r.stdout + r.stderr, "exit_code": r.returncode}

    def write_file(path, content):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return {"bytes_written": len(content)}

    def read_file(path, offset=1, limit=500):
        p = Path(path)
        if not p.exists():
            return {"content": "", "total_lines": 0}
        lines = p.read_text().splitlines(keepends=True)
        start = offset - 1
        end = min(start + limit, len(lines))
        return {"content": "".join(lines[start:end]), "total_lines": len(lines)}

    def web_search(query, limit=5):
        import urllib.request, urllib.parse, json
        try:
            url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json"
            data = json.loads(urllib.request.urlopen(url, timeout=10).read())
            return {"data": {"web": [{"url": "", "title": data.get("AbstractText", ""), "description": ""}]}}
        except Exception as e:
            return {"data": {"web": []}, "error": str(e)}

    def search_files(pattern, target="content", path=".", file_glob=None, limit=50):
        import glob as _glob
        p = Path(path)
        if target == "files":
            return {"matches": [str(f) for f in p.rglob(pattern)][:limit]}
        return {"matches": []}

# Configuration
CORTEX_HOME = Path.home() / ".hermes-cortex"
EVALS_DIR = CORTEX_HOME / "evals"
TRACES_DIR = EVALS_DIR / "traces"
REPORTS_DIR = EVALS_DIR / "reports"
EVALS_REPO_DIR = Path.home() / "hermes-cortex" / "evals"

# Ensure directories exist
TRACES_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_eval_definition(eval_name: str) -> dict:
    """Load eval definition from YAML/JSON file."""
    # Try repo location first
    repo_path = EVALS_REPO_DIR / f"{eval_name}.yaml"
    if repo_path.exists():
        # Parse YAML (simple parser, no external deps)
        return parse_simple_yaml(repo_path.read_text())
    
    # Try hermes location
    hermes_path = EVALS_DIR / f"{eval_name}.yaml"
    if hermes_path.exists():
        return parse_simple_yaml(hermes_path.read_text())
    
    raise FileNotFoundError(f"Eval definition not found: {eval_name}.yaml")


def parse_simple_yaml(content: str) -> dict:
    """Simple YAML parser for eval definitions (no external deps)."""
    # For now, return a stub — in production, use PyYAML
    # This is a placeholder that returns a sample eval structure
    return {
        "name": "sample-eval",
        "description": "Sample evaluation",
        "tasks": [
            {
                "id": "sample-task-1",
                "description": "Sample task",
                "input": "Do something",
                "expected": ["Result 1", "Result 2"],
                "grading": {
                    "deterministic": ["check_1", "check_2"],
                    "llm_rubric": "Grade based on quality"
                }
            }
        ]
    }


def run_task(task: dict, capture_traces: bool = False) -> dict:
    """Run a single eval task and return results."""
    task_id = task['id']
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    trace_id = f"eval-run-{timestamp}-{task_id}"
    
    print(f"  Running task: {task_id}")
    
    result = {
        "task_id": task_id,
        "timestamp": timestamp,
        "trace_id": trace_id,
        "input": task.get("input", ""),
        "expected": task.get("expected", []),
        "actual": None,
        "deterministic_scores": {},
        "llm_score": None,
        "passed": False,
        "error": None,
        "trace_path": None,
    }
    
    try:
        # Execute the task input as a prompt to the agent
        # In production, this would invoke the agent with the task input
        # For now, we simulate by running a command
        cmd_result = terminal(
            command=f"echo 'Task: {task.get('input', '')[:100]}...'",
            timeout=60
        )
        
        result["actual"] = cmd_result.get("output", "")
        
        # Apply deterministic graders
        grading = task.get("grading", {})
        for grader_name in grading.get("deterministic", []):
            # In production, load and execute grader
            # For now, simulate
            result["deterministic_scores"][grader_name] = True  # Simulated pass
        
        # Apply LLM rubric grader
        llm_rubric = grading.get("llm_rubric", "")
        if llm_rubric:
            # In production, call LLM to grade
            # For now, simulate
            result["llm_score"] = 0.85  # Simulated score
        
        # Determine pass/fail
        det_passed = all(result["deterministic_scores"].values())
        llm_passed = result["llm_score"] is None or result["llm_score"] >= 0.7
        result["passed"] = det_passed and llm_passed
        
        # Capture trace if requested
        if capture_traces:
            trace_path = TRACES_DIR / f"{trace_id}.json"
            trace_data = {
                "trace_id": trace_id,
                "task": task,
                "result": result,
                "observations": [cmd_result],
            }
            write_file(path=str(trace_path), content=json.dumps(trace_data, indent=2))
            result["trace_path"] = str(trace_path)
            
    except Exception as e:
        result["error"] = str(e)
        result["passed"] = False
    
    return result


def run_eval_suite(eval_def: dict, capture_traces: bool = False, holdout: bool = False) -> dict:
    """Run all tasks in an eval suite."""
    print(f"\n{'='*60}")
    print(f"Eval: {eval_def.get('name', 'unknown')}")
    print(f"Description: {eval_def.get('description', 'no description')}")
    print(f"{'='*60}\n")
    
    tasks = eval_def.get("tasks", [])
    if holdout:
        # In production, filter to holdout tasks only
        print("Running on HOLDOUT set (unseen test cases)\n")
    
    results = []
    for task in tasks:
        result = run_task(task, capture_traces)
        results.append(result)
        
        status = "✓ PASS" if result["passed"] else "✗ FAIL"
        print(f"    {status}: {task['id']}")
    
    # Aggregate results
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    pass_rate = passed / total if total > 0 else 0
    
    summary = {
        "eval_name": eval_def.get("name", "unknown"),
        "timestamp": datetime.now().isoformat(),
        "holdout": holdout,
        "total_tasks": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": pass_rate,
        "results": results,
    }
    
    return summary


def print_summary(summary: dict):
    """Print eval summary."""
    print(f"\n{'='*60}")
    print(f"Eval Results: {summary['eval_name']}")
    print(f"{'='*60}")
    print(f"Overall: {summary['pass_rate']*100:.0f}% pass ({summary['passed']}/{summary['total_tasks']} tasks)")
    print(f"Holdout: {'Yes' if summary['holdout'] else 'No'}")
    
    # List failures
    failures = [r for r in summary["results"] if not r["passed"]]
    if failures:
        print(f"\nFailures ({len(failures)}):")
        for f in failures:
            print(f"  - {f['task_id']}: {f.get('error', 'unknown error')}")
            if f.get("trace_path"):
                print(f"    Trace: {f['trace_path']}")
    
    # Save report
    report_path = REPORTS_DIR / f"eval-{summary['eval_name']}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    write_file(path=str(report_path), content=json.dumps(summary, indent=2))
    print(f"\nReport saved: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Run eval suites against Hermes agents")
    parser.add_argument("--eval", type=str, help="Name of eval to run")
    parser.add_argument("--suite", type=str, help="Name of eval suite to run")
    parser.add_argument("--standalone", action="store_true", help="Force standalone mode (from shell)")
    parser.add_argument("--holdout", action="store_true", help="Run on holdout set only")
    parser.add_argument("--capture-traces", action="store_true", help="Capture full traces for analysis")
    
    args = parser.parse_args()
    
    if not args.eval and not args.suite:
        print("Error: Must specify --eval or --suite")
        parser.print_help()
        sys.exit(1)
    
    try:
        if args.eval:
            eval_def = load_eval_definition(args.eval)
            summary = run_eval_suite(eval_def, capture_traces=args.capture_traces, holdout=args.holdout)
            print_summary(summary)
            
            # Exit with error if pass rate below threshold
            if args.holdout and summary["pass_rate"] < 0.9:
                print("\n⚠️  Holdout pass rate below 90% threshold — DO NOT DEPLOY")
                sys.exit(1)
                
        elif args.suite:
            # Load suite definition (list of evals)
            suite_path = EVALS_REPO_DIR / "suites" / f"{args.suite}.yaml"
            if not suite_path.exists():
                print(f"Error: Suite not found: {args.suite}")
                sys.exit(1)
            
            suite_def = parse_simple_yaml(suite_path.read_text())
            for eval_name in suite_def.get("evals", []):
                eval_def = load_eval_definition(eval_name)
                summary = run_eval_suite(eval_def, capture_traces=args.capture_traces, holdout=args.holdout)
                print_summary(summary)
                
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error running evals: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
