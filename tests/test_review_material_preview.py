#!/usr/bin/env python3
"""The review-material preview reports what a reviewer will SEE. Run it directly:
    python3 tests/test_review_material_preview.py
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "ops" / "scripts" / "manage" / "review-material.py"


def _load():
    spec = importlib.util.spec_from_file_location("review_material_cli", CLI)
    assert spec and spec.loader, "cannot load the preview CLI"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _StubGate:
    """A gate whose bound hides most of the file — the condition the CLI must call out."""
    DIFF_CHAR_BUDGET = 200
    DIFF_CHAR_BUDGET_DOCS = 400

    @staticmethod
    def _range_is_docs_only(_diff):
        return False

    @staticmethod
    def _split_diff_sections(diff):
        return [("big.py", diff)]

    @staticmethod
    def _bound_diff(diff, budget=None):
        # a marker whose numbers match the REAL section length, as the gate emits
        return ("...[bounded: " + str(len(diff) - 100) + " of " + str(len(diff))
                + " chars omitted from its middle — stub]...")


def test_thin_file_exits_nonzero_and_says_so():
    mod = _load()
    diff = "diff --git a/big.py b/big.py\n" + "+ x\n" * 400
    rc = mod.report(diff, _StubGate)
    assert rc == 1, "a file shown with almost no body must make the preview exit 1"


def test_whole_file_exits_zero():
    mod = _load()

    class Whole(_StubGate):
        @staticmethod
        def _split_diff_sections(diff):
            return [("small.txt", diff)]

        @staticmethod
        def _bound_diff(diff, budget=None):
            return diff           # no marker: shown whole

    diff = "diff --git a/small.txt b/small.txt\n+ hello\n"
    assert mod.report(diff, Whole) == 0, "a file shown whole is not a problem"


def test_cli_self_test_runs_and_judges_every_file():
    p = subprocess.run([sys.executable, str(CLI), "--self-test"], capture_output=True, text=True)
    assert p.returncode == 0, f"--self-test should pass; rc={p.returncode}\n{p.stdout}\n{p.stderr}"
    assert "Every changed file is shown" in p.stdout


if __name__ == "__main__":
    import traceback
    fails = []
    for name, fn in sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)):
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            fails.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()
    print()
    if fails:
        print(f"RESULT: FAIL ({len(fails)}): {fails}")
        sys.exit(1)
    print("RESULT: ALL PASS")
