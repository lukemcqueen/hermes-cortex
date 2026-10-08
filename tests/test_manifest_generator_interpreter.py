#!/usr/bin/env python3
"""The SKILLS-MANIFEST generator must run under an interpreter that HAS PyYAML.

WHY (2026-10-08). `gen-skills-manifest.py` parses `skills/**/SKILL.md` frontmatter
with `yaml.safe_load`. THREE call sites invoked it as a bare `python3`:

    ops/scripts/pre-commit-doc-audit.sh                  the freshness gate
    ops/scripts/manage/verify-skill-lifecycle-run.py     the lifecycle check
    gen-skills-manifest.py's own error message           the remedy it printed

On a host whose default `python3` has no PyYAML (esther: the Hermes tools python)
the generator dies with `ModuleNotFoundError: No module named 'yaml'`. The doc
audit read that as CHECK-FAILED and reported the manifest as STALE on every commit
that touched `skills/` — a FALSE accusation — while the remedy it printed was the
very command that could not run. One wrong interpreter, a dead end AND a false
positive.

The fix is one resolver (`ops/scripts/manage/gen-skills-manifest.sh`), used by
every caller, with a DISTINCT exit code for "cannot check":

    0 = fresh        1 = would change (STALE)        3 = COULD NOT VERIFY

No caller may read 3 as STALE. This test pins the class, not just the instance:
the static sweep below fails if any caller goes back to a bare `python3`.

Run: python3 tests/test_manifest_generator_interpreter.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WRAPPER_REL = "ops/scripts/manage/gen-skills-manifest.sh"
GENERATOR_REL = "ops/scripts/manage/gen-skills-manifest.py"
CALLERS = (
    "ops/scripts/pre-commit-doc-audit.sh",
    "ops/scripts/manage/verify-skill-lifecycle-run.py",
    GENERATOR_REL,
)

_FAIL = []


def _check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        _FAIL.append(name)
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def _broken_invocation(rel: str) -> bool:
    """True when `rel` still invokes the generator with a bare `python3`."""
    text = (REPO / rel).read_text(errors="ignore")
    return "python3 ops/scripts/manage/gen-skills-manifest.py" in text


def test_no_caller_invokes_the_generator_with_a_bare_python3():
    """THE CLASS GUARDRAIL: the broken invocation must not come back."""
    for rel in CALLERS:
        assert (REPO / rel).is_file(), f"{rel} is missing"
        _check(f"{rel} does not call the generator with a bare python3",
               not _broken_invocation(rel),
               "a bare python3 may lack PyYAML; use the wrapper")
    for rel in CALLERS[:2]:
        text = (REPO / rel).read_text(errors="ignore")
        _check(f"{rel} goes through the wrapper",
               "gen-skills-manifest.sh" in text,
               "every caller must use the one resolver")


def test_the_wrapper_exists_and_is_executable():
    wrapper = REPO / WRAPPER_REL
    _check("the wrapper exists", wrapper.is_file(), str(wrapper))
    _check("the wrapper is executable", os.access(wrapper, os.X_OK),
           f"mode {oct(wrapper.stat().st_mode)[-3:] if wrapper.is_file() else '?'}")
    _check("the wrapper is registered for deploy",
           WRAPPER_REL in (REPO / "ops/scripts/cortex-update.sh").read_text(errors="ignore"),
           "an unregistered wrapper is missing on a deployed-only host")


def test_the_wrapper_reports_could_not_verify_when_no_interpreter_has_pyyaml():
    """rc=3, naming what it checked — NOT a false STALE (the bug)."""
    bash = shutil.which("bash")
    assert bash, "bash not found; cannot run the wrapper"
    with tempfile.TemporaryDirectory(prefix="manifest-noyaml-") as tmp:
        # Neuter every candidate: a PYTHON that does not exist, no HERMES_VENV, a
        # HOME with no venv, and a PATH with no python at all. Deterministic on any
        # host — it needs no real PyYAML-less interpreter to exist.
        env = {"HOME": tmp, "PATH": "/nonexistent-path",
               "PYTHON": "/nonexistent/python3"}
        proc = subprocess.run([bash, str(REPO / WRAPPER_REL), "--check"],
                              capture_output=True, text=True, timeout=120, env=env)
        _check("no PyYAML interpreter -> exit 3 (COULD NOT VERIFY)", proc.returncode == 3,
               f"rc={proc.returncode} out={proc.stderr[:300]}")
        _check("the message says COULD NOT VERIFY",
               "COULD NOT VERIFY" in proc.stderr, proc.stderr[:300])
        _check("it is NOT reported as stale",
               "stale" not in proc.stderr.lower(), proc.stderr[:300])


def test_the_wrapper_resolves_an_interpreter_that_has_pyyaml():
    """The positive control — without this, test 1 could pass on a broken wrapper.

    rc must be 0 (fresh) or 1 (stale). rc=3 means this host has NO interpreter with
    PyYAML, so the manifest gate cannot run here at all — that is a real failure to
    verify, reported as one, not a silent pass.
    """
    bash = shutil.which("bash")
    assert bash, "bash not found; cannot run the wrapper"
    proc = subprocess.run([bash, str(REPO / WRAPPER_REL), "--check"],
                          capture_output=True, text=True, timeout=300, cwd=str(REPO))
    out = (proc.stdout + proc.stderr).strip()
    _check("an interpreter with PyYAML is reachable (rc in 0|1)",
           proc.returncode in (0, 1),
           "install PyYAML for a python3 on this host (python3 -m pip install pyyaml), "
           f"or set PYTHON=<interpreter with yaml>. Got rc={proc.returncode}: {out[:300]}")
    _check("the manifest is currently FRESH (rc 0, not stale)", proc.returncode == 0,
           f"rc={proc.returncode}: {out[:300]}  (regenerate + stage, or this cycle "
           "changed the header without regenerating)")


def test_the_generator_refuses_cleanly_without_pyyaml():
    """Run directly with THIS interpreter: either it has PyYAML and works, or it
    must refuse with the fix named — never a bare ModuleNotFoundError traceback."""
    proc = subprocess.run([sys.executable, str(REPO / GENERATOR_REL), "--check"],
                          capture_output=True, text=True, timeout=300)
    txt = proc.stdout + proc.stderr
    if proc.returncode in (0, 1):
        _check("this interpreter has PyYAML and the gate ran", True)
    else:
        _check("no PyYAML -> exit 3, not a crash", proc.returncode == 3,
               f"rc={proc.returncode}: {txt[:300]}")
        _check("the refusal names the fix (the wrapper)",
               "gen-skills-manifest.sh" in txt and "COULD NOT VERIFY" in txt, txt[:300])
        _check("no bare traceback", "Traceback (most recent call last)" not in txt,
               txt[:300])


if __name__ == "__main__":
    for _fn in (test_no_caller_invokes_the_generator_with_a_bare_python3,
                test_the_wrapper_exists_and_is_executable,
                test_the_wrapper_reports_could_not_verify_when_no_interpreter_has_pyyaml,
                test_the_wrapper_resolves_an_interpreter_that_has_pyyaml,
                test_the_generator_refuses_cleanly_without_pyyaml):
        _fn()
    print()
    if _FAIL:
        print(f"{len(_FAIL)} FAILED: {_FAIL}")
        raise SystemExit(1)
    print("ALL PASS — the manifest generator has one interpreter resolver, and "
          "'could not verify' is never read as 'stale'")
