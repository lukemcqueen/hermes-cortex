#!/usr/bin/env python3
"""Hermetic tests for the fail-closed checker template.

    python3 tests/test_fail_closed_checker_template.py     # exit 0 = pass

The artifact under test is a TEMPLATE (a starter skeleton shipped inside a
skill), so the properties worth pinning are the ones a copy inherits: the
exit-code contract, an INERT import, and the fail-closed branch actually
refusing when the evidence store cannot be reached.

Every branch is driven through the template's real command-line entry point
as a subprocess, with HOME redirected into a throwaway tree — so the
could-not-verify outcome is CONSTRUCTED, never merely hoped for from
whatever exists on the host. Paths derive from __file__ (the repo under
test), never from the ambient environment.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = (REPO / "skills/devops/enforcement-gate-migration"
            / "templates/fail-closed-checker.py")

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


def run(*args, home=None, cwd=None):
    """Run the template as a subprocess with a controlled HOME."""
    env = dict(os.environ)
    env["HOME"] = str(home) if home else str(Path(tempfile.mkdtemp(prefix="fcc-home-")))
    return subprocess.run([sys.executable, str(TEMPLATE), *args],
                          capture_output=True, text=True, timeout=60,
                          env=env, cwd=str(cwd or TEMPLATE.parent))


def load_by_path():
    spec = importlib.util.spec_from_file_location("fcc_template", TEMPLATE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load template module: {TEMPLATE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    check("template exists", TEMPLATE.is_file(), True)

    # 1. The exit-code contract a copy inherits — documented in the module
    #    docstring, so pin the values, not just their existence.
    m = load_by_path()
    check("EXIT_VERIFIED", m.EXIT_VERIFIED, 0)
    check("EXIT_REFUSED", m.EXIT_REFUSED, 1)
    check("EXIT_USAGE", m.EXIT_USAGE, 2)
    check("EXIT_CANNOT_VERIFY", m.EXIT_CANNOT_VERIFY, 3)
    check("every non-zero code refuses", all(c != 0 for c in
          (m.EXIT_REFUSED, m.EXIT_USAGE, m.EXIT_CANNOT_VERIFY)), True)

    # 2. Import is INERT: loading the module performs no work and prints nothing.
    with tempfile.TemporaryDirectory(prefix="fcc-inert-") as td:
        env = dict(os.environ)
        env["HOME"] = td
        proc = subprocess.run(
            [sys.executable, "-c",
             "import importlib.util,sys;"
             f"s=importlib.util.spec_from_file_location('t',{str(TEMPLATE)!r});"
             "mod=importlib.util.module_from_spec(s);s.loader.exec_module(mod)"],
            capture_output=True, text=True, timeout=60, env=env, cwd=td)
    check("import is inert (rc)", proc.returncode, 0)
    check("import is inert (silent)", proc.stdout.strip(), "")

    # 3. Usage error is its own outcome (2), distinct from a refusal.
    r = run("--question", "")
    check("empty question exits 2", r.returncode, 2)
    check("empty question names the usage fault", "--question" in r.stderr, True)

    # 4. No session => REFUSED (1), the fail-closed default, never a pass.
    r = run("--question", "reflexion-check")
    check("missing session exits 1", r.returncode, 1)
    check("missing session says REFUSED", "no active session" in r.stderr, True)

    # 5. Unreachable store => COULD NOT VERIFY (3), NOT a pass and NOT a crash.
    #    Constructed: HOME points at an empty tree, and the file-relative
    #    candidate under the repo cannot exist for the placeholder STORE_DIR.
    with tempfile.TemporaryDirectory(prefix="fcc-nostore-") as td:
        r = run("--question", "reflexion-check", "--session", "test-session",
                home=Path(td))
    check("unreachable store exits 3", r.returncode, 3)
    check("unreachable store says COULD NOT VERIFY",
          "store module not found" in r.stderr, True)
    check("unreachable store does not claim success",
          "VERIFIED" in r.stdout, False)

    # 6. Discriminating power: a copy whose fail-closed branch returns the
    #    VERIFIED code instead of COULD-NOT-VERIFY must FAIL this suite.
    with tempfile.TemporaryDirectory(prefix="fcc-mutant-") as td:
        mutant = Path(td) / "mutant.py"
        text = TEMPLATE.read_text()
        mutated = text.replace(
            'return EXIT_CANNOT_VERIFY, "store module not found - run the updater"',
            'return EXIT_VERIFIED, "store module not found - run the updater"')
        check("mutation applied to the fail-closed branch", mutated != text, True)
        mutant.write_text(mutated)
        env = dict(os.environ)
        env["HOME"] = td
        proc = subprocess.run([sys.executable, str(mutant), "--question",
                               "reflexion-check", "--session", "test-session"],
                              capture_output=True, text=True, timeout=60, env=env,
                              cwd=td)
    check("mutant returns the success code (so assertion 5 would fail)",
          proc.returncode, 0)

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)}): {failures}")
        return 1
    print("RESULT: ALL PASS — exit-code contract, inert import, usage/refused/"
          "could-not-verify branches, and the mutated copy that must not pass")
    return 0


def test_fail_closed_checker_template_contract():
    """Pytest entry point; the same assertions run standalone via __main__."""
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
