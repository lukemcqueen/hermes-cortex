#!/usr/bin/env python3
"""Hermetic tests for ops/scripts/manage/reconcile-stranded-skills.py.

    python3 tests/test_reconcile_stranded_skills.py     # exit 0 = pass

Drives the REAL entry point as a subprocess against throwaway trees and a
CONTROLLED detector (the tool's --drift-script seam), so the assertions cannot
depend on whatever the live skill trees happen to look like — and so the
could-not-verify branch is exercised by CONSTRUCTING the failure.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "ops/scripts/manage/reconcile-stranded-skills.py"

# The DETECTOR's real contract, copied from check-skill-drift-parity.py: the metrics
# row is emitted ALWAYS (0 included) and the section is emitted only when non-empty.
# A stub that models a header the detector no longer prints makes every case pass for
# the wrong reason — which is how the rename below went unnoticed.
METRICS_ROW = "print('| Stranded in place (path in repo, content only deployed) | %d |')\n"
SECTION_HEADER = "Stranded in place:"

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


def make_trees(stranded_superset=(), stranded_rewrite=(), stranded_new=()):
    """Build (repo, deployed, drift_script) with exactly the stranded files asked for.

    --deployed points at the skills ROOT (as the tool's default does,
    ~/.hermes-cortex/skills), so deployed files live at deployed/<rel> while repo
    files live at repo/skills/<rel>.
    """
    tmp = Path(tempfile.mkdtemp(prefix="reconcile-"))
    repo, deployed = tmp / "repo", tmp / "deployed"
    (repo / "skills").mkdir(parents=True)
    deployed.mkdir(parents=True)

    rels = list(stranded_superset) + list(stranded_rewrite) + list(stranded_new)
    for rel in stranded_superset:                      # repo is the smaller, older text
        (deployed / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / "skills" / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / "skills" / rel).write_text("base\n")
        (deployed / rel).write_text("base\nadded one\nadded two\n")
    for rel in stranded_rewrite:                       # deployed drops a line
        (deployed / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / "skills" / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / "skills" / rel).write_text("keep me\nsuperseded line\n")
        (deployed / rel).write_text("keep me\nrewritten line\n")
    for rel in stranded_new:                           # no repo counterpart at all
        (deployed / rel).parent.mkdir(parents=True, exist_ok=True)
        (deployed / rel).write_text("brand new lesson\n")

    stub = tmp / "stub-drift.py"
    stub.write_text(
        METRICS_ROW % len(rels)
        + "print('| Files in sync | 1 |')\n"
        + "print('**Verdict: %s**')\n" % ("FAIL" if rels else "PASS")
        + ("print(%r)\n" % SECTION_HEADER if rels else "")
        + "".join(f"print('- {r}')\n" for r in rels)
        + "raise SystemExit(1 if %r else 0)\n" % bool(rels)
    )
    return repo, deployed, stub


def run(repo, deployed, stub, *extra):
    return subprocess.run(
        [sys.executable, str(TOOL), "--repo", str(repo), "--deployed", str(deployed),
         "--drift-script", str(stub), *extra],
        capture_output=True, text=True, timeout=120)


def main():
    check("tool exists", TOOL.is_file(), True)

    # 1. Nothing stranded -> clean exit, no writes.
    repo, deployed, stub = make_trees()
    r = run(repo, deployed, stub)
    check("clean tree exits 0", r.returncode, 0)
    check("clean tree says so", "Nothing stranded" in r.stdout, True)

    # 2. Report mode does NOT write (the whole point of the default).
    repo, deployed, stub = make_trees(stranded_superset=("devops/a/SKILL.md",))
    r = run(repo, deployed, stub)
    check("report mode exits 1 when work remains", r.returncode, 1)
    check("report mode does NOT copy", (repo / "skills/devops/a/SKILL.md").read_text(),
          "base\n")

    # 3. --apply copies a pure superset (nothing dropped).
    r = run(repo, deployed, stub, "--apply")
    check("--apply exits 0 when nothing needs review", r.returncode, 0)
    check("--apply copied the superset", (repo / "skills/devops/a/SKILL.md").read_text(),
          "base\nadded one\nadded two\n")

    # 4. A rewrite is NEVER applied silently, and its dropped lines are shown.
    repo, deployed, stub = make_trees(stranded_rewrite=("devops/b/SKILL.md",))
    r = run(repo, deployed, stub, "--apply")
    check("rewrite is not applied", (repo / "skills/devops/b/SKILL.md").read_text(),
          "keep me\nsuperseded line\n")
    check("rewrite still reports work left", r.returncode, 1)
    check("rewrite prints the dropped line", "DROP: superseded line" in r.stdout, True)

    # 5. A file with no repo counterpart is added (only under --apply).
    repo, deployed, stub = make_trees(stranded_new=("devops/c/SKILL.md",))
    r = run(repo, deployed, stub)
    check("new file is not added in report mode",
          (repo / "skills/devops/c/SKILL.md").exists(), False)
    r = run(repo, deployed, stub, "--apply")
    check("new file is added under --apply",
          (repo / "skills/devops/c/SKILL.md").read_text(), "brand new lesson\n")

    # 6. COULD-NOT-VERIFY is its own outcome, not a pass: a detector that cannot run.
    repo, deployed, _ = make_trees()
    broken = repo / "broken-drift.py"
    broken.write_text("import sys\nsys.exit(2)\n")
    r = run(repo, deployed, broken)
    check("failing detector exits 3 (not 0)", r.returncode, 3)
    check("failing detector says COULD NOT VERIFY", "COULD NOT VERIFY" in r.stdout, True)

    # 7. A detector that crashes on import is also could-not-verify.
    missing = repo / "does-not-exist.py"
    r = run(repo, deployed, missing)
    check("unrunnable detector exits 3", r.returncode, 3)

    # 8. THE REGRESSION THIS FILE NOW GUARDS: the detector renames its section header
    #    (it did: 'Stranded files:' -> 'Stranded in place:'), so the parser finds no
    #    list while the metrics row still says 2. Silence here is the bug: it must be
    #    could-not-verify, never "Nothing stranded".
    repo, deployed, _ = make_trees(stranded_superset=("devops/d/SKILL.md", "devops/e/SKILL.md"))
    renamed = repo / "renamed-drift.py"
    renamed.write_text(
        METRICS_ROW % 2
        + "print('| Files in sync | 1 |')\n"
        + "print('**Verdict: FAIL**')\n"
        + "print('Deployed-only:')\n"
        + "print('- devops/d/SKILL.md')\n"
        + "print('- devops/e/SKILL.md')\n"
        + "raise SystemExit(1)\n"
    )
    r = run(repo, deployed, renamed)
    check("renamed section header exits 3 (not 0)", r.returncode, 3)
    check("renamed section header says COULD NOT VERIFY",
          "COULD NOT VERIFY" in r.stdout, True)
    check("renamed section header names both counts", "2" in r.stdout and "0" in r.stdout, True)
    check("renamed section header does NOT claim agreement",
          "agree on content" in r.stdout, False)

    # 9. No metrics row to cross-check against -> still could-not-verify, not clean.
    repo, deployed, _ = make_trees()
    norow = repo / "norow-drift.py"
    norow.write_text("print('**Verdict: PASS**')\nraise SystemExit(0)\n")
    r = run(repo, deployed, norow)
    check("missing metrics row exits 3", r.returncode, 3)

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)}): {failures}")
        return 1
    print("RESULT: ALL PASS — report/apply split, superset-only copy, review refusal, "
          "and could-not-verify all hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
