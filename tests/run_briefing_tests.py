#!/usr/bin/env python3
"""Dependency-free runner for tests/test_briefing_verification_1012.py.

pytest is not installed on this host and there is no pip, so the briefing
tests are written to run under plain python3 as well as pytest. A reviewer
with no test deps can still execute every assertion:

    python3 tests/test_briefing_verification_1012.py

Exit 0 = all assertions held. Non-zero = at least one failed (printed).

Why this exists: the TDD gate requires a test for the new evidence tooling,
but the gate must not depend on a package this host cannot install. This
runner makes the tests genuinely runnable here rather than nominally present.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent   # repo root
TESTS_DIR = Path(__file__).resolve().parent          # tests/
sys.path.insert(0, str(REPO_ROOT))

TEST_MOD = TESTS_DIR / "test_briefing_verification_1012.py"


def _load_tests():
    """Import the test module with a no-op 'pytest' shim so its module-level
    `import pytest` works, and so pytest.mark.parametrize is a pass-through."""
    import types

    if "pytest" not in sys.modules:
        shim = types.ModuleType("pytest")

        class _Mark:
            @staticmethod
            def parametrize(*a, **k):
                def deco(fn):
                    fn._params = (a, k)
                    return fn
                return deco

            def __getattr__(self, name):  # pragma: no cover
                def deco(fn):
                    return fn
                return deco

        shim.mark = _Mark()

        class _Skipped(Exception):
            pass

        def skip(msg=""):
            raise _Skipped(msg)

        shim.skip = skip
        shim.Skipped = _Skipped
        sys.modules["pytest"] = shim

    import importlib.util
    spec = importlib.util.spec_from_file_location("_briefing_tests", TEST_MOD)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_briefing_tests"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    if not TEST_MOD.is_file():
        print("FAIL  test module missing: %s" % TEST_MOD)
        return 1
    mod = _load_tests()

    cases = []
    for name in dir(mod):
        if not name.startswith("test_"):
            continue
        fn = getattr(mod, name)
        if not callable(fn):
            continue
        params = getattr(fn, "_params", None)
        if params:
            # self._params = (args_tuple, kwargs_dict) where args_tuple is
            # what pytest.parametrize received: ("ext", ["md","docx","pdf"]).
            # Unpack BOTH levels — unpacking only the outer pair makes `args`
            # the bare name string and mis-splits it per character.
            p_args, _p_kwargs = params
            if len(p_args) >= 2 and isinstance(p_args[0], str):
                names = [n.strip() for n in p_args[0].split(",")]
                values = p_args[1]
                if not isinstance(values, (list, tuple)):
                    values = [values]
                for val in values:
                    if len(names) == 1:
                        cases.append((name, fn, {names[0]: val}))
                    else:
                        vals = val if isinstance(val, (tuple, list)) else (val,)
                        cases.append((name, fn, dict(zip(names, vals))))
            else:
                cases.append((name, fn, {}))
        else:
            cases.append((name, fn, {}))

    passed = failed = skipped = 0
    # sort by (test name, param values) — dicts are not orderable, so key on
    # a printable string rather than the tuple itself.
    cases.sort(key=lambda c: (c[0], str(sorted(c[2].items()))))
    for name, fn, kwargs in cases:
        label = name + ("[%s]" % ",".join(map(str, kwargs.values()))
                        if kwargs else "")
        try:
            fn(**kwargs)
            print("PASS  %s" % label)
            passed += 1
        except Exception as e:  # noqa: BLE001
            if type(e).__name__ in ("Skipped", "_Skipped") or \
               "Skipped" in type(e).__name__:
                print("SKIP  %s :: %s" % (label, e))
                skipped += 1
                continue
            print("FAIL  %s :: %s: %s" % (label, type(e).__name__, e))
            traceback.print_exc()
            failed += 1

    print()
    print("ran=%d passed=%d failed=%d skipped=%d"
          % (passed + failed + skipped, passed, failed, skipped))
    print("RESULT: %s" % ("ALL TESTS PASSED" if failed == 0 else "FAILURES"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
