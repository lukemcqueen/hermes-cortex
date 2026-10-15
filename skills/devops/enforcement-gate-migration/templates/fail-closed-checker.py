#!/usr/bin/env python3
"""Fail-closed checker skeleton — for a gate that must answer a yes/no question
against an evidence store it owns.

Copy, then fill in the store lookup and the query. The shape worth reusing is here:
an explicit exit-code contract, a fail-closed unreachable branch, and no run-time
override of where the evidence comes from.

EXIT CODES — ALL non-zero refuse; the calling gate must be able to gate on this:
    0  verified (the answer is yes)
    1  refused (the answer is no)
    2  usage error
    3  cannot verify (store module missing, store unreachable, or store raised)
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_QUESTION = "reflexion-check"
STORE_DIR = "STORE_DIR"   # e.g. mycortex-mem

EXIT_VERIFIED = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2
EXIT_CANNOT_VERIFY = 3


def repo_slug() -> str:
    """Repo name, matching how the governance lock derives its slug."""
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return os.path.basename(r.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "generic"


def _import_module(path: Path):
    """Import from an explicit path, or None with the reason printed."""
    try:
        spec = importlib.util.spec_from_file_location("gate_store", path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:  # noqa: BLE001 - reported, never faked
        print(f"checker: cannot load store module {path}: {exc}", file=sys.stderr)
        return None


def load_store_module():
    """Resolve the store module.

    Search order: a path derived from THIS file's location, then a deployed
    fallback. Count parents[] from the FILE: for <repo>/ops/scripts/x.py,
    parents[0]=scripts, [1]=ops, [2]=repo. An off-by-one yields ops/ops/..., which
    never matches and is invisible wherever the second candidate exists — the repo
    copy becomes dead code that only fails on a never-deployed host.

    Deliberately NOT overridable from the environment: whoever can set env could
    point the gate at a stub that answers yes for anything.
    """
    here = Path(__file__).resolve()
    for candidate in (here.parents[2] / "ops" / "services" / STORE_DIR / "store.py",
                      Path.home() / ".hermes-cortex" / "services" / STORE_DIR / "store.py"):
        if candidate.is_file():
            return _import_module(candidate)
    return None


def answer(question: str, session_id: str) -> tuple[int, str]:
    """(exit_code, message). Never raises: the caller only reads the code."""
    mod = load_store_module()
    if mod is None:
        return EXIT_CANNOT_VERIFY, "store module not found - run the updater"
    try:
        store = mod.Store()
        if not store.available():
            return EXIT_CANNOT_VERIFY, "store unreachable - is the database up?"
        if store.sessions.loaded_skill(question, "", session_key=session_id):
            return EXIT_VERIFIED, f"VERIFIED {question} (session {session_id})"
    except Exception as exc:  # noqa: BLE001 - a gate must answer, not crash
        return EXIT_CANNOT_VERIFY, f"store error: {exc}"
    return EXIT_REFUSED, f"REFUSED {question} (session {session_id})"


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="fail-closed-checker",
        description="Answer a gate's yes/no question from HC-owned evidence.")
    ap.add_argument("--question", default=DEFAULT_QUESTION)
    ap.add_argument("--session", default="",
                    help="session id (default: this repo's active governance lock)")
    ap.add_argument("--repo-slug", default="")
    a = ap.parse_args()

    if not a.question.strip():
        print("checker: --question must not be empty", file=sys.stderr)
        return EXIT_USAGE

    slug = a.repo_slug or repo_slug()
    session_id = a.session.strip()
    if not session_id:
        # Fill in: read this repo's active governance lock and take its session_id.
        # The writer records under the same key, so question and answer agree.
        print(f"checker: no active session for repo {slug}", file=sys.stderr)
        return EXIT_REFUSED

    code, message = answer(a.question.strip(), session_id)
    print(message, file=sys.stdout if code == EXIT_VERIFIED else sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
