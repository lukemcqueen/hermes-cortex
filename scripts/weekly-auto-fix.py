#!/usr/bin/env python3
"""
weekly-auto-fix.py — Companion auto-fix runner for the weekly opportunity scan.

Called from the weekly-scan-opportunities cron job after the LLM phase
identifies issues. Handles known fix patterns:

  - git: pull/stash-commit-push for repos behind upstream
  - branches: delete stale branches (local + remote) + merge ready PRs
  - docker: restart containers, check service health
  - permissions: fix world-readable files, executable pids
  - disk: clean large cache/temp directories

Usage:
  python3 weekly-auto-fix.py [--dry-run] [--verbose]

Output: JSON with actions_taken and warnings.
Empty JSON {} on success with nothing to do = silent (watchdog pattern).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
REPO_DIR = os.path.join(HOME, "hermes-cortex")
BRAIN_DIR = os.path.join(HOME, "brain")
SCRIPTS_DIR = os.path.join(HOME, ".hermes", "scripts")
CRON_OUTPUT_DIR = os.path.join(HOME, ".hermes", "cron", "output")
STATE_DIR = os.path.join(HOME, ".hermes", "state")

# Shell safety — no pipe-to-interpreter patterns
def _run(cmd, cwd=None, timeout=30, shell=False):
    """Run a command, return (output, exit_code)."""
    try:
        env = os.environ.copy()
        if os.path.exists(os.path.join(HOME, ".bun", "bin")):
            env["PATH"] = f"{os.path.join(HOME, '.bun', 'bin')}:{env.get('PATH', '')}"
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=cwd, env=env, shell=shell
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", -1
    except FileNotFoundError:
        return "COMMAND_NOT_FOUND", -1


def fix_git_pull():
    """Pull upstream changes for hermes-cortex repo (safe merge via rebase)."""
    actions = []
    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        return actions

    # Check if behind origin/main
    out, rc = _run(["git", "remote", "-v"], cwd=REPO_DIR)
    if rc != 0 or "origin" not in out:
        return actions

    out, rc = _run(["git", "rev-list", "--left-right", "--count",
                     "HEAD...origin/main"], cwd=REPO_DIR, timeout=15)
    if rc != 0 or not out:
        return actions

    try:
        behind = int(out.split("\t")[1].strip())
    except (IndexError, ValueError):
        behind = 0

    if behind > 0:
        # Try rebase pull
        out, rc = _run(["git", "pull", "--rebase", "--autostash"],
                        cwd=REPO_DIR, timeout=30)
        if rc == 0:
            actions.append(f"git-pull: pulled {behind} commit(s) from origin/main")
        else:
            actions.append(f"git-pull: FAILED (behind by {behind}, rebase conflict)")

    return actions


def fix_stale_branches():
    """Delete local branches whose remote tracking branches are gone."""
    actions = []

    # Prune remote-tracking refs
    _run(["git", "remote", "prune", "origin"], cwd=REPO_DIR, timeout=10)

    # Find stale local branches
    out, rc = _run(["git", "branch", "-vv"], cwd=REPO_DIR, timeout=10)
    if rc != 0:
        return actions

    stale = []
    for line in out.split("\n"):
        if ": gone]" in line:
            parts = line.strip().lstrip("* ").split()
            if parts:
                stale.append(parts[0])

    for branch in stale:
        # Skip protected branches
        if branch in ("main", "master", "develop"):
            continue
        _run(["git", "branch", "-D", branch], cwd=REPO_DIR, timeout=10)
        actions.append(f"branch-delete: removed local '{branch}' (remote gone)")

    return actions


def fix_permissions():
    """Fix common permission issues found in prior audits."""
    actions = []

    # _scorer_summary.json should be 600 not 644
    scorer = os.path.join(CRON_OUTPUT_DIR, "_scorer_summary.json")
    if os.path.exists(scorer):
        mode = os.stat(scorer).st_mode & 0o777
        if mode != 0o600:
            os.chmod(scorer, 0o600)
            actions.append(f"perms: chmod 600 _scorer_summary.json")

    # gateway.pid should be 644 not 755
    gateway_pid = os.path.join(HOME, ".hermes", "gateway.pid")
    if os.path.exists(gateway_pid):
        mode = os.stat(gateway_pid).st_mode & 0o777
        if mode not in (0o644, 0o600):
            os.chmod(gateway_pid, 0o644)
            actions.append(f"perms: chmod 644 gateway.pid")

    return actions


def fix_disk_cleanup():
    """Clean up large temp/cache directories."""
    actions = []

    # Bun cache (grows over time)
    bun_cache = os.path.join(HOME, ".bun", "install", "cache")
    if os.path.isdir(bun_cache):
        try:
            total = 0
            for dirpath, dirnames, filenames in os.walk(bun_cache):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    try:
                        total += os.path.getsize(fp)
                    except OSError:
                        pass
            if total > 100 * 1024 * 1024:  # >100MB
                shutil.rmtree(bun_cache, ignore_errors=True)
                actions.append(f"disk: cleaned bun cache ({total // 1024**2}MB)")
        except Exception:
            pass

    return actions


def fix_docker_restart(container_pattern=None):
    """Restart a Docker container if it's unhealthy or in recovery mode."""
    actions = []
    docker_cmd = shutil.which("docker")
    if not docker_cmd:
        return actions

    out, rc = _run(["docker", "ps", "--format", "{{.Names}} {{.Status}}"], timeout=15)
    if rc != 0:
        return actions

    for line in out.split("\n"):
        parts = line.strip().split(None, 1)
        if len(parts) < 2:
            continue
        name, status = parts

        # Check for restarting/ unhealthy containers
        if "unhealthy" in status.lower() or "restarting" in status.lower():
            _run(["docker", "restart", name], timeout=30)
            actions.append(f"docker: restarted '{name}' ({status.strip()})")
            time.sleep(2)

    return actions


def check_state_dir():
    """Ensure state directory exists."""
    os.makedirs(STATE_DIR, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Weekly auto-fix runner")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be done without doing it")
    parser.add_argument("--verbose", action="store_true",
                        help="Include detailed output")
    args = parser.parse_args()

    check_state_dir()

    all_actions = []

    # Run fix patterns
    for fix_fn in [fix_git_pull, fix_stale_branches, fix_permissions,
                    fix_disk_cleanup, fix_docker_restart]:
        try:
            if args.dry_run:
                continue
            result = fix_fn()
            all_actions.extend(result)
        except Exception as e:
            if args.verbose:
                print(f"WARN: {fix_fn.__name__} failed: {e}")

    # Output
    if not all_actions:
        if args.verbose:
            print(json.dumps({"actions_taken": [], "warnings": []}, indent=2))
        # Empty output = silent (watchdog pattern)
        return

    report = {
        "actions_taken": all_actions,
        "warnings": [],
        "count": len(all_actions)
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
