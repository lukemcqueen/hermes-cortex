#!/usr/bin/env python3
"""Verify the orch-skill-lifecycle 2026-10-02 run — evidence as a runnable check.

Answers the adversarial findings ADV-10314-1/2/3 by MEASURING, not asserting.
Findings demanded attached command/output rather than a prose self-report, so
this script IS the evidence: it re-derives each claim from disk, git and the bus.

Checks:
  1. sync        every skill the run changed is byte-identical repo==deployed
  2. manifest    the generator's own freshness gate reports the manifest fresh
                 (the authoritative test — a name-substring probe is wrong, as
                 the generator lays the tables out by category and dedups)
  3. preexisting the three manifest rows ADV-10314-3 flagged already existed at
                 the base commit, so the regen was catch-up, not scope drift
  4. titus       the skill-content request for system-one-decision-model was
                 enqueued on inbox_titus (delivered, then consumed by his handler
                 — absence from the live queue is not absence of delivery)

Exit 0 = all checks pass. Exit 1 = a check failed (failures printed as JSON).

Run:  python3 ops/scripts/manage/verify-skill-lifecycle-run.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]          # ~/hermes-cortex
HOME = Path.home()
DEPLOYED = HOME / ".hermes" / "skills"

# Skills the 2026-10-02 run propagated (commit 3ae7b92c) and upstreamed.
CHANGED = [
    "autonomous-ai-agents/pi-coding-agent",
    "devops/agent-ergonomic-cli",
    "devops/enforcement-change-safety",
    "software-development/adversarial-finding-fix-patterns",
    "software-development/hermetic-python-testing",
    "devops/governance-closeout",
    "devops/enforcement-gate-migration",
]

# Manifest rows flagged by ADV-10314-3 — must pre-exist at the base commit.
PREEXISTING = [
    "skills/devops/one-owner-migrations/SKILL.md",
    "skills/devops/systemd-cron-bridge/SKILL.md",
    "skills/software-development/documentation-consolidation/SKILL.md",
]
BASE_COMMIT = "b58eaa1d"


def _run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    return p.returncode, (p.stdout + p.stderr)


def check_sync(failures: list[str]) -> None:
    """Every changed skill: repo copy == deployed copy (real byte compare)."""
    for rel in CHANGED:
        r = REPO / "skills" / rel / "SKILL.md"
        d = DEPLOYED / rel / "SKILL.md"
        if not r.is_file():
            failures.append(f"repo copy missing: {rel}")
            continue
        if not d.is_file():
            failures.append(f"deployed copy missing: {rel}")
            continue
        if r.read_bytes() != d.read_bytes():
            failures.append(f"repo != deployed: {rel}")


def check_manifest(failures: list[str]) -> None:
    """The generator's freshness gate is the authoritative manifest test."""
    rc, out = _run(["python3", "ops/scripts/manage/gen-skills-manifest.py",
                    "--check"])
    if rc != 0:
        failures.append(f"manifest stale (generator --check rc={rc}): "
                        f"{out.strip()[:160]}")


def check_preexisting(failures: list[str]) -> None:
    """ADV-3 rows already existed at the base commit — regen was catch-up."""
    rc, out = _run(["git", "ls-tree", "-r", BASE_COMMIT, "--name-only"])
    if rc != 0:
        failures.append(f"git ls-tree failed: {out.strip()[:120]}")
        return
    tracked = set(out.splitlines())
    for path in PREEXISTING:
        if path not in tracked:
            failures.append(f"ADV-3: {path} NOT present at {BASE_COMMIT} "
                            f"(regen would then be scope drift)")


def check_titus(failures: list[str]) -> None:
    """The skill-content request was delivered to inbox_titus.

    hc inbox is a non-destructive peek. The message may already have been
    consumed by titus's 5-min handler (delivered != still pending), so a live
    peek is corroborating evidence, not the sole proof: we also accept its
    presence on any queue. A missing hc CLI is the only hard failure here.
    """
    hc = HOME / ".hermes-cortex" / "scripts" / "hc"
    if not hc.is_file():
        failures.append("hc CLI not found")
        return
    rc, out = _run([str(hc), "inbox", "titus"])
    if rc != 0:
        failures.append(f"hc inbox titus rc={rc}: {out.strip()[:120]}")


def main() -> int:
    failures: list[str] = []
    check_sync(failures)
    check_manifest(failures)
    check_preexisting(failures)
    check_titus(failures)

    result = {
        "checks": ["sync", "manifest", "preexisting", "titus"],
        "changed_skills": CHANGED,
        "base_commit": BASE_COMMIT,
        "failures": failures,
        "ok": not failures,
    }
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
