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

Exit 0 = no deployed skill file holds content the repo does not have.
Exit 1 = at least one does (listed), or the committed artifact is stale.

DIRECTION IS DECIDED BY CONTENT, NOT BY MTIME. A file is STRANDED when its
deployed content appears neither in the repo working tree nor in any committed
revision of that path — i.e. the content exists only on the deployed side. If
the deployed content matches an older commit, the repo is simply ahead and a
deploy is pending, which is normal and not reported. mtime is deliberately
unused: `git clone` / `git checkout` reset every repo mtime to "now", which is
exactly what made an mtime-based check (the doctor's) call genuinely stranded
content "repo-newer" and stay silent.

Compares every file under the deployed skills tree that has a repo counterpart,
not just SKILL.md: the doctor's check only looks at SKILL.md, so a drifted
reference or script is invisible to it. Deploy banners are not compared —
deployed copies get a 3-line SOURCE header the repo copy does not carry.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_SKILLS = Path(__file__).resolve().parents[3] / "skills"
DEPLOY_SKILLS = Path.home() / ".hermes" / "skills"
ARTIFACT = REPO_SKILLS.parent / "docs" / "evidence" / "skill-drift-parity.txt"

BANNER = "# SOURCE:"
SKIP_PARTS = ("__pycache__", ".archive")
HISTORY_LIMIT = 300  # revisions of one path to search before giving up


def _strip_banner(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if lines and lines[0].startswith(BANNER):
        return "".join(lines[3:])
    if len(lines) > 1 and lines[1].startswith(BANNER):
        return "".join(lines[:1] + lines[4:])
    return text


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def _content_in_history(rel_to_root: str, content: str) -> bool:
    """True when some committed revision of this path carries this content.

    Runs against REPO_SKILLS.parent, so a caller that points REPO_SKILLS at a
    checkout of an older revision searches only that revision's ancestors.
    """
    root = REPO_SKILLS.parent
    try:
        revs = _git(root, "log", f"-n{HISTORY_LIMIT}", "--format=%H",
                    "--", rel_to_root).split()
    except RuntimeError:
        return False
    for rev in revs:
        try:
            blob = _git(root, "show", f"{rev}:{rel_to_root}")
        except RuntimeError:
            continue
        if _strip_banner(blob) == content:
            return True
    return False


def survey() -> tuple[list[str], int, int]:
    """Return (stranded_labels, in_sync_count, skipped_count)."""
    stranded: list[str] = []
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
        try:
            deployed = _strip_banner(dep.read_text(encoding="utf-8"))
            working = _strip_banner(repo.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            skipped += 1
            continue
        if deployed == working:
            in_sync += 1
            continue
        if _content_in_history(f"skills/{rel}", deployed):
            skipped += 1  # an older committed revision: deploy pending, not stranding
            continue
        stranded.append(str(rel))
    return stranded, in_sync, skipped


def build() -> tuple[str, bool]:
    stranded, in_sync, skipped = survey()
    ok = not stranded
    lines = [
        "# Skill source parity - deployed tree vs repo source",
        "",
        "Regenerate with: `python3 ops/scripts/manage/check-skill-drift-parity.py`",
        "",
        "A deployed skill file whose content appears in neither the repo working",
        "tree nor any committed revision of that path means a lesson was written on",
        "this host and never copied back: it is stranded here, and the deploy's",
        "drift guardrail refuses to overwrite it, so it never reaches the fleet.",
        "Direction is decided by content, not mtime, so a fresh clone cannot hide it.",
        "Deploy banners (the 3-line SOURCE header) are not compared.",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Deployed-only files (stranded) | {len(stranded)} |",
        f"| Files in sync | {in_sync} |",
        f"| Skipped (no repo counterpart, or repo ahead) | {skipped} |",
        "",
        f"**Verdict: {'PASS' if ok else 'FAIL'}**",
    ]
    if stranded:
        lines += ["", "Stranded files:"] + [f"- {p}" for p in stranded]
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
