#!/usr/bin/env python3
"""
apply-repo-efficiency.py — Add the Hermes fleet session-efficiency block to
any repo's AGENTS.md (creating it if absent), idempotently.

O7-S2 / AGENT-per-repo mods (Luke 2026-08-21). The block is additive:
marker-commented, never overwrites existing content, safe for client repos.

Usage:
    apply-repo-efficiency.py <repo-or-dir> [more dirs...]
    apply-repo-efficiency.py --scan <base-dir>     # find git repos under base
    apply-repo-efficiency.py --scan ~/dev --dry-run

Behavior:
  - Appends the block to <repo>/AGENTS.md (creates the file if missing).
  - Skips repos already carrying the marker (idempotent).
  - --dry-run prints what WOULD change without writing.
Exit: 0 all ok, 1 errors.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

MARKER = "<!-- Hermes fleet efficiency block"
# repo/ops/scripts/manage/apply-repo-efficiency.py -> repo root is parent x4
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BLOCK_PATH = _REPO_ROOT / "docs" / "templates" / "repo-efficiency-block.md"


def find_git_repos(base: Path) -> list[Path]:
    """Recursively find directories containing a .git (bounded depth 4)."""
    found = []
    base = base.resolve()
    for root, dirs, files in os.walk(base):
        depth = root[len(str(base)):].count(os.sep)
        if depth > 4:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "venv", ".venv", "dist", "build")]
        if ".git" in dirs or (Path(root) / ".git").exists():
            found.append(Path(root))
            dirs[:] = [d for d in dirs if d != ".git"]
    return found


def block_text() -> str:
    if not BLOCK_PATH.exists():
        print(f"❌ template missing: {BLOCK_PATH}", file=sys.stderr)
        sys.exit(1)
    return BLOCK_PATH.read_text(encoding="utf-8").rstrip() + "\n"


def apply_to(repo: Path, dry_run: bool, commit: bool = False) -> tuple[str, bool]:
    target = repo / "AGENTS.md"
    if target.exists():
        content = target.read_text(encoding="utf-8", errors="replace")
        if MARKER in content:
            return f"SKIP  {repo} (already has block)", False
        new_content = content.rstrip() + "\n\n" + block_text()
    else:
        new_content = block_text()
    if dry_run:
        return f"DRY   {repo} → {'append' if target.exists() else 'create'} AGENTS.md", False
    target.write_text(new_content, encoding="utf-8")
    if commit:
        try:
            subprocess.run(["git", "-C", str(repo), "add", "AGENTS.md"], check=True, capture_output=True)
            subprocess.run(
                ["git", "-C", str(repo), "commit", "-m", "docs: add Hermes fleet session-efficiency block (additive)"],
                check=True, capture_output=True,
            )
            return f"OK    {repo} → appended + committed AGENTS.md", True
        except subprocess.CalledProcessError as e:
            err = (e.stderr or b"").decode(errors="replace").strip().splitlines()
            detail = err[-1] if err else str(e)
            return f"WARN  {repo} → wrote AGENTS.md but commit failed: {detail[:80]}", True
    return f"OK    {repo} → {'appended' if target.exists() else 'created'} AGENTS.md", True


def main() -> int:
    ap = argparse.ArgumentParser(description="Add fleet session-efficiency block to repo AGENTS.md")
    ap.add_argument("paths", nargs="*", help="repo dirs or files (or use --scan)")
    ap.add_argument("--scan", metavar="BASE", help="find git repos under BASE and apply")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true", help="git add + commit the AGENTS.md change in each repo")
    args = ap.parse_args()

    targets: list[Path] = []
    if args.scan:
        targets = find_git_repos(Path(args.scan).expanduser())
        if not targets:
            print(f"no git repos found under {args.scan}")
            return 1
    else:
        for p in args.paths:
            pp = Path(p).expanduser()
            if pp.is_dir() and (pp / ".git").exists():
                targets.append(pp)
            elif pp.is_file():
                targets.append(pp.parent)
            else:
                print(f"⚠️  not a repo or missing: {p}")

    if not targets:
        print("no targets — pass repo dirs or --scan <base>")
        return 1

    changed = 0
    for t in sorted(set(targets)):
        msg, did = apply_to(t, args.dry_run, commit=args.commit)
        print(msg)
        changed += 1 if did else 0
    print(f"\n{changed} repo(s) would change" if args.dry_run else f"\n{changed} repo(s) updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
