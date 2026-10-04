#!/usr/bin/env python3
"""Non-destructive deployed-state check for the task-queue remediation.

Cycle 10577's closing note could only PASTE this state (adversarial findings
ADV-10577-6 and ADV-10577-7). This script makes it checkable: it changes
nothing and exits non-zero on any mismatch.

    python3 ops/scripts/manage/check-remediation-state.py

Gated checks
  1. deployed mcp-servers/task-mcp.py == the repo source, beyond the deploy banner
  2. deployed task-db.py carries the SPLIT pending board (claimable / story)
  3. state/update-commit == git HEAD                      (deploy is current)
  4. git rev-list origin/main..HEAD is empty              (nothing unpushed)
  5. ops/docs/ holds no tracked file and no non-empty file

Reported, never gated (environment conditions needing an operator action)
  - a running task-mcp daemon older than the deployed file. The MCP server
    loads its module once at spawn, so its board output stays stale until the
    gateway restarts, which is agent-blocked by design.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DEPLOY = Path.home() / ".hermes-cortex"
DEPLOY_SCRIPTS = DEPLOY / "scripts"
UPDATE_COMMIT = DEPLOY / "state" / "update-commit"
SOURCE_HEADER = "# SOURCE:"


def _run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _strip_deploy_banner(text: str) -> str:
    """cortex-update prepends a 3-line banner under the shebang of .py files."""
    lines = text.splitlines(keepends=True)
    if len(lines) > 3 and lines[1].startswith(SOURCE_HEADER):
        return "".join(lines[:1] + lines[4:])
    return text


def check_task_mcp_matches_repo() -> str:
    deployed_path = DEPLOY_SCRIPTS / "task-mcp.py"
    deployed = _read(deployed_path)
    if deployed is None:
        return f"SKIP no deployed tree ({deployed_path})"
    repo = (REPO / "mcp-servers" / "task-mcp.py").read_text(encoding="utf-8")
    if _strip_deploy_banner(deployed) != repo:
        return ("FAIL deployed task-mcp.py differs from the repo source beyond the "
                "deploy banner - run: bash ops/scripts/cortex-update.sh")
    return "PASS deployed task-mcp.py == repo source"


def check_split_board_is_deployed() -> str:
    deployed = _read(DEPLOY_SCRIPTS / "task-db.py")
    if deployed is None:
        return f"SKIP no deployed tree ({DEPLOY_SCRIPTS / 'task-db.py'})"
    missing = [b for b in ("pending (claimable)", "pending (story, not claimable)")
               if b not in deployed]
    if missing:
        return ("FAIL deployed task-db.py lacks the split board buckets: "
                + ", ".join(missing) + " - run: bash ops/scripts/cortex-update.sh")
    return "PASS deployed task-db.py carries the split pending board"


def check_deploy_is_current() -> str:
    deployed = _read(UPDATE_COMMIT)
    if deployed is None:
        return f"SKIP no deploy tree ({UPDATE_COMMIT})"
    rc, head = _run(["git", "-C", str(REPO), "rev-parse", "HEAD"])
    if rc != 0 or not head:
        return "FAIL cannot resolve git HEAD"
    if deployed.strip() != head:
        return (f"FAIL HEAD ({head[:12]}) is not deployed "
                f"(state/update-commit={deployed.strip()[:12]}) - "
                "run: bash ops/scripts/cortex-dogfood.sh")
    return f"PASS state/update-commit == HEAD ({head[:12]})"


def check_nothing_unpushed() -> str:
    rc, out = _run(["git", "-C", str(REPO), "rev-list", "origin/main..HEAD"])
    if rc != 0:
        return "SKIP cannot compare with origin/main"
    if out.strip():
        return (f"FAIL {len(out.split())} commit(s) unpushed - run: git push origin main")
    return "PASS nothing unpushed"


def check_ops_docs_holds_no_real_content() -> str:
    """ops/docs/ is NOT a path this repo uses. A 0-byte stray file is known to
    sit there pending an operator-approved deletion (deletion is gated by the
    destructive-action approval prompt, which timed out unanswered). Real
    content landing there is a bug, so this fails if any appears."""
    stray = REPO / "ops" / "docs"
    if not stray.exists():
        return "PASS ops/docs/ absent"
    rc, tracked = _run(["git", "-C", str(REPO), "ls-files", "ops/docs"])
    if tracked.strip():
        return ("FAIL ops/docs/ holds git-tracked file(s): "
                + ", ".join(tracked.split()) + " - this path is not used by the repo")
    nonempty = [p for p in stray.rglob("*") if p.is_file() and p.stat().st_size > 0]
    if nonempty:
        return ("FAIL ops/docs/ holds non-empty file(s): "
                + ", ".join(str(p.relative_to(REPO)) for p in nonempty))
    return "PASS ops/docs/ holds no tracked file and no non-empty file"


def report_stale_daemon() -> str:
    """Informational: the running MCP server predates the deployed file."""
    deployed_path = DEPLOY_SCRIPTS / "task-mcp.py"
    if not deployed_path.is_file():
        return "INFO no deployed tree"
    rc, out = _run(["pgrep", "-af", "task-mcp.py"])
    if rc != 0 or not out.strip():
        return "INFO no running task-mcp daemon"
    return ("INFO a task-mcp daemon is running; the MCP server loads its module "
            "once at spawn, so a daemon started before the deployed file was "
            "written serves the OLD board until the gateway restarts "
            "(agent-blocked - operator action)")


CHECKS = (
    check_task_mcp_matches_repo,
    check_split_board_is_deployed,
    check_deploy_is_current,
    check_nothing_unpushed,
    check_ops_docs_holds_no_real_content,
)


def main() -> int:
    failed = 0
    for check in CHECKS:
        result = check()
        print(f"{result}  [{check.__name__}]")
        if result.startswith("FAIL"):
            failed += 1
    print(report_stale_daemon())
    print()
    if failed:
        print(f"RESULT: FAIL ({failed} check(s) failed)")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
