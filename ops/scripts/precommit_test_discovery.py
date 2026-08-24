#!/usr/bin/env python3
"""precommit_test_discovery.py — monorepo test discovery for pre-commit-score.

Extracted from pre-commit-score's inline pass-rate measurement (TitusClaude
proposal 2026-08-24, verified by Esther). Solves the monorepo blind spot:
repos with apps/<svc>/ layout (tests in apps/api/tests, config in
apps/api/pyproject.toml, runner `./run test`) never triggered measurement,
so every governance cycle scored pass-pct=100 unmeasured.

Mechanism:
1. Per-repo opt-in: <repo>/ops/scripts/test-command.sh — the repo declares
   how tests run (e.g. `./run test`). Preferred when present.
2. Fallback discovery: find test configs up to max_depth (pytest.ini,
   setup.cfg, pyproject.toml with [tool.pytest]) and measure each dir.
3. Warn when test infra exists but measurement fails — never silent 100.
4. Fail-open (100) only when NO test infra exists.

Imported by tests/; pre-commit-score sources the bash equivalents.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Config files that indicate a pytest suite lives in that directory.
# pyproject.toml only counts if it has a [tool.pytest] section.
_PYTEST_INI = "pytest.ini"
_SETUP_CFG = "setup.cfg"
_PYPROJECT = "pyproject.toml"


def _is_test_config(path: Path) -> bool:
    """True when path holds a pytest config file."""
    if not path.is_dir():
        return False
    if (path / _PYTEST_INI).is_file():
        return True
    if (path / _SETUP_CFG).is_file():
        return True
    pyproject = path / _PYPROJECT
    if pyproject.is_file():
        try:
            text = pyproject.read_text(errors="replace")
        except OSError:
            return False
        return "[tool.pytest" in text
    return False


def discover_test_dirs(repo_root: str, max_depth: int = 3) -> list[Path]:
    """Return directories containing pytest config, up to max_depth below root.

    Depth is measured as path segments below repo_root (apps/api = depth 2).
    Excludes hidden dirs (node_modules, .git, venv) and the root itself
    (root is handled by the existing pre-commit-score root-level check).
    """
    root = Path(repo_root)
    if not root.is_dir():
        return []
    found: list[Path] = []
    for candidate in root.rglob("*"):
        if not candidate.is_dir():
            continue
        rel = candidate.relative_to(root)
        # Skip hidden dirs and dependency dirs (they'd match pyproject.toml)
        if any(part.startswith(".") or part in ("node_modules", "venv", ".venv")
               for part in rel.parts):
            continue
        if len(rel.parts) > max_depth:
            continue
        if _is_test_config(candidate):
            found.append(candidate)
    # Depth-first order: shallowest first (root-most suites run first)
    return sorted(found, key=lambda p: (len(p.relative_to(root).parts), str(p)))


def resolve_test_command(repo_root: str) -> str | None:
    """Return the repo's declared test command, if present.

    <repo>/ops/scripts/test-command.sh — the repo's own test runner
    (mirrors the change-validate.sh pattern). Executed with cwd=repo_root.
    """
    tc = Path(repo_root) / "ops" / "scripts" / "test-command.sh"
    if tc.is_file() and tc.stat().st_mode & 0o111:
        return str(tc)
    return None


def parse_pass_pct(pytest_output: str) -> int | None:
    """Parse 'N passed, M failed' output into a pass percentage.

    Returns None when the output has no parseable pass/fail line (the caller
    then warns — measurement failure must not silently score 100).
    """
    m = re.search(r"(\d+)\s+passed(?:,\s*(\d+)\s+failed)?|(\d+)\s+failed", pytest_output)
    if not m:
        return None
    if m.group(1) is not None:
        passed = int(m.group(1))
        failed = int(m.group(2)) if m.group(2) else 0
    else:
        passed = 0
        failed = int(m.group(3))
    total = passed + failed
    if total == 0:
        return None
    return round((passed / total) * 100)


def classify_measurement(pass_pct: int, found_infra: bool,
                         warned: bool) -> dict:
    """Decide the final pass_pct + whether a warning was emitted.

    - found_infra=False → fail-open 100, no warning (repo has no tests).
    - found_infra=True but warned=True → 100 kept but flagged (never silent).
    - measured → the real pass_pct.
    """
    return {"pass_pct": pass_pct, "warned": warned}


def measure_passes(repo_root: str) -> dict:
    """Run the full measurement: test-command → discovery → per-dir pytest.

    Returns {"pass_pct": int, "warned": bool, "dirs_measured": [str]}.
    """
    root = Path(repo_root)
    cmd = resolve_test_command(repo_root)

    if cmd:
        try:
            out = subprocess.run(
                [cmd], cwd=root, capture_output=True, text=True, timeout=300,
            ).stdout
        except (subprocess.TimeoutExpired, OSError):
            return {"pass_pct": 100, "warned": True,
                    "dirs_measured": [f"{cmd} (failed to run)"]}
        pct = parse_pass_pct(out)
        if pct is not None:
            return {"pass_pct": pct, "warned": False,
                    "dirs_measured": [cmd]}
        return {"pass_pct": 100, "warned": True,
                "dirs_measured": [f"{cmd} (unparseable output)"]}

    dirs = discover_test_dirs(repo_root)
    if not dirs:
        return {"pass_pct": 100, "warned": False, "dirs_measured": []}

    measured: list[str] = []
    pcts: list[int] = []
    warned = False
    for d in dirs:
        try:
            out = subprocess.run(
                ["python3", "-m", "pytest", "-q", "--tb=no"],
                cwd=d, capture_output=True, text=True, timeout=300,
            ).stdout
        except (subprocess.TimeoutExpired, OSError):
            warned = True
            measured.append(f"{d.name} (failed to run)")
            continue
        pct = parse_pass_pct(out)
        if pct is None:
            warned = True
            measured.append(f"{d.name} (unparseable output)")
            continue
        pcts.append(pct)
        measured.append(f"{d.name} ({pct}%)")

    if not pcts:
        return {"pass_pct": 100, "warned": True, "dirs_measured": measured}

    return {"pass_pct": min(pcts), "warned": warned,
            "dirs_measured": measured}


def main() -> int:
    """CLI entry for pre-commit-score: print measurement as shell-parseable.

    Output format (parsed by pre-commit-score bash):
        PASS_PCT=<int>
        MEASURE_WARN=<string or empty>
        DIRS=<comma-separated dirs measured>

    Exit 0 always — fail-open (never block the commit on measurement).
    """
    import json
    import os
    repo_root = os.environ.get("REPO_ROOT") or os.getcwd()
    result = measure_passes(repo_root)
    print(f"PASS_PCT={result['pass_pct']}")
    print(f"MEASURE_WARN={'1' if result['warned'] else '0'}")
    print(f"DIRS={','.join(result['dirs_measured'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
