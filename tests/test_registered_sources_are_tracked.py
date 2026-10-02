#!/usr/bin/env python3
"""Every deploy source must exist AND be tracked by git.

The class this guards (found 2026-10-02, by a peer agent's doctor run, not by me):

  .gitignore carries a deliberate guard against committing secret VALUES —
  *secret*, *credential*, *cred*, *token*, *.p12. I added a helper whose NAME
  matched it (env-secret.sh). `git add -A` skipped it SILENTLY (no error, no
  warning), so the commit that shipped the register() entry did NOT ship the file.
  On my host everything worked — the deploy copies from the WORKING TREE — so the
  defect was invisible here and broke every other host with "source missing".

Silent-skip is the whole problem: a file that is ignored can never arrive upstream,
yet nothing in a normal dev loop says so. Git is the ground truth here, so this
asserts against git rather than against any marker a session could forge:

  1. every register() source must EXIST in the tree;
  2. it must be TRACKED by git (an ignored file is not);
  3. it must not be matched by any ignore rule — reported explicitly so the fix is
     obvious (rename it, or track it deliberately) rather than a puzzle.

Measured before asserting: 283 register() entries, 0 missing, 0 untracked — so the
invariant holds fleet-wide and this test is not fighting legitimate exceptions.
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _registered_pairs() -> list[tuple[str, str]]:
    sh = (REPO / "ops" / "scripts" / "cortex-update.sh").read_text()
    return re.findall(r'^register\s+"([^"]+)"\s+"([^"]+)"', sh, re.M)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def test_registered_sources_are_tracked() -> None:
    pairs = _registered_pairs()
    assert pairs, "parsed 0 register() entries — the parser, not the repo, is broken"

    missing, untracked, ignored = [], [], []
    for src, _dst in pairs:
        if not (REPO / src).exists():
            missing.append(src)
            continue
        if _git("ls-files", "--error-unmatch", src).returncode != 0:
            untracked.append(src)
            if _git("check-ignore", "-v", src).returncode == 0:
                ignored.append(src)

    problems = []
    if missing:
        problems.append(f"{len(missing)} registered source(s) do not exist: {missing[:5]}")
    if untracked:
        detail = f"{len(untracked)} registered source(s) are not tracked by git: {untracked[:5]}"
        if ignored:
            detail += (f" — {len(ignored)} of them are matched by an ignore rule "
                       f"(a file that is ignored can NEVER reach other hosts, while the deploy "
                       f"still works locally from the working tree: {ignored[:3]})")
        problems.append(detail)

    assert not problems, (
        f"deploy manifest integrity ({len(pairs)} entries checked): " + "; ".join(problems)
        + " — rename the artifact out of the ignore pattern, or track it deliberately "
          "(never rely on git add -A to pick up an ignored file)."
    )


if __name__ == "__main__":
    test_registered_sources_are_tracked()
    pairs = _registered_pairs()
    print(f"✅ all {len(pairs)} registered deploy sources exist and are tracked by git")
    sys.exit(0)
