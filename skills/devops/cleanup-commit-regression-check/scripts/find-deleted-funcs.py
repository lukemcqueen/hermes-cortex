#!/usr/bin/env python3
"""Detect functions deleted by a commit vs its parent — catches mass-edit
passes that strip `def` lines while replacing no-op statements.

Usage:
    python3 find-deleted-funcs.py <commit> [--path-filter ops/scripts]

Exit 0: no single-function deletions (or all deletions are in wholesale
rewrites — reviewed manually).
Exit 1: at least one file has deleted functions; inspect output.
"""
import argparse
import ast
import os
import pathlib
import subprocess
import sys

# Portable default: run from the repo (or set HERMES_CORTEX_REPO).
REPO = os.environ.get("HERMES_CORTEX_REPO") or os.getcwd()


def funcs_of(text: str) -> set:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    return {n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("commit", help="suspicious commit (e.g. 84272894)")
    ap.add_argument("--path-filter", default="ops/scripts",
                    help="only scan paths containing this substring")
    ap.add_argument("--repo", default=REPO)
    args = ap.parse_args()

    stat = subprocess.run(["git", "show", "--stat", args.commit],
                          capture_output=True, text=True, cwd=args.repo)
    if stat.returncode != 0:
        print(stat.stderr, file=sys.stderr)
        return 2

    touched = []
    for line in stat.stdout.splitlines():
        parts = line.split("|")
        if (len(parts) == 2 and parts[0].strip().endswith(".py")
                and args.path_filter in parts[0]):
            touched.append(parts[0].strip())

    print(f"scanning {len(touched)} files touched by {args.commit} ...")
    found = 0
    for p in sorted(touched):
        cur = pathlib.Path(args.repo) / p
        if not cur.exists():
            continue
        parent = subprocess.run(["git", "show", f"{args.commit}^:{p}"],
                                capture_output=True, text=True, cwd=args.repo)
        if parent.returncode != 0:
            continue
        deleted = funcs_of(parent.stdout) - funcs_of(cur.read_text())
        if deleted:
            found += 1
            print(f"{p}: DELETED FUNCS: {sorted(deleted)}")
            print("  ^ if 1-3 functions deleted, this is likely collateral "
                  "damage — restore from `git show COMMIT^:path`")

    if found:
        print(f"\n{found} file(s) with deleted functions — investigate.")
        return 1
    print("no function deletions detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
