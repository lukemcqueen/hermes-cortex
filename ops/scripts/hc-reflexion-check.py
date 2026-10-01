#!/usr/bin/env python3
"""hc-reflexion-check — the reflexion gate's question, answered from HC's OWN
session/memory store (`mycortex_mem.tool_events`) instead of ~/.hermes/state.db.

WHY THIS EXISTS
---------------
The pre-commit reflexion gate asked `~/.hermes/state.db` whether this session had
loaded a skill. That file is HERMES-owned: a Pi / aider / Claude Code / CI session
has no Hermes and therefore no rows, so reflexion governance was structurally
unsatisfiable for every harness that is not Hermes — while a change to how Hermes
records tool calls could silently break the gate for everyone.

HC now records its own tool events in the session/memory store it already runs.
The gate asks THAT. No fallback: a fallback keeps the incumbent load-bearing and
hides a failure of HC's own recording instead of surfacing it.

SESSION IDENTITY
----------------
The session is the repo's ACTIVE GOVERNANCE LOCK (`session_id`), which is exactly
what the gate always used. The writer records under the same key — the enforcer
plugin has the Hermes session id, and it is the lock's session_id — so the
question and the answer cannot disagree about which session they mean.

EXIT CODES (a shell gate must be able to gate on this)
------------------------------------------------------
    0  the skill IS loaded in this session            → gate passes
    1  the skill is NOT loaded in this session        → gate refuses
    2  usage error
    3  HC's store could not be reached / is broken    → gate refuses, says why

Exit 3 is FAIL-CLOSED, matching the incumbent's NO-DB behaviour: a gate that
silently passes when it cannot verify is not a gate. The message says which
component is missing so the fix is obvious rather than mysterious.
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

GOV_DIR = Path.home() / ".hermes-cortex" / "state"
DEFAULT_SKILL = "reflexion-check"

EXIT_LOADED = 0
EXIT_NOT_LOADED = 1
EXIT_USAGE = 2
EXIT_STORE_UNREACHABLE = 3


def repo_slug() -> str:
    """The governed repo's slug — matches how the governance lock derives it."""
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return os.path.basename(r.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "generic"


def active_session_id(slug: str) -> str:
    """The session the gate asks about: this repo's active governance lock.

    Precedence is the incumbent's, unchanged: (1) the current session's own lock,
    (2) the first interactive (non-cron/bg) lock, (3) the first matching lock.
    Multiple sessions can hold locks on one repo at once, so picking a cron
    session's lock here would judge an interactive commit by a cron's evidence.
    """
    current = os.environ.get("HERMES_SESSION_ID", "")
    matching: list[dict] = []
    for path in glob.glob(str(GOV_DIR / ".governance-*.json")):
        try:
            with open(path) as fh:
                d = json.load(fh)
        except (OSError, json.JSONDecodeError):
            # A lock being written atomically can read partial — skip, never fail.
            continue
        if d.get("repo_slug") == slug:
            matching.append(d)

    for d in matching:
        if current and d.get("session_id") == current:
            return d.get("session_id") or ""
    for d in matching:
        sid = d.get("session_id") or ""
        if sid and not sid.startswith(("cron_", "bg_")):
            return sid
    if matching:
        return matching[0].get("session_id") or ""
    return ""


def _import_module(path: Path):
    """Import a module from an explicit path, or None (with the reason printed)."""
    try:
        spec = importlib.util.spec_from_file_location("hc_store_reflexion", path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:  # noqa: BLE001 — reported, never faked
        print(f"hc-reflexion-check: cannot load store module {path}: {exc}", file=sys.stderr)
        return None


def load_store_module():
    """Resolve HC's store module.

    Search order: `$repo/ops/services/mycortex-mem/store.py` (repo root derived from
    this file's location), then `~/.hermes-cortex/services/mycortex-mem/store.py`.
    Returns the module, or None when neither exists.
    """
    here = Path(__file__).resolve()
    for c in (here.parents[2] / "ops" / "services" / "mycortex-mem" / "store.py",
              Path.home() / ".hermes-cortex" / "services" / "mycortex-mem" / "store.py"):
        if c.is_file():
            return _import_module(c)
    return None


def skill_loaded(skill: str, session_id: str) -> tuple[int, str]:
    """(exit_code, message) for "did this session load this skill".

    Reads HC's own store only (mycortex_mem.tool_events, keyed by session_id). There
    is no fallback source and no run-time override of the store lookup.

    Returns (0, message) when loaded, (1, message) when not loaded, (3, message) when
    the store module is missing, unreachable, or raises. Never raises.
    """
    mod = load_store_module()
    if mod is None:
        return EXIT_STORE_UNREACHABLE, (
            "HC store module not found at ~/.hermes-cortex/services/mycortex-mem/store.py "
            "— run cortex-update.sh")
    try:
        store = mod.Store()
        if not store.available():
            return EXIT_STORE_UNREACHABLE, (
                "HC session/memory store unreachable — is mycortex-postgres running? "
                "(docker ps | grep mycortex-postgres)")
        if store.sessions.loaded_skill(skill, "", session_key=session_id):
            return EXIT_LOADED, f"LOADED {skill} (session {session_id})"
    except Exception as exc:  # noqa: BLE001 — a gate must answer, not crash
        return EXIT_STORE_UNREACHABLE, f"HC store error: {exc}"
    return EXIT_NOT_LOADED, f"NOT-LOADED {skill} (session {session_id})"


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="hc-reflexion-check",
        description="Answer the reflexion gate's question from HC's own store.")
    ap.add_argument("--skill", default=DEFAULT_SKILL, help=f"skill name (default: {DEFAULT_SKILL})")
    ap.add_argument("--session", default="",
                    help="session id override (default: this repo's active governance lock)")
    ap.add_argument("--repo-slug", default="", help="repo slug override (default: git toplevel name)")
    a = ap.parse_args()

    if not a.skill.strip():
        print("hc-reflexion-check: --skill must not be empty", file=sys.stderr)
        return EXIT_USAGE

    slug = a.repo_slug or repo_slug()
    session_id = a.session.strip() or active_session_id(slug)
    if not session_id:
        print(f"NO-SESSION — no active governance lock for repo '{slug}'; "
              "call begin_change() before committing", file=sys.stderr)
        return EXIT_NOT_LOADED

    code, message = skill_loaded(a.skill.strip(), session_id)
    stream = sys.stdout if code == EXIT_LOADED else sys.stderr
    print(message, file=stream)
    return code


if __name__ == "__main__":
    sys.exit(main())
