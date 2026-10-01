#!/usr/bin/env python3
"""session-autocheckpoint.py — the HARNESS side of the session split (S2c).

The design splits session state in two (docs/design/cortex-memory-session-mcp.md):

    store + search   → the MCP server (cortex-context-mcp.py), shared
    WHEN a checkpoint is written → THE HARNESS, this script

Why it exists: MCP is tool-call shaped and has no lifecycle. If the only way a
checkpoint gets written is the model deciding to call a tool, then the session
that most needs a checkpoint — the one that just got killed — is exactly the one
that never wrote one. So the harness calls this at a boundary (turn end, before
a long step, on stop) and the model is never the only trigger.

Call it from a harness hook, e.g.:
    pi ... --on-stop  "python3 ~/hermes-cortex/ops/scripts/session-autocheckpoint.py --notes 'stopped'"
    claude ... hooks: [Stop: session-autocheckpoint.py]

Usage:
    session-autocheckpoint.py                       # checkpoint git state + notes
    session-autocheckpoint.py --done "x" --pending "y" --decision "z"
    session-autocheckpoint.py --from-json '{"done":[...],"pending":[...]}'
    session-autocheckpoint.py --close               # final checkpoint + end session
    session-autocheckpoint.py --show                # print the current checkpoint

Contracts:
  * **Fail-open, always exit 0.** A harness hook must never break the harness
    because memory was unreachable. It reports and moves on.
  * **Duplicate suppression.** An identical consecutive checkpoint is skipped
    (state-signature, not content-hash-of-everything) — re-firing the hook on
    every turn must not shred session history or spam the store.
  * Identity is the same derivation the MCP server uses (env → git), so a
    checkpoint written here and a restore read there agree on the session.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path.home() / "hermes-cortex"
_STORE_PY = _REPO / "ops" / "services" / "mycortex-mem" / "store.py"
_STATE = Path.home() / ".hermes-cortex" / "state" / "session-autocheckpoint.json"


def _load_store():
    spec = importlib.util.spec_from_file_location("cortex_mem_store", _STORE_PY)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(*args: str) -> str:
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _identity(args) -> tuple[str, str, str]:
    """Same precedence as the MCP server — args → env → git."""
    key = (args.session_key or os.environ.get("CORTEX_SESSION_KEY", "")).strip()
    if key:
        return (key, "", "")
    harness = (args.harness or os.environ.get("CORTEX_SESSION_HARNESS")
               or os.environ.get("AGENT_NAME") or "unknown").strip()
    repo = (args.repo or os.environ.get("CORTEX_SESSION_REPO") or "").strip()
    branch = (args.branch or os.environ.get("CORTEX_SESSION_BRANCH") or "").strip()
    if not repo:
        top = _git("rev-parse", "--show-toplevel")
        repo = Path(top).name if top else ""
    if not branch:
        branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    return (harness, repo, branch)


def _signature(done, pending, blockers, decisions, notes) -> str:
    """State signature for duplicate suppression — the STATE, not the clock."""
    blob = json.dumps([sorted(done), sorted(pending), sorted(blockers),
                       sorted(decisions), notes], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _last_signature(key: str) -> str:
    try:
        data = json.loads(_STATE.read_text())
        return (data.get(key) or {}).get("sig", "")
    except (OSError, json.JSONDecodeError):
        return ""


def _remember(key: str, sig: str) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if _STATE.exists():
            try:
                data = json.loads(_STATE.read_text())
            except json.JSONDecodeError:
                data = {}
        data[key] = {"sig": sig}
        _STATE.write_text(json.dumps(data, indent=2))
    except OSError as exc:
        # Bookkeeping must never break the harness, but it must not vanish
        # either: an unwritable state file disables duplicate suppression, which
        # is exactly the kind of silent degradation worth one line of output.
        print(f"session-autocheckpoint: could not record signature ({exc}) — "
              "duplicate suppression is disabled until this is writable", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Harness-side session checkpoint (fail-open).")
    ap.add_argument("--done", action="append", default=[])
    ap.add_argument("--pending", action="append", default=[])
    ap.add_argument("--blocker", action="append", default=[])
    ap.add_argument("--decision", action="append", default=[])
    ap.add_argument("--notes", default="")
    ap.add_argument("--from-json", default="")
    ap.add_argument("--harness", default="")
    ap.add_argument("--repo", default="")
    ap.add_argument("--branch", default="")
    ap.add_argument("--session-key", default="")
    ap.add_argument("--close", action="store_true",
                    help="final checkpoint + end the session (promotes decisions to memory)")
    ap.add_argument("--show", action="store_true", help="print the current checkpoint")
    ap.add_argument("--force", action="store_true", help="write even if unchanged")
    args = ap.parse_args()

    store_mod = _load_store()
    if store_mod is None:
        print(f"session-autocheckpoint: store.py not found at {_STORE_PY} — skipping", file=sys.stderr)
        return 0                                  # fail-open

    done, pending, blockers, decisions = args.done, args.pending, args.blocker, args.decision
    notes = args.notes
    if args.from_json:
        try:
            payload = json.loads(args.from_json)
            done += list(payload.get("done") or [])
            pending += list(payload.get("pending") or [])
            blockers += list(payload.get("blockers") or [])
            decisions += list(payload.get("decisions") or [])
            notes = notes or (payload.get("notes") or "")
        except json.JSONDecodeError as e:
            print(f"session-autocheckpoint: --from-json is not valid JSON ({e}) — skipping", file=sys.stderr)
            return 0

    harness, repo, branch = _identity(args)
    store = store_mod.Store()
    if not store.available():
        print("session-autocheckpoint: cortex store unavailable — skipping (this is not an error)",
              file=sys.stderr)
        return 0

    key = store_mod.SessionStore.session_key(harness, repo, branch)
    try:
        if args.show:
            snap = store.sessions.latest(harness, repo, branch)
            print(json.dumps({"session_key": key, "checkpoint": snap}, indent=2, ensure_ascii=False))
            return 0

        sig = _signature(done, pending, blockers, decisions, notes)
        if not args.force and sig == _last_signature(key):
            print(f"session-autocheckpoint: unchanged since last checkpoint ({key}) — skipped")
            return 0

        store.sessions.checkpoint(harness, repo, branch, done=done, pending=pending,
                                  blockers=blockers, decisions=decisions, notes=notes)
        _remember(key, sig)
        print(f"session-autocheckpoint: saved ({key})")

        if args.close:
            snap = store.sessions.close(harness, repo, branch, promote_decisions=True)
            promoted = len((snap or {}).get("decisions") or [])
            print(f"session-autocheckpoint: session closed; {promoted} decision(s) promoted to memory")
    except Exception as e:  # noqa: BLE001 — a harness hook must never break the harness
        print(f"session-autocheckpoint: {type(e).__name__}: {e} — skipping (not an error)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
