#!/usr/bin/env python3
"""executor_context_builder.py — deterministic context pre-fetch (F13).

Dexter Horthy, 12-Factor Agents, factor-13 (verified 2026-08-24):
"If you already know what tools you'll want the model to call, call them
DETERMINISTICALLY and let the model do the hard part of figuring out how
to use their outputs."

For a coding agent dispatched to a worktree, the likely-needed context is
knowable BEFORE dispatch:
  - repo rules: AGENTS.md / CLAUDE.md (the governance + conventions the
    agent must follow — F2 "own your prompts" applied to client repos)
  - the slice plan (orchestrator-written task model plan)
  - recent git history (what changed recently in this repo)
  - the diff being built on (optional; budget-limited)

The executor MCP server calls build_context() and puts the result in the
execution_request envelope, so the coding agent spends ZERO tool
round-trips fetching context and starts doing the work immediately.

Budget: context is capped (F3 "own your context window") — the builder
returns the highest-value sections within the budget, newest rules first.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def _read_limited(path: Path, max_chars: int) -> str:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return ""
    return text[:max_chars]


def _git_log(repo: Path, n: int = 8, max_chars: int = 1500) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", f"-{n}", "--oneline"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return out[:max_chars]


def _git_diff_stat(repo: Path, max_chars: int = 800) -> str:
    """Diff stat of uncommitted changes (the worktree the agent inherits)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "diff", "--stat"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except (subprocess.TimeoutExpired, OSError):
        return ""
    return out[:max_chars]


def build_context(repo_root: str, task: str = "", plan: str = "",
                  max_chars: int = 6000) -> str:
    """Build the deterministic pre-fetched context envelope.

    Sections (in priority order, budget-capped):
      1. RULES — AGENTS.md then CLAUDE.md (governance + conventions)
      2. PLAN — the orchestrator-written slice plan
      3. TASK — the task statement
      4. GIT LOG — recent history (context for the codebase state)
      5. WORKTREE DIFF — uncommitted changes the agent inherits

    Returns a markdown envelope string. On missing/invalid repo, returns
    an error marker (never raises — fail-open for the executor).
    """
    repo = Path(repo_root)
    if not repo.is_dir() or not (repo / ".git").is_dir():
        return ("error: not a git repo — cannot build context envelope for "
                f"{repo_root}")

    sections: list[tuple[str, str]] = []

    # 1. Rules — AGENTS.md first (Hermes convention), CLAUDE.md second
    agents = repo / "AGENTS.md"
    if agents.is_file():
        text = _read_limited(agents, max_chars // 3)
        if text.strip():
            sections.append(("REPOSITORY RULES (AGENTS.md)", text))
    claude = repo / "CLAUDE.md"
    if claude.is_file():
        text = _read_limited(claude, max_chars // 3)
        if text.strip():
            sections.append(("AGENT GOVERNANCE (CLAUDE.md)", text))

    # 2. Plan (orchestrator-written slice plan)
    if plan and plan.strip():
        sections.append(("PLAN", plan.strip()))

    # 3. Task
    if task and task.strip():
        sections.append(("TASK", task.strip()))

    # 4. Recent git history
    git_log = _git_log(repo)
    if git_log.strip():
        sections.append(("RECENT GIT HISTORY", git_log.strip()))

    # 5. Worktree diff stat (what the agent inherits uncommitted)
    diff = _git_diff_stat(repo)
    if diff.strip():
        sections.append(("WORKTREE CHANGES (uncommitted)", diff.strip()))

    # Budget enforcement (F3): pack sections in priority order until full.
    used = 0
    parts = ["# Pre-fetched context (deterministic — do not re-fetch)\n"]
    for title, body in sections:
        block = f"\n## {title}\n{body}\n"
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining > 200:  # only add truncated block if meaningful
                parts.append(f"\n## {title}\n{body[:remaining]}\n")
            break
        parts.append(block)
        used += len(block)

    return "".join(parts)


if __name__ == "__main__":
    import sys
    repo = sys.argv[1] if len(sys.argv) > 1 else "."
    task = sys.argv[2] if len(sys.argv) > 2 else ""
    plan = sys.argv[3] if len(sys.argv) > 3 else ""
    print(build_context(repo, task=task, plan=plan))
