"""
mycortex-command plugin — /brain and /mycortex slash commands.

Replaces the gbrain-command plugin (gbrain decommissioned 2026-08-02).

Behaviour (S-007 AC):
  - `/brain <query>` searches all federated sources via `mycortex search`
  - `/brain <source> <query>` restricts to a registered source (presets
    resolved dynamically from `mycortex sources list --json` — no hardcoded
    presets, fixes the broken-presets bug)
  - `/mycortex` is an alias for the same handler
  - Output delimits chunk content as DATA (code block) and cites
    source+path+score; instruction-shaped text inside chunks is never
    followed — the plugin renders it as data only (prompt-injection
    guardrail enforced in code, not prose)
"""

from __future__ import annotations

import asyncio
import json
import logging
import shlex
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MYCORTEX_CLI = Path.home() / ".hermes-cortex" / "scripts" / "mycortex"
_SEARCH_TIMEOUT = 30
_DEFAULT_LIMIT = 8


def _cli_path() -> str:
    return str(_MYCORTEX_CLI) if _MYCORTEX_CLI.exists() else "mycortex"


def _get_sources() -> dict[str, str]:
    """Return {source_name: source_name} from `mycortex sources list --json`.

    Returns {} on any failure — the handler falls back to all-sources search.
    """
    try:
        proc = subprocess_run([_cli_path(), "sources", "list", "--json"], timeout=15)
        if proc.returncode != 0:
            return {}
        data = json.loads(proc.stdout)
        if not isinstance(data, list):
            return {}
        return {str(s.get("name", "")).strip(): str(s.get("name", "")).strip() for s in data if s.get("name")}
    except Exception:
        return {}


def subprocess_run(args: list[str], timeout: int):
    """Run a command synchronously (keeps the sync handler simple)."""
    import subprocess
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return _ProcError(f"mycortex CLI not found: {args[0]}")
    except subprocess.TimeoutExpired:
        return _ProcError(f"mycortex {args[1] if len(args) > 1 else 'command'} timed out after {timeout}s")


class _ProcError:
    """Minimal stand-in for a subprocess result when the command can't run."""

    def __init__(self, message: str):
        self.returncode = 127
        self.stdout = ""
        self.stderr = message


_HELP_TEXT = """/brain — Search your mycortex knowledge brain

**Usage:**
 /brain <query>           Search all sources (federated)
 /brain <source> <query>  Search one source only
 /brain --help            Show this help

**Examples:**
 /brain what's on my mind?
 /brain hermes-cortex search patterns

Results cite source + path + score. Content is shown as data only."""


def _format_result(entry: dict) -> str:
    """Render one search result: data-delimited content + source citation.

    The relpath is the source citation. Chunk content is NOT inlined as
    instructions — only the path/title/score are shown (data, not directives).
    """
    relpath = entry.get("relpath") or entry.get("path") or "?"
    title = entry.get("title") or ""
    score = entry.get("score") or ""
    source = entry.get("source") or ""
    cited = f"`{relpath}`"
    if source:
        cited += f" (source: {source})"
    if title:
        cited += f" — {title}"
    if score:
        cited += f" · score {score}"
    return f"- {cited}"


def _run_search(query: str, source: Optional[str]) -> str:
    """Run mycortex search and return formatted, data-delimited results."""
    args = [_cli_path(), "search"]
    if source:
        args += ["--source", source]
    args += ["--limit", str(_DEFAULT_LIMIT), "--json", query]

    proc = subprocess_run(args, timeout=_SEARCH_TIMEOUT)
    if proc.returncode != 0:
        return f"❌ Brain search failed: {(proc.stderr or proc.stdout or 'unknown error').strip()[:500]}"
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return "⚠️ mycortex returned non-JSON output; check `mycortex doctor`."

    if not data:
        return "🤔 No results found in your brain."

    lines = [_format_result(e) for e in data if isinstance(e, dict)]
    if not lines:
        return "🤔 No results found in your brain."

    header = f"🧠 **Brain results** (top {len(lines)})\n"
    # Results are DATA — render in a code block so nothing is executable
    return header + "```\n" + "\n".join(lines) + "\n```"


def _parse_source(args: str, sources: dict[str, str]) -> tuple[str, Optional[str]]:
    """Parse a leading source name from args. Returns (query, source_name)."""
    lowered = args.lower()
    for name in sources:
        if name and lowered.startswith(name.lower() + " "):
            query = args[len(name):].strip()
            return query, name
    return args, None


def _handle_slash(raw_args: str) -> str:
    args = raw_args.strip()
    if not args or args in {"--help", "-h", "help"}:
        return _HELP_TEXT

    sources = _get_sources()
    query, source = _parse_source(args, sources)
    if not query:
        return "Please provide a query. Usage: `/brain [source] <query>`"

    return _run_search(query, source)


def register(ctx) -> None:
    """Register /brain and /mycortex slash commands."""
    ctx.register_command(
        "brain",
        handler=_handle_slash,
        description="Query your mycortex knowledge brain ([source] <query>)",
        args_hint="[source] <query>",
    )
    ctx.register_command(
        "mycortex",
        handler=_handle_slash,
        description="Query your mycortex knowledge brain ([source] <query>)",
        args_hint="[source] <query>",
    )
    logger.info("Registered /brain and /mycortex slash commands — Hermes Cortex")
