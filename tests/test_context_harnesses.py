#!/usr/bin/env python3
"""Tests for the context access layers and the harness registry (S2c).

The point of these tests is DRIFT, not happy paths. With several access layers
over one implementation the realistic failure is not "the tool is broken" — it is
"one layer quietly disagrees with another": a Pi extension registering a tool the
implementation does not have, or a registry entry whose generated docs are stale.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
TOOLS_PY = REPO / "ops/services/mycortex-mem/context_tools.py"
CLI_PY = REPO / "ops/scripts/cortex-context.py"
MCP_PY = REPO / "mcp-servers/cortex-context-mcp.py"
HARNESS_DIR = REPO / "ops/install/harnesses"
REGISTRY = HARNESS_DIR / "registry.yaml"
PI_EXT = HARNESS_DIR / "pi/extensions/cortex-context.ts"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tools():
    return _load(TOOLS_PY, "context_tools_under_test")


def run_cli(*args: str, env: dict | None = None):
    return subprocess.run([sys.executable, str(CLI_PY), *args],
                          capture_output=True, text=True, timeout=90, env=env)


# ── The tool surface ─────────────────────────────────────────────

def test_both_families_are_present(tools):
    names = set(tools.HANDLERS)
    assert {n for n in names if n.startswith("mem_")} >= {
        "mem_profile", "mem_search", "mem_context", "mem_conclude"}
    assert {n for n in names if n.startswith("session_")} >= {
        "session_checkpoint", "session_restore", "session_list",
        "session_search", "session_note", "session_close"}


def test_every_tool_has_metadata_and_a_handler(tools):
    """Metadata and handlers must not drift apart: a tool described but not
    implemented fails only when an agent calls it."""
    described = {t["name"] for t in tools.TOOLS}
    assert described == set(tools.HANDLERS)


def test_mcp_schema_translation(tools):
    for t in tools.TOOLS:
        schema = tools.tool_schema_for_mcp(t)
        assert schema["type"] == "object"
        assert schema["required"] == t["required"]
        for key in t["params"]:
            assert key in schema["properties"]
            if key in t["required"]:
                assert key in schema["properties"], key


def test_dispatch_never_raises_on_unknown_tool(tools):
    assert "unknown tool" in tools.dispatch("nope", {})


def test_dispatch_reports_bad_arguments_as_a_message_not_a_crash(tools):
    assert "error:" in tools.dispatch("mem_search", {})       # query required
    assert "error:" in tools.dispatch("session_note", {})     # text required


def test_identity_precedence_args_beat_env(tools, monkeypatch):
    monkeypatch.setenv("CORTEX_SESSION_HARNESS", "from-env")
    assert tools.resolve_identity({"harness": "from-arg"})[0] == "from-arg"
    # session_key short-circuits to an exact session, never a guess
    assert tools.resolve_identity({"session_key": "k:r:b"}) == ("k:r:b", "", "")


# ── The CLI access layer ─────────────────────────────────────────

def test_cli_lists_tools():
    r = run_cli("--list")
    assert r.returncode == 0
    assert "session_checkpoint" in r.stdout and "mem_context" in r.stdout


def test_cli_tools_json_is_machine_readable():
    r = run_cli("--tools-json")
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert isinstance(data, list) and data
    for t in data:
        assert {"name", "description", "params", "required"} <= set(t)


def test_cli_unknown_tool_exits_nonzero():
    r = run_cli("not_a_tool")
    assert r.returncode == 1
    assert "unknown tool" in r.stderr


def test_cli_malformed_json_exits_nonzero():
    assert run_cli("mem_context", "{not json").returncode == 1
    assert run_cli("mem_context", "[1,2,3]").returncode == 1


def test_cli_reaches_the_store_and_exits_zero():
    """Real store, real call — the point is that a HARNESS can rely on exit 0."""
    r = run_cli("mem_context", "{}",
                env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()),
                     "CORTEX_SESSION_HARNESS": "pytest"})
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert "card" in payload and "session_key" in payload


# ── Drift guards ─────────────────────────────────────────────────

def test_pi_extension_registers_only_real_tools(tools):
    """The extension must not invent a tool: it would fail at runtime, in Pi,
    far from here. Parse the .ts and check every registered name."""
    src = PI_EXT.read_text()
    registered = set(re.findall(r'tool\(\s*"([a-z_]+)"', src))
    assert registered, "no registerTool calls found — did the extension change shape?"
    unknown = registered - set(tools.HANDLERS)
    assert not unknown, f"Pi extension registers tools the implementation lacks: {unknown}"


def test_pi_extension_uses_the_shared_cli_not_its_own_logic():
    src = PI_EXT.read_text()
    assert "cortex-context.py" in src, "extension must call the shared CLI"
    # A second implementation of the semantics is the defect this guards against.
    assert "psql" not in src and "mycortex_mem" not in src


def test_pi_extension_wires_the_lifecycle_trigger():
    """The trigger half must live in the harness hooks, never in a prompt."""
    src = PI_EXT.read_text()
    assert "turn_end" in src, "no turn_end hook — nothing writes checkpoints"
    assert "before_agent_start" in src, "no restore hook — sessions cannot resume"


def test_mcp_server_shares_the_implementation():
    """The MCP server must import the shared surface, not define its own."""
    src = MCP_PY.read_text()
    assert "context_tools.py" in src
    assert "def mem_context" not in src and "def session_checkpoint" not in src


# ── The harness registry ─────────────────────────────────────────

def test_registry_is_valid_and_every_entry_is_complete():
    reg = yaml.safe_load(REGISTRY.read_text())
    assert reg["harnesses"], "registry declares no harnesses"
    names = [h["name"] for h in reg["harnesses"]]
    assert len(names) == len(set(names)), "duplicate harness name"
    for h in reg["harnesses"]:
        assert h["layer"] in {"mcp", "cli-extension", "cli-hook", "none"}
        assert h.get("why"), f"{h['name']}: needs a why (the evidence for the layer)"
        if h["layer"] != "none":
            assert h.get("surface") and h.get("install") and h.get("verify"), \
                f"{h['name']}: incomplete entry — an unverifiable instruction ships broken"


def test_generated_harness_docs_are_current():
    """CI-style parity: the derived docs must match the registry exactly."""
    r = subprocess.run([sys.executable, str(HARNESS_DIR / "generate-harnesses.py"), "--check"],
                       capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, f"stale derived files:\n{r.stdout}{r.stderr}"


def test_generated_docs_refuse_hand_editing():
    index = (HARNESS_DIR / "INDEX.md").read_text()
    assert "GENERATED" in index.splitlines()[0]
    for h in yaml.safe_load(REGISTRY.read_text())["harnesses"]:
        doc = HARNESS_DIR / h["name"] / "README.md"
        assert doc.is_file(), f"missing generated doc for {h['name']}"
        assert "GENERATED" in doc.read_text().splitlines()[0]


def test_every_harness_names_its_access_layer_in_its_doc():
    reg = yaml.safe_load(REGISTRY.read_text())
    for h in reg["harnesses"]:
        text = (HARNESS_DIR / h["name"] / "README.md").read_text()
        assert f"`{h['layer']}`" in text


def test_steadfaste_is_declared_blocked_not_silently_absent():
    """An unsupported harness must be VISIBLE with its reason, so nobody
    assumes it was simply overlooked."""
    reg = yaml.safe_load(REGISTRY.read_text())
    entries = {h["name"]: h for h in reg["harnesses"]}
    assert "steadfaste-tui" in entries
    assert entries["steadfaste-tui"]["layer"] == "none"
    assert entries["steadfaste-tui"]["why"].strip()
