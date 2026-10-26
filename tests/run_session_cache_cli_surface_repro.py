#!/usr/bin/env python3
"""Runnable regression for the session-cache-build CLI surface (2026-10-26 weekly run).

Why this exists: `session-cache-build` (the CLI the loop-governance skill tells
agents to use for the embedding cache) pointed at a stale, UNREGISTERED duplicate
at tools/loop-governance/session_cache.py. That copy did a module-level
`from hermes_models import get_model`, and hermes_models.py is not importable
from the tools/loop-governance/ directory, so EVERY invocation died before doing
any work:

    session-cache-build --help   -> ModuleNotFoundError: No module named 'hermes_models'
    session-cache-build build    -> ModuleNotFoundError: No module named 'hermes_models'

The canonical, registered builder is ops/scripts/manage/agent-session_cache.py
(deployed to ~/.hermes-cortex/scripts/agent-session_cache.py) — the same script
the agent-session-cache-build cron invokes — and it already carries the
sys.path fallback for exactly this relocation. It was simply never wired to the
CLI name.

Asserted here (each fact is a way this broke):

  1. The repo's canonical builder exposes a sys.path fallback for hermes_models
     (so a relocated copy can still import it) — the defect the orphan lacked.
  2. A copy placed in a foreign directory (temp dir, no hermes_models beside it)
     still imports and reports usage instead of dying on ModuleNotFoundError.
  3. The live CLI, if resolvable on PATH, answers `--help` with rc=0 and no
     ModuleNotFoundError — the deployed end-to-end path.

Hermetic: uses a throwaway copy in a temp dir; never touches the live cache DB.

Usage:  python3 tests/run_session_cache_cli_surface_repro.py
Exit 0 = the session cache CLI is importable from a relocated path.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CANON = REPO / "ops/scripts/manage/agent-session_cache.py"
ORPHAN = REPO / "core/governance/loop-governance" / "session_cache.py"  # must NOT exist

FAILURES: list = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def main():
    print("session-cache-build CLI surface repro")
    print(f"  canonical: {CANON}")

    check("canonical builder exists in the repo", CANON.is_file())

    src = CANON.read_text()

    # 1. The sys.path fallback must be present (this is what the orphan lacked).
    has_path_fallback = bool(
        re.search(r"sys\.path\.insert\(0,\s*str\(_cand\)\)", src)
        or re.search(r"sys\.path\.insert\(0,", src)
    )
    check(
        "canonical builder resolves hermes_models via a sys.path fallback",
        has_path_fallback,
    )
    check(
        "canonical builder guards the hermes_models import",
        "from hermes_models import get_model" in src
        and ("try:" in src and "except ImportError" in src),
    )

    # 2. Relocate a copy to a foreign dir and confirm it still starts.
    with tempfile.TemporaryDirectory() as td:
        foreign = Path(td) / "session_cache_relocated.py"
        shutil.copy(CANON, foreign)
        r = subprocess.run(
            [sys.executable, str(foreign), "--help"],
            capture_output=True, text=True, timeout=60,
            cwd=td,  # deliberately not the repo or the deployed dir
        )
        combined = (r.stdout or "") + (r.stderr or "")
        check(
            "relocated copy answers --help with rc=0",
            r.returncode == 0,
            f"rc={r.returncode}",
        )
        check(
            "relocated copy does not raise ModuleNotFoundError",
            "ModuleNotFoundError" not in combined and "No module named 'hermes_models'" not in combined,
            (r.stderr or "").strip().splitlines()[-1] if r.stderr else "",
        )

    # 3. Live deployed CLI (best-effort; skipped cleanly if not on PATH).
    cli = shutil.which("session-cache-build")
    if cli:
        r = subprocess.run([cli, "--help"], capture_output=True, text=True, timeout=60)
        combined = (r.stdout or "") + (r.stderr or "")
        check(
            f"live CLI {cli} answers --help with rc=0",
            r.returncode == 0 and "ModuleNotFoundError" not in combined,
            f"rc={r.returncode}",
        )
        target = Path(cli).resolve()
        check(
            "live CLI resolves to the canonical builder",
            target == (Path.home() / ".hermes-cortex/scripts/agent-session_cache.py").resolve()
            or "agent-session_cache.py" in target.name,
            str(target),
        )
    else:
        print("  [SKIP] session-cache-build not on PATH (not this host)")

    print()
    if FAILURES:
        print(f"FAILED ({len(FAILURES)}): " + ", ".join(FAILURES))
        return 1
    print("ALL PASS — session cache CLI is importable from a relocated path")
    return 0


if __name__ == "__main__":
    sys.exit(main())
