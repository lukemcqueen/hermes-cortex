#!/usr/bin/env python3
"""Remove Hermes cron jobs by name from ~/.hermes/cron/jobs.json.

Fleet-safe generic remover for orchestrator EXEC dispatch. Removes every
job whose name matches an argument exactly. Safe defaults:
  - no args -> usage, exit 2
  - unknown name -> warning, but continues (never fails on a non-match)
  - atomic write (tmp + rename)
  - prints removed ids + names; silent-exit 0 when nothing matched

Usage:
  python3 remove-cron-jobs.py <name> [<name> ...]
  python3 remove-cron-jobs.py --list          # print all job names, exit 0

The scheduler picks up jobs.json changes on its next tick — no restart
needed. Verify after removal with: hermes cron list | grep <name>
"""
import json
import os
import sys

JOBS_FILE = os.path.expanduser("~/.hermes/cron/jobs.json")


def load_jobs() -> dict:
    with open(JOBS_FILE) as f:
        return json.load(f)


def save_jobs(data: dict) -> None:
    tmp = JOBS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, JOBS_FILE)


def main() -> int:
    args = sys.argv[1:]
    if not args:
        doc = __doc__ or "Remove Hermes cron jobs by name"
        print(doc.strip().splitlines()[0])
        print("Usage: remove-cron-jobs.py <name> [<name> ...] | --list")
        return 2

    if args == ["--list"]:
        data = load_jobs()
        for job in data.get("jobs", []):
            print(job.get("name", "?"))
        return 0

    wanted = set(args)
    data = load_jobs()
    jobs = data.get("jobs", [])
    kept = []
    removed = []
    for job in jobs:
        name = job.get("name", "")
        if name in wanted:
            removed.append((job.get("id", "?"), name))
        else:
            kept.append(job)

    for job_id, name in removed:
        print(f"Removed: {name} ({job_id})")
    for name in sorted(wanted - {n for _, n in removed}):
        print(f"Not found (skipped): {name}")

    if removed:
        data["jobs"] = kept
        data["updated_at"] = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat()
        save_jobs(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
