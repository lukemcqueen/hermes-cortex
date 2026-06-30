#!/usr/bin/env python3
"""
cron-cost-inject.py — Post-processes cron output by replacing cost placeholders with actual costs.

Run after an LLM cron executes. Reads the last run's cost from the cron DB
and patches SOUL.md / cron output to replace placeholders with real costs.

Usage:
  python3 cron-cost-inject.py agent-daily-bible-reading
  python3 cron-cost-inject.py agent-daily-bible-reading agent-daily-soul-refinement
"""

import json
import os
import re
import sys
from pathlib import Path


HERMES_HOME = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
SOUL_MD = HERMES_HOME / "SOUL.md"


def load_cron_state():
    paths = [
        HERMES_HOME / "cron" / "jobs.json",
        Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))) / "cron" / "jobs.json",
    ]
    for p in paths:
        try:
            with open(p) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    print("Cannot read cron state", file=sys.stderr)
    sys.exit(1)


def find_job(cron_state, name):
    jobs = cron_state if isinstance(cron_state, list) else cron_state.get("jobs", [])
    for j in jobs:
        if isinstance(j, dict) and j.get("name") == name:
            return j
    return None


def get_last_cost(job):
    lrc = job.get("last_run_cost", {}) or {}
    cost = lrc.get("estimated_cost_usd")
    if cost is not None:
        return round(cost, 6)
    inp = lrc.get("input_tokens", 0) or 0
    out = lrc.get("output_tokens", 0) or 0
    cost = (inp * 0.15 + out * 0.60) / 1_000_000
    return round(cost, 6) if cost > 0 else None


def cost_str(cost):
    if cost < 0.01:
        return f"${cost:.6f}"
    return f"${cost:.4f}"


def replace_placeholders(text, cost):
    text = re.sub(r"Cost: see cron metadata", f"Cost: {cost}", text)
    text = re.sub(r"Cost: \$?0\.00\b", f"Cost: {cost}", text)
    text = re.sub(r"\$COST_UNKNOWN", cost, text)
    return text


def patch_file(filepath, cost):
    if not filepath.exists():
        return False
    content = filepath.read_text(encoding="utf-8", errors="replace")
    new_content = replace_placeholders(content, cost)
    if new_content != content:
        filepath.write_text(new_content, encoding="utf-8")
        return True
    return False


def patch_output_files(job_name, cost):
    output_dir = HERMES_HOME / "cron" / "output"
    if not output_dir.exists():
        return False
    outputs = sorted(output_dir.glob(f"{job_name}*"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not outputs:
        return False
    return patch_file(outputs[0], cost)


def main():
    if len(sys.argv) < 2:
        print("Usage: cron-cost-inject.py <cron-job-name> [...]", file=sys.stderr)
        sys.exit(1)

    cron_state = load_cron_state()
    job_names = sys.argv[1:]
    any_patched = False

    for name in job_names:
        job = find_job(cron_state, name)
        if not job:
            print(f"  Job '{name}' not found in cron state — skipping")
            continue

        cost = get_last_cost(job)
        if cost is None:
            print(f"  '{name}' has no cost data — skipping")
            continue

        c = cost_str(cost)
        patched = False

        # Patch SOUL.md for soul/bible crons
        if "soul" in name or "bible" in name:
            if patch_file(SOUL_MD, c):
                print(f"  '{name}': patched SOUL.md (cost={c})")
                patched = True

        # Patch cron output files
        if patch_output_files(name, c):
            print(f"  '{name}': patched cron output (cost={c})")
            patched = True

        if patched:
            any_patched = True
        else:
            print(f"  '{name}': no placeholders found to replace (cost={c})")

    if not any_patched:
        print("No placeholders found to replace.")
        sys.exit(1)


if __name__ == "__main__":
    main()
