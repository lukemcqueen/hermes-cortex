#!/usr/bin/env python3
"""Tests for `hc harness` — the CLI driver over the harness registry.

The registry (ops/install/harnesses/registry.yaml) already declares every
coding-agent harness and its access layer. These tests pin the thing that was
missing: a single command a developer runs so wiring Pi (or any other harness)
never depends on remembering a cp + a hand-typed --tools list.

The drift this test suite exists to prevent:
  * a run line whose tool list was hand-typed and therefore rots when the
    contract grows a tool (the `--tools read,bash,edit,write,mem_context,...`
    literal in the registry is exactly that liability);
  * an MCP-layer install step that edits ANOTHER tool's config file;
  * an unknown harness name that silently does nothing.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HARNESS_CMD = REPO / "ops/scripts/hc/harness.py"
TOOLS_PY = REPO / "ops/services/mycortex-mem/context_tools.py"


def _contract_tool_names() -> set[str]:
    spec = importlib.util.spec_from_file_location("ctx_tools_for_hc_test", TOOLS_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {t["name"] for t in mod.TOOLS}


def run(*args: str, cwd: Path | None = None):
    return subprocess.run([sys.executable, str(HARNESS_CMD), *args],
                          capture_output=True, text=True, timeout=90,
                          cwd=str(cwd) if cwd else None)


def test_lists_registry_harnesses():
    r = run("list")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "pi" in out and "claude-code" in out and "codex" in out
    assert "cli-extension" in out and "mcp" in out


def test_install_pi_copies_the_extension_into_the_project(tmp_path):
    r = run("install", "pi", "--dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "extensions" / "cortex-context.ts").is_file()


def _extension_registered() -> set[str]:
    """Tools the Pi extension actually registers (same parse the drift guard uses)."""
    import re
    src = (REPO / "ops/install/harnesses/pi/extensions/cortex-context.ts").read_text()
    return set(re.findall(r'tool\(\s*"([a-z_]+)"', src))


def _run_line(stdout: str) -> str:
    line = next((ln for ln in stdout.splitlines() if ln.strip().startswith("pi -e")), None)
    assert line, f"no run line in output:\n{stdout}"
    return line


def test_install_pi_prints_a_run_line_with_the_full_contract_surface(tmp_path):
    r = run("install", "pi", "--dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    line = _run_line(r.stdout)
    for base in ("read", "bash", "edit", "write"):
        assert base in line
    for name in _contract_tool_names():
        if name in _extension_registered():
            assert name in line, f"contract tool '{name}' missing from the generated run line"


def test_the_gate_critical_tools_are_in_the_run_line(tmp_path):
    """Regression pin for the drift this command removes.

    The hand-typed literal in the old registry omitted `session_tool_event` and
    `session_loaded_skill` — the two tools the global pre-commit reflexion gate
    reads for a Pi session. A developer following that literal got a Pi session
    whose commits are REFUSED (the gate cannot see the evidence), which is
    invisible until the commit fails.
    """
    line = _run_line(run("install", "pi", "--dir", str(tmp_path)).stdout)
    for gate_tool in ("session_tool_event", "session_loaded_skill"):
        assert gate_tool in line, f"{gate_tool} unreachable from Pi"


def test_run_line_is_derived_not_the_hand_written_registry_literal(tmp_path):
    """`--tools` = base + (contract ∩ artifact registrations), computed — not typed."""
    line = _run_line(run("install", "pi", "--dir", str(tmp_path)).stdout)
    printed_tools = set(line.split("--tools", 1)[1].strip().split(","))
    expected = _contract_tool_names() & _extension_registered()
    assert printed_tools == expected | {"read", "bash", "edit", "write"}


def test_unknown_harness_fails_loudly():
    r = run("install", "not-a-real-harness")
    assert r.returncode != 0
    assert "unknown harness" in (r.stdout + r.stderr).lower()


def test_mcp_layer_install_prints_the_registration_and_writes_nothing(tmp_path):
    """An MCP harness's config belongs to that harness — never edit it for them."""
    r = run("install", "claude-code", "--dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "mcpServers" in r.stdout
    assert not list(tmp_path.iterdir()), "install must not create files for an MCP harness"


def test_verify_reports_the_registry_and_the_store():
    r = run("verify", "pi")
    assert "registry" in r.stdout.lower()
    assert "store" in r.stdout.lower()


def test_hc_entrypoint_dispatches_harness():
    """`hc harness` must work through the real CLI entrypoint, not just the module."""
    r = subprocess.run([sys.executable, str(REPO / "ops/scripts/hc/hc.py"), "harness", "list"],
                       capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, r.stderr
    assert "pi" in r.stdout and "cli-extension" in r.stdout
