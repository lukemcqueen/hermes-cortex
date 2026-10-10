#!/usr/bin/env python3
"""Reconcile stranded deployed-only skill files into the repo — REPORT by default.

A stranded file is one the DEPLOYED tree has and the repo (working tree or any
committed revision) does not: a lesson written on this host that the deploy's drift
guardrail refuses to overwrite, so the fleet never receives it. cortex-update.sh
tells the operator to "copy the deployed changes to the repo source first, then
commit" and ships no tool to do it — this is that tool.

Which files are stranded is NOT re-defined here: it calls the fleet's own
ops/scripts/manage/check-skill-drift-parity.py and parses its stranded list, so this
tool cannot drift from the detector's definition.

Direction is decided by CONTENT, never mtime:
  * the deployed copy is a pure superset (nothing dropped)  -> safe to apply
  * the deployed copy drops lines as well                   -> reported for review,
    with the dropped lines printed, and NOT applied
`--apply` therefore only ever copies the safe class. A rewrite needs a human or
agent decision, which is exactly what the dropped-lines listing is for.

Usage:
  reconcile-stranded-skills.py                 # report (exit 0 clean / 1 work left)
  reconcile-stranded-skills.py --apply         # apply the pure-superset class only
  reconcile-stranded-skills.py --repo DIR --deployed DIR
Exit: 0 nothing stranded · 1 stranded remain or review needed · 3 could not verify
"""
import argparse
import difflib
import pathlib
import shutil
import subprocess
import sys

DRIFT = pathlib.Path(__file__).resolve().parent / "check-skill-drift-parity.py"


def stranded_files(repo, drift_script=None):
    """The detector's stranded list + verdict, via its own output.

    `drift_script` is injectable so a test can drive this with a controlled
    detector (including one that FAILS to run) instead of the live tree.
    """
    # Resolve BEFORE the subprocess changes cwd to the repo: a relative
    # --drift-script would otherwise be looked up inside the repo and read as
    # "detector missing" (could-not-verify) instead of running.
    script = str(pathlib.Path(drift_script or DRIFT).resolve())
    try:
        r = subprocess.run([sys.executable, script], capture_output=True, text=True,
                           timeout=600, cwd=str(repo))
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"could not run {script}: {e}", None
    if r.returncode not in (0, 1):
        return None, f"{pathlib.Path(script).name} exited {r.returncode}: {r.stderr.strip()[:200]}", None
    out = r.stdout
    verdict = "PASS" if "Verdict: PASS" in out else ("FAIL" if "Verdict: FAIL" in out else "?")
    files, collecting = [], False
    for line in out.splitlines():
        if line.startswith("Stranded files:"):
            collecting = True
            continue
        if collecting:
            if line.startswith("- "):
                files.append(line[2:].strip())
            elif line.strip() == "":
                continue
            else:
                collecting = False
    return files, None, verdict


def classify(deployed_text, repo_text):
    """(added, dropped, dropped_lines) — counts plus the actual dropped lines."""
    diff = list(difflib.unified_diff(repo_text.splitlines(), deployed_text.splitlines(),
                                     lineterm="", n=0))
    added = sum(1 for x in diff if x.startswith("+") and not x.startswith("+++"))
    drops = [x[1:] for x in diff if x.startswith("-") and not x.startswith("---")]
    return added, len(drops), drops


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(pathlib.Path.home() / "hermes-cortex"))
    ap.add_argument("--deployed", default=str(pathlib.Path.home() / ".hermes-cortex/skills"))
    ap.add_argument("--apply", action="store_true",
                    help="copy the pure-superset class only (never a rewrite)")
    ap.add_argument("--drift-script", default=str(DRIFT),
                    help="the detector to take the stranded list from (test seam)")
    a = ap.parse_args()
    repo, deployed = pathlib.Path(a.repo), pathlib.Path(a.deployed)
    repo_skills = repo / "skills"

    files, err, verdict = stranded_files(repo, a.drift_script)
    if err:
        print(f"⚠️  COULD NOT VERIFY — {err}")
        return 3
    print(f"Detector verdict: {verdict} · stranded: {len(files)}")
    if not files:
        print("Nothing stranded: repo and deployed trees agree on content.")
        return 0

    review, applied, missing = [], [], []
    for rel in files:
        d, r = deployed / rel, repo_skills / rel
        if not d.is_file():
            print(f"SKIP     {rel}: deployed copy missing")
            missing.append(rel)
            continue
        if not r.is_file():
            if a.apply:
                r.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(d, r)
                applied.append(rel)
                print(f"ADDED    {rel}: no repo counterpart -> copied")
            else:
                print(f"NEW      {rel}: no repo counterpart (would be added)")
            continue
        added, dropped, drop_lines = classify(d.read_text(), r.read_text())
        if dropped == 0:
            if a.apply:
                shutil.copy2(d, r)
                applied.append(rel)
                print(f"APPLIED  {rel}: pure superset (+{added}, -0)")
            else:
                print(f"SUPERSET {rel}: pure superset (+{added}, -0) -> safe to apply")
        else:
            review.append(rel)
            print(f"REVIEW   {rel}: would drop {dropped} line(s), add {added} -> not applied")
            for ln in drop_lines:
                print(f"           DROP: {ln}")

    print()
    print(f"applied={len(applied)} need-review={len(review)} missing={len(missing)}"
          f"{'' if a.apply else '  (report only — rerun with --apply for the superset class)'}")
    if review:
        print("Review each DROP above: take the deployed side only where the dropped lines are")
        print("superseded in place; otherwise merge the additions by hand.")
    return 1 if (review or missing or (not a.apply and files)) else 0


if __name__ == "__main__":
    sys.exit(main())
