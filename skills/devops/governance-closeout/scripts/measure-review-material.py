#!/usr/bin/env python3
"""Measure a candidate CLOSE range against the review gate's OWN material bound.

WHY THIS EXISTS. The close gate cuts the diff it hands the reviewer to a character
budget, allocated PER FILE across the range. When a range is over budget, whole
files shrink to a head+tail sliver and the reviewer files `unverified-claim` /
`fabrication` findings about code that IS committed and tested — findings that no
rewrite of a note can answer, because the material is what is short. Guessing which
range will fit wastes a full review round per attempt; this prints the answer.

It imports the gate's own `_bound_diff` / `_range_is_docs_only` / budget constants
from the deployed MCP server, so the verdict is the gate's, not a re-implementation
(a second, looser copy of the rule is how the rule stops meaning anything).

USAGE
  measure-review-material.py [--repo PATH] [--base REV] [--head REV] [paths...]

  No --base: uses the merge-base of HEAD with origin/main (the usual push range).
  Trailing paths restrict the measurement to a subset, which is how you test a
  PROPOSED wave split before committing it.

EXIT CODES
  0  every measured range fits — the reviewer sees it whole
  1  something is cut — split the range into waves before closing
  3  COULD NOT VERIFY: the gate's module could not be imported (never treat as 0)
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import contextlib
import pathlib
import subprocess
import sys

DEFAULT_REPO = pathlib.Path.home() / "hermes-cortex"
GATE_REL = pathlib.Path("mcp-servers") / "loop-gov-mcp.py"


def run(args: list[str], cwd: pathlib.Path) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if out.returncode != 0 and args[:1] != ["diff"]:
        print(f"git {' '.join(args)} failed: {out.stderr.strip()}", file=sys.stderr)
    return out.stdout


def load_gate(repo: pathlib.Path):
    """Import the deployed gate module and return it (import prints a warning)."""
    path = repo / GATE_REL
    if not path.is_file():
        return None, f"gate module not found at {path}"
    spec = importlib.util.spec_from_file_location("review_gate", path)
    if spec is None or spec.loader is None:
        return None, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    buf = io.StringIO()
    try:
        # The module warns on stderr when the mcp package is absent; that is not a
        # failure here (we only need its pure helpers), so keep it out of the output.
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            spec.loader.exec_module(mod)
    except SystemExit as exc:  # a dependency check called sys.exit()
        return None, f"gate module exited during import (code {exc.code})"
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        return None, f"gate module failed to import: {exc!r}"
    return mod, ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure a close range against the gate's material bound.")
    ap.add_argument("--repo", default=str(DEFAULT_REPO))
    ap.add_argument("--base")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("paths", nargs="*")
    a = ap.parse_args()

    repo = pathlib.Path(a.repo).expanduser().resolve()
    base = a.base
    if not base:
        base = run(["merge-base", a.head, "origin/main"], repo).strip()
        if not base:
            base = "origin/main"

    scope = ["--", *a.paths] if a.paths else []
    diff = run(["diff", f"{base}..{a.head}", *scope], repo)
    if not diff:
        print(f"no diff for {base}..{a.head}{' (subset)' if a.paths else ''}", file=sys.stderr)
        return 0

    mod, why = load_gate(repo)
    if mod is None:
        print(f"COULD NOT VERIFY: {why}", file=sys.stderr)
        print("  the gate's budget constants are not knowable from here; do NOT read this", file=sys.stderr)
        print("  as 'no truncation'. Deploy the repo copy, then re-run.", file=sys.stderr)
        return 3

    docs_only = mod._range_is_docs_only(diff)
    budget = mod.DIFF_CHAR_BUDGET_DOCS if docs_only else mod.DIFF_CHAR_BUDGET
    bounded = mod._bound_diff(diff)
    cut = len(bounded) < len(diff)

    files = sorted({ln[len("diff --git a/"):].split(" ")[0]
                    for ln in diff.splitlines() if ln.startswith("diff --git a/")})
    print(f"range        {base[:12]}..{a.head}")
    print(f"files        {len(files)}")
    print(f"diff chars   {len(diff)}")
    print(f"docs-only    {docs_only}   (standard budget {mod.DIFF_CHAR_BUDGET}, "
          f"docs budget {mod.DIFF_CHAR_BUDGET_DOCS})")
    print(f"budget       {budget}   per-file share ≈ {budget // max(len(files), 1)}")
    print(f"CUT          {cut}")
    if files:
        print("per file (chars of diff, and whether the reviewer sees it whole):")
        for f in files:
            one = run(["diff", f"{base}..{a.head}", "--", f], repo)
            if not one:
                continue
            whole = len(mod._bound_diff(one)) >= len(one)
            print(f"  {len(one):7}  {'whole' if whole else 'CUT  '}  {f}")
    print()
    print("A CUT range is not a smaller review — for the cut files it is no review. "
          "Split it into waves (pair each source file with its test), push each wave "
          "before committing the next, and re-run this on the next candidate.")
    return 1 if cut else 0


if __name__ == "__main__":
    sys.exit(main())
