#!/usr/bin/env python3
"""Tests for ops/scripts/manage/env-secret.sh — ONE variable, nothing else.

Matching the behavior documented in the env-secret.sh commit: cortex-env
precedence, the Hermes fallback, both quote styles, exit 1 on absent, exit 2 on
a bad name, exit 2 on a regex-looking name, and — the important, negative one —
"leaks NO other variable" is asserted, not assumed.

Run: python3 tests/test_env_secret.py
"""
import os
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "ops" / "scripts" / "manage" / "env-secret.sh"
_FAIL = []


def _check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        _FAIL.append(label)


def run(tmp, name, cortex_env=None, hermes_env=None):
    """Run env-secret.sh with the given HOME and (optionally) cortex env override."""
    env = {"HOME": str(tmp)}
    if cortex_env is not None:
        env["CORTEX_REPO"] = str(tmp / "cortex")
    res = subprocess.run(
        ["bash", str(SCRIPT), name],
        env=env, capture_output=True, text=True,
    )
    return res.returncode, res.stdout.strip(), res.stderr.strip()


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "cortex").mkdir()
        (tmp / ".hermes").mkdir()

        # -- setup -------------------------------------------------------------
        (tmp / "cortex" / ".env").write_text('A_SECRET="cortex-value"\nOTHER="nope"\n')
        (tmp / ".hermes" / ".env").write_text(
            'A_SECRET="hermes-value"\nUNQUOTED=plain\nSINGLE=\'sq-value\'\n'
            'OPENROUTER_API_KEY="keep-me-secret"\nSIBLING="also-secret"\n'
        )

        # -- cortex env precedence --------------------------------------------
        rc, out, _ = run(tmp, "A_SECRET", cortex_env=True, hermes_env=True)
        _check("cortex env wins over hermes", rc == 0 and out == "cortex-value", out or f"rc={rc}")

        # -- hermes fallback (no cortex env) ----------------------------------
        rc, out, _ = run(tmp, "A_SECRET", hermes_env=True)
        _check("hermes fallback when no cortex env", rc == 0 and out == "hermes-value", out or f"rc={rc}")

        # -- quote styles ------------------------------------------------------
        rc, out, _ = run(tmp, "UNQUOTED", hermes_env=True)
        _check("unquoted value", rc == 0 and out == "plain", out or f"rc={rc}")
        rc, out, _ = run(tmp, "SINGLE", hermes_env=True)
        _check("single-quoted value", rc == 0 and out == "sq-value", out or f"rc={rc}")

        # -- fail-closed on absent --------------------------------------------
        rc, _, err = run(tmp, "DEFINITELY_ABSENT_XYZ", hermes_env=True)
        _check("absent name -> exit 1", rc == 1, f"rc={rc}")

        # -- name validation ---------------------------------------------------
        rc, _, _ = run(tmp, "lowercase", hermes_env=True)
        _check("bad (lowercase) name -> exit 2", rc == 2, f"rc={rc}")
        rc, _, _ = run(tmp, "A.*", hermes_env=True)
        _check("regex-looking name -> exit 2", rc == 2, f"rc={rc}")

        # -- THE important negative: leaks NO other variable ------------------
        _check("requested value is printed", run(tmp, "OPENROUTER_API_KEY", hermes_env=True)[1] == "keep-me-secret")
        _check("sibling secret is NOT leaked",
               run(tmp, "OPENROUTER_API_KEY", hermes_env=True)[1] != "also-secret")

    if _FAIL:
        print(f"\n{len(_FAIL)} FAILED: {', '.join(_FAIL)}")
        raise SystemExit(1)
    print("\nALL PASS")


if __name__ == "__main__":
    main()
