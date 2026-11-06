#!/usr/bin/env python3
"""Session repo identity for TASK QUERIES — one resolver, one place to fix.

WHY THIS EXISTS (cycle 12593, reported by Titus): the MCP task tools returned
EVERY repo's tasks for an agent, so an agent working in repo A picked up and
reported work belonging to repo B. The tools now scope their queries to the
caller's OWN repo, resolved here.

OPERATOR RULE (2026-10-14): "If the repo is unknown or the current dir is
unknown then NO tasks should be returned." An unresolved repo therefore yields
ZERO rows — never an all-repos result. `FLEET_ALL` is the only way to ask for
the fleet-wide view, and it must be asked for EXPLICITLY.

Resolution ladder (first hit wins) — mirrors the fleet's existing session-repo
identity (`mcp-servers/loop-gov-mcp.py::_session_repo_path`, documented in
docs/troubleshooting.md) so task scoping and lock identity agree:

  1. explicit `repo` argument          -> the caller's own declaration
  2. injected `repo_path`/`repo_slug`  -> the governance-enforcer observed it for
                                          THIS session (Hermes; injected into
                                          mcp__tasks__* calls like it already is
                                          for mcp__loop_governance__*)
  3. `CORTEX_SESSION_REPO` env         -> the documented per-harness lever
                                          (absolute path, or a bare repo name)
  4. the process's own cwd git repo    -> a harness that spawns one MCP child per
                                          session inside the session's project
                                          (pi, Claude Code, Codex)
  5. otherwise -> None -> ZERO tasks

There is deliberately NO host-canonical fallback: a caller whose repo cannot be
established must not be shown another repo's work (that is the reported bug,
one level up). A caller that genuinely wants every repo says `ALL`.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Same identifier allowlist the task store enforces on its `repo` column.
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

SESSION_REPO_ENV = "CORTEX_SESSION_REPO"

#: Explicit, documented opt-in for a fleet-wide (unscoped) query. Never a default.
FLEET_ALL = "ALL"


@dataclass(frozen=True)
class ResolvedRepo:
    """Where a task query is scoped to. `fleet` means the caller asked for ALL."""

    slug: Optional[str]
    source: str          # explicit | injected | env | cwd | explicit-all
    fleet: bool = False
    path: Optional[Path] = None

    def describe(self) -> str:
        if self.fleet:
            return "ALL repos (explicit fleet-wide request)"
        return f"'{self.slug}' (from {self.source})"


def _is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def _cwd_git_repo() -> Optional[Path]:
    """The git repo this process sits in, or None. A harness's per-session MCP
    child is spawned inside the session's project, so its cwd IS the repo."""
    try:
        out = subprocess.check_output(  # noqa: S603,S404 — fixed argv
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL, timeout=3, text=True,
        ).strip()
    except Exception:  # noqa: BLE001 — git absent, no repo, cwd deleted
        return None
    if not out:
        return None
    candidate = Path(out)
    return candidate if _is_git_repo(candidate) else None


def resolve_query_repo(explicit: Optional[str] = None,
                       repo_path: Optional[str] = None,
                       repo_slug: Optional[str] = None) -> Optional[ResolvedRepo]:
    """Resolve the repo a task QUERY belongs to. None => unknown => no tasks."""
    raw = (explicit or "").strip()
    if raw:
        if raw.upper() == FLEET_ALL:
            return ResolvedRepo(slug=None, source="explicit-all", fleet=True)
        if NAME_RE.match(raw):
            return ResolvedRepo(slug=raw, source="explicit")
        # Not a legal repo label: fail CLOSED rather than fall through to a
        # broader scope. Callers that validate first (task-db --repo) error out
        # with a usable message before reaching here.
        return None

    path = (repo_path or "").strip()
    if path:
        candidate = Path(path).expanduser()
        if _is_git_repo(candidate):
            return ResolvedRepo(slug=candidate.name, source="injected", path=candidate)

    slug = (repo_slug or "").strip()
    if slug and NAME_RE.match(slug):
        return ResolvedRepo(slug=slug, source="injected")

    declared = (os.environ.get(SESSION_REPO_ENV) or "").strip()
    if declared:
        if declared.startswith(("/", "~")):
            candidate = Path(declared).expanduser()
            if _is_git_repo(candidate):
                return ResolvedRepo(slug=candidate.name, source="env", path=candidate)
        elif NAME_RE.match(declared):
            # A NAME is a declaration, not a guess (docs/runbooks/context-integration.md).
            return ResolvedRepo(slug=declared, source="env")

    cwd_repo = _cwd_git_repo()
    if cwd_repo is not None:
        return ResolvedRepo(slug=cwd_repo.name, source="cwd", path=cwd_repo)

    return None


def unknown_repo_message(tool: str) -> str:
    """The one message every scoped query emits when it cannot scope itself."""
    return (f"{tool}: repo unknown — none of: an explicit repo argument, an injected "
            f"session repo, {SESSION_REPO_ENV}, or a git repo at the current "
            f"directory. Returning NO tasks rather than every repo's tasks "
            f"(operator rule 2026-10-14).")
