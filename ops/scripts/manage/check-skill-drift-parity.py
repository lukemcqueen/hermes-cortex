#!/usr/bin/env python3
"""Skill source parity — does the repo carry what the deployed tree carries?

The deployed skills tree is the one agents actually read; the repo is what the
fleet receives. When a lesson is written into a deployed skill and never copied
back, it is stranded on one host and the next cortex-update would have
overwritten it (the deploy's drift guardrail skips such files, so they simply
never propagate). The doctor reports this as a WARN; this check makes it a
non-zero exit so the condition can be gated.

    python3 ops/scripts/manage/check-skill-drift-parity.py
    python3 ops/scripts/manage/check-skill-drift-parity.py --check   # compare only

Exit 0 = no deployed skill file is newer than its repo counterpart.
Exit 1 = at least one is (list them), or the committed artifact is stale.

Compares every file under the deployed skills tree that has a repo counterpart,
not just SKILL.md: the doctor's check only looks at SKILL.md, so a drifted
reference or script is invisible to it. Deploy banners are not compared —
deployed copies get a 3-line SOURCE header the repo copy does not carry.

Direction is decided by mtime, as in the doctor. That is a real limitation: a
fresh `git clone` or `git checkout` resets every repo mtime to "now", so a
deployed copy that is genuinely newer is then classified as repo-newer and the
check stays silent. Treat a PASS as "no file was *seen* to be newer", not as
proof that no lesson is stranded.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
REPO_SKILLS = REPO / "skills"
DEPLOY_SKILLS = Path.home() / ".hermes" / "skills"
ARTIFACT = REPO / "docs" / "evidence" / "skill-drift-parity.txt"

BANNER = "# SOURCE:"
SKIP_PARTS = ("__pycache__", ".archive")


def _strip_banner(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if lines and lines[0].startswith(BANNER):
        return "".join(lines[3:])
    if len(lines) > 1 and lines[1].startswith(BANNER):
        return "".join(lines[:1] + lines[4:])
    return text


def _digest(path: Path) -> str:
    return hashlib.sha256(_strip_banner(path.read_text(encoding="utf-8")).encode()).hexdigest()


def survey() -> tuple[list[str], int, int]:
    """Return (deployed_newer_labels, in_sync_count, skipped_count)."""
    deployed_newer: list[str] = []
    in_sync = 0
    skipped = 0
    for dep in sorted(DEPLOY_SKILLS.rglob("*")):
        if not dep.is_file():
            continue
        rel = dep.relative_to(DEPLOY_SKILLS)
        if any(p in rel.parts for p in SKIP_PARTS) or dep.suffix == ".pyc":
            continue
        repo = REPO_SKILLS / rel
        if not repo.is_file():
            skipped += 1  # Hermes default — not ours
            continue
        if _digest(dep) == _digest(repo):
            in_sync += 1
            continue
        if dep.stat().st_mtime > repo.stat().st_mtime + 60:
            deployed_newer.append(str(rel))
        else:
            skipped += 1  # repo-newer: a normal pending deploy, not stranding
    return deployed_newer, in_sync, skipped


def build() -> tuple[str, bool]:
    deployed_newer, in_sync, skipped = survey()
    ok = not deployed_newer
    lines = [
        "# Skill source parity - deployed tree vs repo source",
        "",
        "Regenerate with: `python3 ops/scripts/manage/check-skill-drift-parity.py`",
        "",
        "A deployed skill file newer than its repo counterpart means a lesson was",
        "written on this host and never copied back: it is stranded here, and the",
        "deploy's drift guardrail will refuse to overwrite it, so it never reaches",
        "the fleet. Deploy banners (the 3-line SOURCE header) are not compared.",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Deployed-newer files (stranded) | {len(deployed_newer)} |",
        f"| Files in sync | {in_sync} |",
        f"| Skipped (no repo counterpart, or repo-newer) | {skipped} |",
        "",
        f"**Verdict: {'PASS' if ok else 'FAIL'}**",
    ]
    if deployed_newer:
        lines += ["", "Stranded files:"] + [f"- {p}" for p in deployed_newer]
    return "\n".join(lines) + "\n", ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Skill source parity check")
    ap.add_argument("--check", action="store_true",
                    help="compare against the committed artifact, do not write")
    args = ap.parse_args()

    text, ok = build()

    if args.check:
        if not ARTIFACT.is_file():
            print(f"MISSING artifact: {ARTIFACT}")
            return 1
        if ARTIFACT.read_text(encoding="utf-8") != text:
            print("STALE artifact - regenerate: "
                  "python3 ops/scripts/manage/check-skill-drift-parity.py")
            return 1
        if not ok:
            print("artifact matches, but the parity claim it records does NOT hold")
            return 1
        print("artifact matches the live derivation")
        return 0

    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
