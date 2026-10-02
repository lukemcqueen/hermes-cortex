#!/usr/bin/env python3
"""env-value.sh — hands a harness ONE variable and nothing else.

The property that matters is the NEGATIVE one: it must not reveal any other
variable. A harness (pi, claude-code, codex) can print its own environment, so a
command like `. ~/.hermes/.env` would leak every secret in that file to the agent.
This script exists so a consumer can be given exactly one named value.

Run: python3 tests/test_env_value.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "ops/scripts/manage/env-value.sh"
_FAIL = []


def _check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        _FAIL.append(label)


def _call(env_file: str, name: str, herm: str | None = None):
    env = dict(os.environ)
    env["CORTEX_ENV_FILE"] = env_file
    env["HOME"] = herm if herm is not None else env.get("HOME", "/root")
    return subprocess.run(["bash", str(SCRIPT), name], capture_output=True, text=True,
                          timeout=30, env=env)


def test_env_value():
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        herm = t / "hermes-home"
        (herm / ".hermes").mkdir(parents=True)
        cortex = t / "cortex.env"

        cortex.write_text("WANTED=from-cortex\nOTHER_CORTEX=not-yours\n")
        (herm / ".hermes" / ".env").write_text('WANTED=from-hermes\nDEEP_SECRET=never\n')

        r = _call(str(cortex), "WANTED", str(herm))
        _check("returns the value", r.stdout == "from-cortex", repr(r.stdout))
        _check("cortex env WINS over the Hermes env", r.stdout == "from-cortex", repr(r.stdout))
        _check("exit 0 on success", r.returncode == 0, str(r.returncode))

        # the negative property: nothing else may come through
        _check("leaks NO other variable", "never" not in r.stdout and "not-yours" not in r.stdout,
               repr(r.stdout))
        _check("prints the VALUE only (no NAME=)", "WANTED=" not in r.stdout, repr(r.stdout))

        # falls through to the Hermes env when the cortex env lacks the name
        r = _call(str(cortex), "DEEP_SECRET", str(herm))
        _check("falls back to the Hermes env for a name it holds",
               r.stdout == "never" and r.returncode == 0, repr(r.stdout))

        # quote stripping, both styles
        cortex.write_text("Q1=\"quoted\"\nQ2='single'\n")
        _check("double quotes stripped", _call(str(cortex), "Q1", str(herm)).stdout == "quoted")
        _check("single quotes stripped", _call(str(cortex), "Q2", str(herm)).stdout == "single")

        # fail closed
        r = _call(str(cortex), "ABSENT_XYZ", str(herm))
        _check("absent name exits non-zero (fail closed, no empty credential)",
               r.returncode == 1 and r.stdout == "", f"rc={r.returncode} out={r.stdout!r}")
        _check("absent name explains itself on stderr", "not found" in r.stderr, r.stderr[:120])

        # a name that is not a variable name must be refused before it becomes a pattern
        r = _call(str(cortex), "bad-name", str(herm))
        _check("bad name refused with exit 2", r.returncode == 2, str(r.returncode))
        r = _call(str(cortex), ".*", str(herm))
        _check("regex-looking name refused (no wildcard leak)", r.returncode == 2, str(r.returncode))


if __name__ == "__main__":
    print("env-value.sh — one variable, nothing else")
    test_env_value()
    print()
    if _FAIL:
        print(f"{len(_FAIL)} FAILED: {', '.join(_FAIL)}")
        sys.exit(1)
    print("ALL PASS")
