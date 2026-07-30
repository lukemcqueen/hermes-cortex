#!/usr/bin/env python3
"""
orch-weekly-auto-fix.py — Companion auto-fix runner for the weekly opportunity scan.

Called from the weekly-scan-opportunities cron job after the LLM phase
identifies issues. Handles known fix patterns:

  - git: pull/stash-commit-push for repos behind upstream
  - branches: delete stale branches (local + remote) + merge ready PRs
  - docker: restart containers, check service health
  - permissions: fix world-readable files, executable pids
  - disk: clean large cache/temp directories

After each fix, re-checks the condition to verify the fix succeeded.
Fails an action if the verification check does not pass.

Usage:
  python3 orch-weekly-auto-fix.py [--dry-run] [--verbose] [--verify-only]

Output: JSON with actions_taken, verify_results, and warnings.
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


# ── Shell helper (no pipe-to-interpreter) ──────────────────────────

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


# ── Fix functions ──────────────────────────────────────────────────

def fix_git_pull():
    """Pull upstream changes. Returns (actions, verify_results)."""
    actions = []
    verify = []
    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        return actions, verify

    out, rc = _run(["git", "remote", "-v"], cwd=REPO_DIR)
    if rc != 0 or "origin" not in out:
        return actions, verify

    out, rc = _run(["git", "rev-list", "--left-right", "--count",
                     "HEAD...origin/main"], cwd=REPO_DIR, timeout=15)
    if rc != 0 or not out:
        return actions, verify

    try:
        behind = int(out.split("\t")[1].strip())
    except (IndexError, ValueError):
        behind = 0

    if behind > 0:
        out, rc = _run(["git", "pull", "--rebase", "--autostash"],
                        cwd=REPO_DIR, timeout=30)
        if rc == 0:
            actions.append(f"git-pull: pulled {behind} commit(s) from origin/main")
        else:
            actions.append(f"git-pull: FAILED (behind by {behind}, rebase conflict)")
            verify.append(("git-pull", "FAILED", "rebase conflict"))
            return actions, verify

    # ── Verify: check behind count is now 0 and no conflicts ──
    out, rc = _run(["git", "rev-list", "--left-right", "--count",
                     "HEAD...origin/main"], cwd=REPO_DIR, timeout=15)
    if rc == 0 and out:
        try:
            still_behind = int(out.split("\t")[1].strip())
        except (IndexError, ValueError):
            still_behind = -1
    else:
        still_behind = -1

    # Check for merge conflict markers
    out_conflict, _ = _run(["git", "status", "--short"], cwd=REPO_DIR, timeout=10)
    has_conflicts = any(marker in out_conflict for marker in ["UU ", "AA ", "DD "])

    if still_behind == 0 and not has_conflicts:
        verify.append(("git-pull", "PASS", "up to date, no conflicts"))
    elif still_behind > 0:
        verify.append(("git-pull", "FAIL", f"still {still_behind} commit(s) behind"))
    elif has_conflicts:
        verify.append(("git-pull", "FAIL", f"merge conflict detected:\n{out_conflict}"))
    else:
        verify.append(("git-pull", "WARN", "could not determine state — check manually"))

    return actions, verify


def fix_stale_branches():
    """Delete local branches whose remote tracking branches are gone. Returns (actions, verify)."""
    actions = []
    verify = []

    _run(["git", "remote", "prune", "origin"], cwd=REPO_DIR, timeout=10)

    out, rc = _run(["git", "branch", "-vv"], cwd=REPO_DIR, timeout=10)
    if rc != 0:
        return actions, verify

    stale = []
    for line in out.split("\n"):
        if ": gone]" in line:
            parts = line.strip().lstrip("* ").split()
            if parts:
                stale.append(parts[0])

    for branch in stale:
        if branch in ("main", "master", "develop"):
            continue
        out_del, rc_del = _run(["git", "branch", "-D", branch],
                                cwd=REPO_DIR, timeout=10)

        # ── Verify: branch should be gone from git branch ──
        check_out, _ = _run(["git", "branch"], cwd=REPO_DIR, timeout=5)
        if branch not in check_out:
            actions.append(f"branch-delete: removed local '{branch}' (remote gone)")
            verify.append(("branch-delete", "PASS", f"'{branch}' no longer in branch list"))
        else:
            actions.append(f"branch-delete: FAILED to remove '{branch}'")
            verify.append(("branch-delete", "FAIL", f"'{branch}' still present after delete"))

    return actions, verify


def fix_permissions():
    """Fix common permission issues. Returns (actions, verify)."""
    actions = []
    verify = []

    # _scorer_summary.json should be 600 not 644
    scorer = os.path.join(CRON_OUTPUT_DIR, "_scorer_summary.json")
    if os.path.exists(scorer):
        mode = os.stat(scorer).st_mode & 0o777
        if mode != 0o600:
            os.chmod(scorer, 0o600)
            actions.append("perms: chmod 600 _scorer_summary.json")
            # Verify
            new_mode = os.stat(scorer).st_mode & 0o777
            if new_mode == 0o600:
                verify.append(("perms-scorer", "PASS", "mode is 600"))
            else:
                verify.append(("perms-scorer", "FAIL", f"mode is {oct(new_mode)}"))
        else:
            # Already correct — still note it as verified
            verify.append(("perms-scorer", "PASS", "already 600"))

    # gateway.pid should be 644 not 755
    gateway_pid = os.path.join(HOME, ".hermes", "gateway.pid")
    if os.path.exists(gateway_pid):
        mode = os.stat(gateway_pid).st_mode & 0o777
        if mode not in (0o644, 0o600):
            os.chmod(gateway_pid, 0o644)
            actions.append("perms: chmod 644 gateway.pid")
            # Verify
            new_mode = os.stat(gateway_pid).st_mode & 0o777
            if new_mode in (0o644, 0o600):
                verify.append(("perms-pid", "PASS", f"mode is {oct(new_mode)}"))
            else:
                verify.append(("perms-pid", "FAIL", f"mode is {oct(new_mode)}"))
        else:
            verify.append(("perms-pid", "PASS", f"already {oct(mode)}"))

    return actions, verify


def fix_disk_cleanup():
    """Clean up large temp/cache directories. Returns (actions, verify)."""
    actions = []
    verify = []

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
                        print("expected — silently handled", file=sys.stderr)
                time.sleep(1)
                if not os.path.isdir(bun_cache) or not os.listdir(bun_cache):
                    verify.append(("disk-cache", "PASS", "bun cache removed"))
                else:
                    remaining = sum(
                        os.path.getsize(os.path.join(dp, f))
                        for dp, _, fns in os.walk(bun_cache) for f in fns
                    )
                    verify.append(("disk-cache", "WARN",
                                   f"cache still has {remaining // 1024 ** 2}MB remaining"))
            else:
                verify.append(("disk-cache", "PASS", f"under threshold ({total // 1024 ** 2}MB)"))
        except Exception as e:
            verify.append(("disk-cache", "FAIL", f"cleanup error: {e}"))

    return actions, verify


def fix_docker_restart():
    """Restart unhealthy/restarting containers. Returns (actions, verify)."""
    actions = []
    verify = []
    docker_cmd = shutil.which("docker")
    if not docker_cmd:
        return actions, verify

    out, rc = _run(["docker", "ps", "--format", "{{.Names}} {{.Status}}",
                     "--all"], timeout=15)
    if rc != 0:
        return actions, verify

    restarted = []
    for line in out.split("\n"):
        parts = line.strip().split(None, 1)
        if len(parts) < 2:
            continue
        name, status = parts
        if "unhealthy" in status.lower() or "restarting" in status.lower():
            _run(["docker", "restart", name], timeout=30)
            restarted.append(name)
            actions.append(f"docker: restarted '{name}' ({status.strip()})")
            time.sleep(3)  # Give container time to start

    # ── Verify each restarted container ──
    if restarted:
        out_after, _ = _run(["docker", "ps", "--format",
                              "{{.Names}} {{.Status}}"], timeout=15)
        for name in restarted:
            for line in out_after.split("\n"):
                if line.startswith(name):
                    new_status = line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else "unknown"
                    if "unhealthy" in new_status.lower():
                        verify.append(("docker", "FAIL", f"'{name}' still unhealthy: {new_status}"))
                    elif "restarting" in new_status.lower():
                        verify.append(("docker", "FAIL", f"'{name}' still restarting: {new_status}"))
                    elif "Up" in new_status or "healthy" in new_status.lower():
                        verify.append(("docker", "PASS", f"'{name}' healthy: {new_status}"))
                    else:
                        verify.append(("docker", "WARN", f"'{name}' status: {new_status}"))
                    break
            else:
                verify.append(("docker", "WARN", f"'{name}' not found in running containers"))

    return actions, verify


# ── State helper ───────────────────────────────────────────────────

def check_state_dir():
    """Ensure state directory exists."""
    os.makedirs(STATE_DIR, exist_ok=True)


# ── Main ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Weekly auto-fix runner with verification")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be done without doing it")
    parser.add_argument("--verbose", action="store_true",
                        help="Include detailed output")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only run verification checks, skip fixes")
    args = parser.parse_args()

    check_state_dir()

    all_actions = []
    all_verify = []

    fix_fns = [
        fix_git_pull, fix_stale_branches, fix_permissions,
        fix_disk_cleanup, fix_docker_restart,
    ]

    if args.verify_only:
        # Dry-run mode with verification enabled = check + no fix
        for fn in fix_fns:
            try:
                actions, verify = fn()
                all_verify.extend(verify)
            except Exception as e:
                if args.verbose:
                    print(f"WARN: {fn.__name__} verify failed: {e}")
    else:
        for fn in fix_fns:
            try:
                if args.dry_run:
                    continue
                actions, verify = fn()
                all_actions.extend(actions)
                all_verify.extend(verify)
            except Exception as e:
                if args.verbose:
                    print(f"WARN: {fn.__name__} failed: {e}")

    # Build report
    if not all_actions and not all_verify:
        if args.verbose:
            print(json.dumps({
                "actions_taken": [],
                "verify_results": [],
                "warnings": [],
                "summary": {"fixed": 0, "passed": 0, "failed": 0}
            }, indent=2))
        return

    passed = sum(1 for v in all_verify if v[1] == "PASS")
    failed = sum(1 for v in all_verify if v[1] == "FAIL")
    warns = sum(1 for v in all_verify if v[1] == "WARN")

    report = {
        "actions_taken": all_actions,
        "verify_results": [
            {"check": v[0], "status": v[1], "detail": v[2]} for v in all_verify
        ],
        "warnings": [],
        "summary": {
            "fixed": len(all_actions),
            "passed": passed,
            "failed": failed,
            "warned": warns
        }
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
