#!/usr/bin/env python3
"""Show a worker EXACTLY what the close review's material window will show them.

WHY (2026-10-12): cycle 12307 took six review rounds because the worker could not see the
window it was writing evidence for — it guessed at the budget, shrank a file to 244 bytes
and STILL came back "318 of 1118 omitted". One command that prints the bounded material
turns six rounds of guessing into a pre-commit check.

Portability: pure Python 3 (stdlib only) and plain `git`. It runs on Linux AND macOS and in
ANY repo, with or without Hermes or cortex installed — a Pi / Claude Code / plain-shell
session can check its own material before committing. The material-bounding code is the
gate's own, so what this prints is what the reviewer gets; when no gate copy can be found it
says so and exits 0 rather than pretending.

Usage:
  review-material.py [--repo DIR] [--base REV] [--tip REV] [--budget N] [--note TEXT]
  review-material.py --self-test            # exercise the reporter on a synthetic diff

Exit: 0 = reported (or nothing to report); 1 = a changed file would be shown with almost no
body (< 200 chars), i.e. evidence you have not yet made visible; 2 = usage/setup problem.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

MIN_USEFUL = 200          # chars; below this a reviewer cannot judge the file at all
GATE_CANDIDATES = (
    "mcp-servers/loop-gov-mcp.py",
    "~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py",
)


def _git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if p.returncode != 0:
        sys.stderr.write(f"git {' '.join(args)} failed: {p.stderr.strip()}\n")
        sys.exit(2)
    return p.stdout


def _load_gate(repo: Path):
    """The gate module, from the repo checkout or the deployed copy. None if absent."""
    for cand in GATE_CANDIDATES:
        p = Path(cand).expanduser()          # expand FIRST: "~/…" joined to a repo is not a path
        if not p.is_absolute():
            p = repo / cand
        if not p.is_file():
            continue
        spec = importlib.util.spec_from_file_location("loop_gov_mcp_preview", p)
        if spec is None or spec.loader is None:
            continue
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, p
    return None, None


def report(diff: str, gate) -> int:
    """Print per-file what the bound shows, and whether that is enough to judge."""
    sections = gate._split_diff_sections(diff)
    budget = gate.DIFF_CHAR_BUDGET
    if gate._range_is_docs_only(diff):
        budget = gate.DIFF_CHAR_BUDGET_DOCS
    bounded = gate._bound_diff(diff)
    print(f"changed files: {len(sections)}   budget: {budget} chars"
          f"   diff: {len(diff)} chars")
    print(f"{'shown':>7}  {'of':>7}  file")
    thin = []
    for path, text in sections:
        marker = re.search(r"bounded: (\d+) of " + str(len(text)) + r" chars omitted", bounded)
        shown = len(text) - int(marker.group(1)) if marker else len(text)
        if marker:
            thin.append((path, shown, len(text)))
        print(f"{shown:>7}  {len(text):>7}  {path or '(preamble)'}")
    if thin:
        print("\nBOUNDED (a reviewer sees head+tail of these):")
        for path, shown, total in thin:
            print(f"  {path}: {shown} of {total} chars")
    too_thin = [(p, s, t) for p, s, t in thin if s < MIN_USEFUL]
    if too_thin:
        print("\nTOO THIN to judge (< %d chars shown):" % MIN_USEFUL)
        for path, shown, total in too_thin:
            print(f"  {path}: {shown} of {total}")
        print("\nFix by shrinking the file, splitting the range, or making it smaller by design"
              "\n(ops/scripts/make-evidence.sh writes that shape).")
        return 1
    print("\nEvery changed file is shown with a body a reviewer can judge.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default="")
    ap.add_argument("--tip", default="HEAD")
    ap.add_argument("--note", default="", help="the note you intend to submit (printed as-is)")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--gate", choices=("auto", "repo", "deployed"), default="auto",
                    help="which copy of the bounding code to use (default: repo, then deployed)")
    a = ap.parse_args()

    repo = Path(a.repo).expanduser().resolve()
    global GATE_CANDIDATES
    if a.gate == "deployed":
        GATE_CANDIDATES = ("~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py",)
    elif a.gate == "repo":
        GATE_CANDIDATES = ("mcp-servers/loop-gov-mcp.py",)
    gate, gate_path = _load_gate(repo)
    if gate is None:
        print("No gate module found (looked for: " + ", ".join(GATE_CANDIDATES) + ").")
        print("Nothing to preview here — this repo has no governance material window.")
        return 0
    print(f"gate: {gate_path}")

    if a.self_test:
        small = "".join(
            f"diff --git a/docs/evidence/e{i}.txt b/docs/evidence/e{i}.txt\n"
            f"--- a/docs/evidence/e{i}.txt\n+++ b/docs/evidence/e{i}.txt\n@@ -0,0 +1,40 @@\n"
            + "".join(f"+ line {k}\n" for k in range(40)) for i in range(3))
        code = ("diff --git a/ops/scripts/thing.py b/ops/scripts/thing.py\n"
                "--- a/ops/scripts/thing.py\n+++ b/ops/scripts/thing.py\n@@ -0,0 +1,300 @@\n"
                + "".join(f"+ x = {k}\n" for k in range(300)))
        rc = report(small + code, gate)
        print(f"self-test rc={rc} (0 means the reporter judged every file visible)")
        return rc

    base = a.base or _git(repo, "merge-base", "origin/main", "HEAD").strip()
    # MIRROR THE REVIEW'S COMPOSITION (2026-10-12). The close review does NOT bound a plain
    # `git diff`: it builds `git log -p` for THIS author (so a path appears once per commit
    # that touches it) and appends other authors' commits. A preview built with `git diff`
    # is a different material, and previewing it hid exactly what the reviewer complained
    # about. Same shape here, minus the provenance prose.
    author = _git(repo, "log", "-1", "--format=%an", a.tip).strip()
    mine = _git(repo, "log", "--format=%H", f"--author={author}", f"{base}..{a.tip}").split()
    diff = _git(repo, "log", "-p", "--no-ext-diff", "-U3", f"--author={author}", f"{base}..{a.tip}")
    allc = [s for s in _git(repo, "log", "--format=%H", f"{base}..{a.tip}").split() if s.strip()]
    others = [s for s in allc if s not in set(mine)]
    if others:
        print(f"NOTE: {len(others)} commit(s) in this range are NOT yours; they are in the "
              f"material too (mirrors the review's provenance block).")
        diff += _git(repo, "show", "-p", "--no-ext-diff", "-U3", *others)
    untracked = [u for u in _git(repo, "ls-files", "--others", "--exclude-standard").splitlines() if u.strip()]
    if not diff.strip():
        print(f"no diff between {base} and the working tree — nothing for a reviewer to see")
        if untracked:
            print("untracked files are NOT in a diff; `git add` them to preview their material:")
            for u in untracked[:20]:
                print(f"  {u}")
        return 0
    if untracked:
        print(f"NOTE: {len(untracked)} untracked file(s) are NOT part of this diff (a reviewer "
              f"sees them only once committed):")
        for u in untracked[:10]:
            print(f"  {u}")

    # SAME-REPO CONCURRENT SESSIONS (2026-10-12): another session in this repo can put its
    # own commits inside YOUR range, and every one of them consumes the same material
    # window — a peer's evidence files are why your code diff shows as "6526 of 6526
    # omitted". Show the range's commits so a worker sees whose work it is carrying.
    log = _git(repo, "log", "--format=%h %an %s", f"{base}..{a.tip}")
    commits = [l for l in log.splitlines() if l.strip()]
    print(f"range {base[:12]}..{a.tip}  ({len(commits)} commit(s))")
    for line in commits:
        print(f"  {line}")
    if len(commits) > 1:
        print("  ^ if any of those are NOT yours, their files are in your material too:"
              "\n    land them in their own cycle, or expect the window to be shared")

    if a.note:
        print(f"\nYour note (submitted separately, shown to the reviewer as-is):\n  {a.note}\n")
    return report(diff, gate)


if __name__ == "__main__":
    sys.exit(main())
