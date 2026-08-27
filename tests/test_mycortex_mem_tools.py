"""Regression test: mycortex-mem provider must advertise its 5 tools
BEFORE initialize() is called.

The gateway calls add_provider() (which reads get_tool_schemas() to build
the executor's tool routing table) BEFORE initialize_all() runs
(agent/agent_init.py). If get_tool_schemas() gates on self._pg being set,
the routing table is empty and every mem_* call fails with
"Unknown tool: mem_profile" — even though the schemas appear in the
system prompt (inject_memory_provider_tools runs after initialize, when
_pg exists). This test pins the pre-initialize contract.

Repro log: "Memory provider 'mycortex-mem' registered (0 tools)" on every
session while the prompt advertised all 5 tools.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

PLUGIN_INIT = Path(__file__).resolve().parents[1] / "plugins" / "mycortex-mem" / "__init__.py"

_spec = importlib.util.spec_from_file_location("mycortex_mem_plugin", PLUGIN_INIT)
assert _spec is not None and _spec.loader is not None, f"cannot load plugin from {PLUGIN_INIT}"
mycortex_mem = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mycortex_mem)

EXPECTED_TOOLS = {"mem_profile", "mem_search", "mem_context", "mem_reasoning", "mem_conclude"}


@pytest.fixture()
def provider():
    return mycortex_mem.MycortexMemMemoryProvider()


def test_get_tool_schemas_before_initialize_returns_five_tools(provider):
    """The ABC contract (memory_provider.py) requires schemas to be
    advertised regardless of connection state; the gateway reads them at
    add_provider() time, before initialize() has run."""
    schemas = provider.get_tool_schemas()

    assert len(schemas) == 5
    names = {s.get("name") for s in schemas}
    assert names == EXPECTED_TOOLS


def test_handle_tool_call_routes_all_advertised_tools(provider):
    """Every advertised tool must have a handler — otherwise the executor
    routes to the provider and dies on a missing handler."""
    handlers = {
        "mem_profile": provider._tool_profile,
        "mem_search": provider._tool_search,
        "mem_context": provider._tool_context,
        "mem_reasoning": provider._tool_reasoning,
        "mem_conclude": provider._tool_conclude,
    }
    for schema in provider.get_tool_schemas():
        assert schema["name"] in handlers, f"no handler for {schema['name']}"
