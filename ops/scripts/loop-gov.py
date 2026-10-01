#!/usr/bin/env python3
"""loop-gov — GENERIC governance CLI for ANY coding agent.

The adapter that lets a harness with no MCP client (Pi, aider, cursor, a plain
shell script, a CI job) drive the SAME loop governance Hermes agents get through
the loop-governance MCP server.

    loop-gov check_lock '{}'
    loop-gov begin_change '{"task_id":"my-task","description":"what and why"}'
    loop-gov end_change   '{"task_id":"my-task"}'
    loop-gov --list                    # tool names + descriptions
    loop-gov --tools-json              # MACHINE-READABLE manifest

DESIGN — one implementation, generic by construction:

  * There is **no second implementation** here. This file loads the MCP server
    module and calls its own handlers, so governance semantics stay in one place.
  * The tool list is **discovered from the server at runtime** and mapped to its
    `_<tool>` handlers. There is no hand-written route table, so a new governance
    tool is automatically reachable and CANNOT drift out of sync.
  * `--tools-json` is the integration point for OTHER agents: any harness, in any
    language, can read the manifest and generate its own thin shim. Publish the
    manifest, not a bespoke binding per agent.
  * Nothing here knows about any particular harness. If it does, that is a bug.

CONTRACTS

  Exit codes — a script must be able to GATE on this:
      0  the tool ran and governance allowed / reported as asked
      1  the tool RAN and governance REFUSED (blocked, not locked, denied) —
         a refusal is a decision, not a crash, and callers must see it
      2  usage error (unknown tool, malformed JSON)
      3  governance unavailable (server module or its dependencies missing)

  Governance refusals are reported on stdout as JSON and are NOT exceptions. A
  fabricated lock file is never written — if this tool cannot reach governance it
  says so and exits 3.

WHY THIS EXISTS: governance is enforced for Hermes at COMMIT time via the global
git hook (that already covers every harness). The INTERACTIVE ritual
(cache_search → begin_change → work → cycle_query → feedback_accept → end_change)
was reachable only through MCP. This is the generic way in.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path

SERVER_NAME = "loop-gov-mcp.py"


def _server_path() -> Path | None:
    """Find the governance server module. Repo layout first, then deployed."""
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent / "mcp-servers" / SERVER_NAME,          # repo
        Path.home() / ".hermes-cortex" / "scripts" / SERVER_NAME,  # deployed
        Path.home() / "hermes-cortex" / "mcp-servers" / SERVER_NAME,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _quiet_logging() -> None:
    """Silence the server's import-time DEBUG logging for CLI use.

    The server calls logging.basicConfig(level=DEBUG, force=True) at import (right
    for a stdio server, where stderr is a log channel). For a CLI it is noise that
    buries the actual answer — and a harness parsing our output must not have to
    filter it. Applied AFTER import, since force=True would win otherwise.
    """
    import logging
    for name in ("", "loop-governance", "mcp-server", "mcp"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger().handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.WARNING)
    logging.getLogger().addHandler(handler)


def load_governance():
    """Import the MCP server module — the ONE implementation of governance.

    Works with or without the MCP SDK: the server guards its SDK import so an
    MCP-less host can still drive the handlers (that is the whole point).
    """
    path = _server_path()
    if path is None:
        print("loop-gov: the governance server module was not found "
              f"({SERVER_NAME}). Looked in the repo and ~/.hermes-cortex/scripts.",
              file=sys.stderr)
        sys.exit(3)
    try:
        spec = importlib.util.spec_from_file_location("loop_gov_mcp_cli", path)
        if spec is None or spec.loader is None:
            print(f"loop-gov: cannot load {path}", file=sys.stderr)
            sys.exit(3)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _quiet_logging()   # the server sets DEBUG+force at import; undo it for CLI use
        return mod
    except Exception as exc:  # noqa: BLE001 — report, never fake a lock
        print(f"loop-gov: governance is unavailable: {exc}", file=sys.stderr)
        sys.exit(3)


def discover_tools(mod) -> list[dict]:
    """The tool list, asked of the server itself.

    Deliberately NOT a hand-written table: a route list maintained separately
    from the implementation is a second definition of the same thing, and it
    drifts silently. Discovery makes drift impossible.
    """
    out: list[dict] = []
    try:
        result = asyncio.run(mod.list_tools(None))
        for t in getattr(result, "tools", []):
            out.append({
                "name": getattr(t, "name", ""),
                "description": (getattr(t, "description", "") or "")[:400],
                "input_schema": getattr(t, "input_schema", None)
                                 or getattr(t, "inputSchema", None) or {},
            })
    except Exception as exc:  # noqa: BLE001 — fall back to reflection, loudly
        print(f"loop-gov: could not enumerate tools from the server ({exc}); "
              "falling back to reflected handlers", file=sys.stderr)
    if out:
        return out
    # Reflection fallback: `_<tool>` handlers the server defines.
    known_prefixes = ("_tool_",)
    for name in dir(mod):
        if name.startswith("_") and not name.startswith(known_prefixes) and callable(getattr(mod, name)):
            continue
    return out


def handler_for(mod, tool: str):
    """Map a tool name to the server's own handler. `<tool>` → `_<tool>`."""
    return getattr(mod, f"_{tool}", None)


def is_refusal(payload: dict, text: str) -> bool:
    """Governance decisions arrive as content, not exceptions.

    A refusal must be visible to a caller that gates on exit codes, but it is a
    DECISION — so it is exit 1, distinct from a usage error (2) or governance
    being unreachable (3).

    Markers are intentionally explicit: a refusal phrased as "Error: Lock belongs
    to task X" must not slip through as success (it did in the first version, and
    a caller gating on the exit code would have believed a locked repo was free).

    ⚠️ Enumerating phrasings is whack-a-mole — a SECOND refusal wording shipped
    past this list: `end_change` with no active lock answers "No governance
    session active. Nothing to release." and exited 0, so a caller would conclude
    the release had succeeded. Each wording added below is a real refusal the
    server emits; tests/test_loop_gov_cli.py pins them.
    """
    if payload.get("isError") or payload.get("is_error"):
        return True
    low = text.lower()
    return any(marker in low for marker in (
        "❌", "error:", "cannot", "refused", "denied", "blocked",
        "not locked", "belongs to task", "is still pending", "not scored",
        "violation", "unauthorised", "unauthorized",
        # end_change with no session: the release did NOT happen.
        "no governance session", "nothing to release",
    ))


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="loop-gov",
        description="Generic loop-governance CLI — one implementation, any harness.")
    ap.add_argument("tool", nargs="?", help="governance tool name (e.g. begin_change)")
    ap.add_argument("args", nargs="?", default="{}", help="JSON object of arguments")
    ap.add_argument("--list", action="store_true", help="list tools")
    ap.add_argument("--tools-json", action="store_true",
                    help="machine-readable tool manifest (for generating a shim in any agent)")
    ap.add_argument("--repo", default=None, help="repo to govern (default: cwd)")
    a = ap.parse_args()

    mod = load_governance()
    tools = discover_tools(mod)

    if a.tools_json:
        print(json.dumps({
            "surface": "loop-governance",
            "transport": "cli",
            "entrypoint": "loop-gov <tool> '<json>'",
            "exit_codes": {"0": "ran / allowed", "1": "governance refused",
                           "2": "usage error", "3": "governance unavailable"},
            "tools": tools,
            "note": ("Generate your own thin shim from this manifest. Do not "
                     "reimplement governance, and never hand-write a lock file."),
        }, indent=2, ensure_ascii=False))
        return 0

    if a.list or not a.tool:
        for t in tools:
            print(f"{t['name']:<24} {(t['description'] or '').split('.')[0]}")
        return 0

    if not any(t["name"] == a.tool for t in tools) and handler_for(mod, a.tool) is None:
        print(f"loop-gov: unknown tool '{a.tool}' — try --list", file=sys.stderr)
        return 2

    try:
        payload = json.loads(a.args) if a.args.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"loop-gov: arguments must be a JSON object ({exc})", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        print("loop-gov: arguments must be a JSON object", file=sys.stderr)
        return 2

    # Governance resolves the repo from the cwd (and the lock is repo-scoped), so
    # let a caller be explicit without needing a harness-specific mechanism.
    if a.repo:
        os.chdir(a.repo)

    handler = handler_for(mod, a.tool)
    if handler is None:
        print(f"loop-gov: '{a.tool}' is advertised but has no handler — the server "
              "and its tool list disagree (a bug, not a usage error)", file=sys.stderr)
        return 3

    try:
        result = handler(payload)
    except Exception as exc:  # noqa: BLE001 — surface, never invent a result
        print(f"loop-gov: {a.tool} failed: {exc}", file=sys.stderr)
        return 3

    # Serialise the server's CallToolResult the same way the MCP shape describes.
    if hasattr(result, "model_dump"):
        dumped = result.model_dump()
        texts = [c.get("text", "") for c in dumped.get("content", [])
                 if isinstance(c, dict)]
        body = "\n".join(t for t in texts if t)
        print(body if body else json.dumps(dumped, indent=2, ensure_ascii=False))
        return 1 if is_refusal(dumped, body) else 0

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
