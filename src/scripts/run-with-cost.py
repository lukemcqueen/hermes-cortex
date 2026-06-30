#!/usr/bin/env python3
"""
run-with-cost.py — Run a Hermes cron job and inject the real cost into its output.

Usage:
  python3 run-with-cost.py agent-daily-bible-reading

Runs the cron, captures the runtime response including actual cost,
then patches SOUL.md and the cron output file with the real figure.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


HERMES_HOME = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
SOUL_MD = HERMES_HOME / "SOUL.md"


def load_jobs() -> dict:
    """Load cron jobs from state file, keyed by name."""
    try:
        with open(HERMES_HOME / "cron" / "jobs.json") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    
    jobs = data if isinstance(data, list) else data.get("jobs", [])
    by_name = {}
    for j in jobs:
        if isinstance(j, dict) and "name" in j and "id" in j:
            by_name[j["name"]] = j
    return by_name


def run_cron(job_name: str) -> dict:
    """Run a cron job via hermes CLI and return the parsed response."""
    jobs = load_jobs()
    job = jobs.get(job_name)
    if not job:
        raise RuntimeError(f"Job '{job_name}' not found in cron state")
    
    job_id = job["id"]
    result = subprocess.run(
        ["hermes", "cron", "run", job_id],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        raise RuntimeError(f"hermes cron run '{job_name}' failed: {result.stderr}")
    
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        text = result.stdout
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end+1])
        raise


def get_actual_cost(run_result: dict) -> float | None:
    """Extract actual cost from cron run result."""
    lrc = run_result.get("last_run_cost", {}) or {}
    cost = lrc.get("estimated_cost_usd")
    if cost is not None:
        return round(cost, 6)
    inp = lrc.get("input_tokens", 0) or 0
    out = lrc.get("output_tokens", 0) or 0
    cost = (inp * 0.15 + out * 0.60) / 1_000_000
    return round(cost, 6) if cost > 0 else None


def cost_fmt(cost: float) -> str:
    if cost < 0.01:
        return f"${cost:.6f}"
    return f"${cost:.4f}"


def patch_cost_in_text(text: str, actual_cost: str) -> str:
    """Replace any cost placeholder ($COST_UNKNOWN, $0.00, see cron metadata) with actual cost."""
    result = text
    result = re.sub(r"Cost: see cron metadata", f"Cost: {actual_cost}", result)
    result = re.sub(r"Cost:\s*\$?\d+\.\d+\b", f"Cost: {actual_cost}", result)
    return result


def patch_file(filepath: Path, actual_cost: str) -> bool:
    if not filepath.exists():
        return False
    content = filepath.read_text(encoding="utf-8", errors="replace")
    new_content = patch_cost_in_text(content, actual_cost)
    if new_content != content:
        filepath.write_text(new_content, encoding="utf-8")
        return True
    return False


def patch_latest_output(job_name: str, job_id: str | None, actual_cost: str) -> bool:
    """Patch the most recent cron output file for this job."""
    output_dir = HERMES_HOME / "cron" / "output"
    # Try by job_id first
    if job_id:
        job_dir = output_dir / job_id
        if job_dir.exists():
            files = sorted(job_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
            if files:
                return patch_file(files[0], actual_cost)
    
    # Try by name
    files = sorted(output_dir.glob(f"{job_name}*"), key=lambda f: f.stat().st_mtime, reverse=True)
    if files:
        return patch_file(files[0], actual_cost)
    
    # Try all dirs containing name
    for d in output_dir.iterdir():
        if d.is_dir() and any(f.name.startswith(job_name) for f in d.iterdir()):
            files = sorted(d.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
            if files:
                return patch_file(files[0], actual_cost)
    
    return False


def main():
    if len(sys.argv) < 2:
        print("Usage: run-with-cost.py <cron-job-name> [cron-job-name...]", file=sys.stderr)
        sys.exit(1)
    
    for job_name in sys.argv[1:]:
        print(f"Running '{job_name}'...", file=sys.stderr)
        
        try:
            result = run_cron(job_name)
        except Exception as e:
            print(f"  Failed to run '{job_name}': {e}", file=sys.stderr)
            continue
        
        cost = get_actual_cost(result)
        if cost is None:
            print(f"  '{job_name}' ran but no cost data available. Check hermes cron list for details.", file=sys.stderr)
            continue
        
        c = cost_fmt(cost)
        job_id = result.get("job", {}).get("job_id") or result.get("job_id")
        patched = False
        
        # Patch SOUL.md for soul/bible crons
        if "soul" in job_name or "bible" in job_name:
            if patch_file(SOUL_MD, c):
                print(f"  ✅ '{job_name}': patched SOUL.md (actual cost={c})", file=sys.stderr)
                patched = True
        
        # Patch cron output
        if patch_latest_output(job_name, job_id, c):
            print(f"  ✅ '{job_name}': patched output file (actual cost={c})", file=sys.stderr)
            patched = True
        
        if not patched:
            print(f"  '{job_name}': ran (actual cost={c}), but no files needed patching", file=sys.stderr)
        
        # Print cost summary for verification
        print(json.dumps({
            "job": job_name,
            "actual_cost": c,
            "input_tokens": result.get("last_run_cost", {}).get("input_tokens"),
            "output_tokens": result.get("last_run_cost", {}).get("output_tokens"),
            "tool_calls": result.get("last_run_cost", {}).get("api_calls"),
        }))


if __name__ == "__main__":
    main()
