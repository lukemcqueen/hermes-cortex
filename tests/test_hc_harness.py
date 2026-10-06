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


def _harness_module():
    """The CLI's own module — the derivation is unit-testable without spawning it."""
    spec = importlib.util.spec_from_file_location("hc_harness_mod", HARNESS_CMD)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def test_install_pi_prints_a_run_line_without_an_allowlist(tmp_path):
    """Pi reads the memory/session contract over MCP, so its run line carries no
    `--tools` allowlist: the surface cannot be silently narrowed by a list that ages."""
    r = run("install", "pi", "--dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    line = _run_line(r.stdout)
    assert "--tools" not in line, f"Pi run line still carries an allowlist: {line}"
    assert "over MCP" in r.stdout, "the install output must name where the tools come from"


def test_the_gate_tools_are_reachable_from_a_pi_session(tmp_path):
    """Regression pin for the drift this command removes, both halves.

    The hand-typed literal in the old registry omitted `session_tool_event` and
    `session_loaded_skill` — the two tools the global pre-commit reflexion gate reads
    for a Pi session — so a developer following it got commits REFUSED, invisible
    until the commit failed. Two assertions now, because either alone can pass while
    the gate is unreachable:

    1. the run line carries NO `--tools` allowlist (nothing can be excluded), and
    2. the tools the gate reads are actually SERVED by the MCP surface Pi is pointed
       at — a regression that dropped them from the contract while still printing
       "over MCP" fails here.
    """
    out = run("install", "pi", "--dir", str(tmp_path)).stdout
    line = _run_line(out)
    assert "--tools" not in line, f"an allowlist could exclude a gate tool: {line}"
    assert "over MCP" in out, "the install output must name where the surface comes from"

    contract = _contract_tool_names()
    for gate_tool in ("session_tool_event", "session_loaded_skill"):
        assert gate_tool in contract, (
            f"{gate_tool} is not in the MCP contract — the reflexion gate cannot read "
            "a Pi session's evidence")
    assert "cortex-context-mcp.py" in (
        (REPO / "ops/install/harnesses/registry.yaml").read_text(encoding="utf-8")), \
        "the registry must name the MCP server that serves those tools"


def test_run_line_is_derived_not_the_hand_written_registry_literal(tmp_path, monkeypatch):
    """`--tools` = base + (contract ∩ artifact registrations), computed — not typed.

    No harness declares `cli-extension` today (Pi moved to MCP), so the derivation is
    driven on a synthetic entry: an artifact registering a SUBSET must yield exactly
    base + that subset and return the REST of the contract as the unexposed gap — the
    return value that makes a missing gate tool visible instead of silent.
    """
    mod = _harness_module()
    contract = mod.contract_tool_names()
    assert contract, "contract tools unavailable — fix the probe, not the test"
    subset = contract[:2]

    regdir = tmp_path / "harnesses"
    (regdir / "fake").mkdir(parents=True)
    shim = regdir / "fake" / "shim.ts"
    shim.write_text("\n".join(f'tool("{n}", {{}});' for n in subset) + "\n", encoding="utf-8")
    monkeypatch.setattr(mod, "registry_dir", lambda: regdir)
    entry = {"name": "fake", "layer": "cli-extension", "artifact": "shim.ts",
             "tools_base": ["read", "bash", "edit", "write"]}

    run_line, unexposed = mod.derived_run_line(entry)
    printed = set(run_line.split("--tools", 1)[1].strip().split(","))
    assert printed == set(subset) | {"read", "bash", "edit", "write"}
    assert unexposed == [n for n in contract if n not in subset]

    # An artifact registering NOTHING is unverifiable: expose the base only and report
    # the whole contract as the gap — never silently list tools that may not exist.
    shim.write_text("// no tool() registrations\n", encoding="utf-8")
    run_line2, gap = mod.derived_run_line(entry)
    assert run_line2.endswith("--tools read,bash,edit,write")
    assert gap == contract


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
