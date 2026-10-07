#!/usr/bin/env python3
"""The doctor must FAIL on a repo-local .hermes-cortex/ — both ways (no pytest).

    python3 tests/test_repo_local_cortex_dir_check.py     # exit 0 = pass

Drives the real check with a temp CORTEX_REPO, so it asserts the check's logic
without touching the live repo.
"""
import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "ops/scripts/manage/cortex_doctor"
failures = []


class Res:
    def __init__(self):
        self.checks = []

    def add(self, name, status, detail="", fix=""):
        self.checks.append((name, status, detail, fix))


def load_checks():
    # Import the PACKAGE normally. Loading checks.py by file path instead made the
    # package __init__ (-> cli -> checks) run around a half-initialised module and
    # raised a misleading "cannot import name check_repo" — the code was fine.
    sys.path.insert(0, str(PKG.parent))
    import cortex_doctor.checks as mod
    return mod


def status_of(res, name):
    for n, s, d, f in res.checks:
        if n == name:
            return s, d
    return None, None


def main():
    mod = load_checks()
    tmp = Path(tempfile.mkdtemp(prefix="repo-local-check-"))
    real = mod.CORTEX_REPO
    try:
        mod.CORTEX_REPO = tmp

        res = Res(); mod.check_repo_local_cortex_dir(res)
        s, d = status_of(res, "Repo-local .hermes-cortex")
        ok = (s == "PASS")
        print(f"{'PASS' if ok else 'FAIL'}  absent directory -> {s}: {d}")
        if not ok: failures.append("absent-case")

        (tmp / ".hermes-cortex").mkdir()
        res = Res(); mod.check_repo_local_cortex_dir(res)
        s, d = status_of(res, "Repo-local .hermes-cortex")
        ok = (s == "FAIL")
        print(f"{'PASS' if ok else 'FAIL'}  empty directory -> {s}: {d}")
        if not ok: failures.append("present-case")

        (tmp / ".hermes-cortex" / ".governance-lock").write_text("{}")
        res = Res(); mod.check_repo_local_cortex_dir(res)
        s, d = status_of(res, "Repo-local .hermes-cortex")
        ok = (s == "FAIL" and "governance-lock" in (d or ""))
        print(f"{'PASS' if ok else 'FAIL'}  lock marker named -> {s}: {d}")
        if not ok: failures.append("marker-case")
    finally:
        mod.CORTEX_REPO = real
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print(f"RESULT: FAIL ({failures})")
        return 1
    print("RESULT: ALL PASS - the check fails on presence and names the marker")
    return 0


if __name__ == "__main__":
    sys.exit(main())
