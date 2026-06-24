#!/usr/bin/env python3
"""
Cron Installer — reads crons.json template and manages Hermes Agent cron jobs.

Usage:
    python3 install-crons.py              # install/update
    python3 install-crons.py --check      # dry-run
    python3 install-crons.py --force      # re-install even if same version
"""
import json
import os
import subprocess
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "crons.json")
MARKER_PATH = os.path.join(SCRIPT_DIR, ".cron-version")
DEFAULT_CRON_PROMPT = {
    "weekly-loop-evaluation": (
        "Run the loop governance evaluation pipeline for the last 7 days, "
        "then auto-apply safe config changes, and finally vacuum old cycles.\n\n"
        "1. Generate the evaluation report using the loop-governance skill.\n"
        "2. Deliver the report (summary, trends, accuracy, recommendations).\n"
        "3. Run auto-apply: execute `auto-apply --json`.\n"
        "4. Run DB retention (archive cycles older than 90 days).\n"
        "5. Deliver a combined message."
    ),
}


def run_hermes(args: list[str], timeout: int = 30) -> tuple[str, str, int]:
    """Run a hermes command and return (stdout, stderr, returncode)."""
    try:
        r = subprocess.run(["hermes"] + args, capture_output=True, text=True, timeout=timeout)
        return r.stdout, r.stderr, r.returncode
    except FileNotFoundError:
        return "", "Hermes Agent not found", 1
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1


def get_existing_jobs() -> dict[str, str]:
    """Return {name: job_id} for all current cron jobs."""
    out, err, rc = run_hermes(["cron", "list"])
    if rc != 0:
        return {}
    jobs = {}
    current_id = None
    for line in out.split("\n"):
        line = line.strip()
        # Match "  abc123def456 [active]"
        if len(line) >= 12 and line.split() and len(line.split()[0]) == 12 and "[" in line:
            current_id = line.split()[0]
        if "Name:" in line and current_id:
            name = line.split("Name:")[-1].strip()
            jobs[name] = current_id
            current_id = None
    return jobs


def main():
    check_only = "--check" in sys.argv
    force = "--force" in sys.argv

    if not os.path.exists(TEMPLATE_PATH):
        print(f"✗ Template not found: {TEMPLATE_PATH}")
        sys.exit(1)

    with open(TEMPLATE_PATH) as f:
        template = json.load(f)

    template_ver = template.get("version", 0)
    installed_ver = "0"
    if os.path.exists(MARKER_PATH):
        with open(MARKER_PATH) as f:
            installed_ver = f.read().strip()

    print(f"\n═ Loop Governance Crons ═\n")
    print(f"  ℹ Template v{template_ver}  |  Installed v{installed_ver}\n")

    if str(template_ver) == installed_ver and not force:
        print(f"  ✓ Crons are up to date (v{template_ver})")
        return

    existing = get_existing_jobs()
    crons = template.get("crons", [])

    # Step 1: Remove existing crons with matching names
    for cron in crons:
        name = cron["name"]
        if name in existing:
            jid = existing[name]
            if check_only:
                print(f"  ℹ Would remove '{name}' ({jid})")
            else:
                out, err, rc = run_hermes(["cron", "remove", jid])
                if rc == 0:
                    pass  # removed silently
                else:
                    print(f"  ⚠ Failed to remove '{name}': {err[:80]}")

    if check_only:
        print()
        for cron in crons:
            print(f"  ℹ Would create '{cron['name']}' ({cron['schedule']})")
        print("\n  ℹ Run without --check to apply")
        return

    # Step 2: Create fresh crons from template
    for cron in crons:
        name = cron["name"]
        schedule = cron["schedule"]
        deliver = cron.get("deliver", "origin")
        no_agent = cron.get("no_agent", False)
        script = cron.get("script", "")
        skills = cron.get("skills", [])
        prompt = cron.get("prompt", "") or DEFAULT_CRON_PROMPT.get(name, "")

        cmd = ["cron", "create", schedule]

        # Prompt must come immediately after schedule, before any --flags
        if no_agent and script:
            cmd.extend(["--no-agent", "--script", script])
        elif prompt:
            cmd.append(prompt)
            cmd.extend(["--name", name, "--deliver", deliver])
            for s in skills:
                cmd.extend(["--skill", s])
        else:
            cmd.extend(["--name", name, "--deliver", deliver])

        out, err, rc = run_hermes(cmd)
        if rc == 0:
            print(f"  ✓ {name} created ({schedule})")
        else:
            print(f"  ✗ {name} failed: {err[:120]}")

        # Clean up — no temp file needed now (prompt passed inline)

    # Record version
    with open(MARKER_PATH, "w") as f:
        f.write(str(template_ver))
    print(f"\n  ✓ Crons installed (v{template_ver})")
    print("\n  ℹ Verify: hermes cron list | grep -E '(loop|weekly)'")


if __name__ == "__main__":
    main()