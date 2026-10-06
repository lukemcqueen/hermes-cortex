"""psql must never prompt for a password — every invocation carries `-w`.

Regression for the TUI-pollution bug: without `-w`, psql prompts on /dev/tty when
`MYCORTEX_MEM_PASSWORD` is empty or the PGPASSFILE is wrong. That prompt is invisible
to the harness (it never reaches stdout/stderr) and hangs the caller instead of
failing, so the fail-open contract reads it as "memory unavailable" only after a
timeout — or never.

Both copies of the connection seam are pinned: `ops/services/mycortex-mem/store.py`
(the harness-facing store) and `plugins/mycortex-mem/__init__.py` (the Hermes plugin).
"""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
STORE = REPO / "ops" / "services" / "mycortex-mem" / "store.py"
PLUGIN = REPO / "plugins" / "mycortex-mem" / "__init__.py"


def _load(path: Path, name: str, stubs: dict[str, list[str]] | None = None):
    """Load a module by path, optionally stubbing hermes-internal imports first."""
    for module_name, attrs in (stubs or {}).items():
        module = sys.modules.get(module_name) or types.ModuleType(module_name)
        for attr in attrs:
            if not hasattr(module, attr):
                setattr(module, attr, type(attr, (), {}))
        sys.modules.setdefault(module_name, module)
        parent, _, leaf = module_name.rpartition(".")
        if parent:
            sys.modules.setdefault(parent, sys.modules[module_name])
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def store_module():
    return _load(STORE, "mycortex_mem_store_under_test")


@pytest.fixture(scope="module")
def plugin_module():
    return _load(
        PLUGIN,
        "mycortex_mem_plugin_under_test",
        {
            "agent.memory_provider": [
                "INDICATOR_GLYPH",
                "MemoryProvider",
                "RecallStatus",
                "is_trivial_prompt",
            ],
            "tools.registry": ["tool_error"],
        },
    )


def _store_macos_cmd(store_module):
    connection = store_module.PgConnection()
    connection._is_macos = True  # force the branch without an actual Darwin host
    return connection._cmd("mycortex_mem_reader")[0]


def _store_linux_cmd(store_module):
    connection = store_module.PgConnection()
    connection._is_macos = False
    return connection._cmd("mycortex_mem_reader")[0]


def _plugin_cmd(plugin_module, is_macos: bool):
    connection = plugin_module._PgConnection()
    connection.init("mycortex_mem")
    connection._is_macos = is_macos
    return connection._cmd("mycortex_mem_reader")[0]


def test_store_macos_invocation_forbids_password_prompt(store_module):
    cmd = _store_macos_cmd(store_module)

    assert cmd[0] == "psql"
    assert "-w" in cmd
    # -w belongs with the other option flags, before the trailing format flags.
    assert cmd.index("-w") < cmd.index("-t")


def test_store_linux_invocation_forbids_password_prompt(store_module):
    cmd = _store_linux_cmd(store_module)

    assert cmd[:3] == ["sg", "docker", "-c"]
    docker_exec = cmd[3]
    assert "psql" in docker_exec
    assert re.search(r"psql -U \S+ -d \S+ -w -v ON_ERROR_STOP=1", docker_exec), docker_exec


def test_plugin_macos_invocation_forbids_password_prompt(plugin_module):
    cmd = _plugin_cmd(plugin_module, is_macos=True)

    assert cmd[0] == "psql"
    assert "-w" in cmd


def test_plugin_linux_invocation_forbids_password_prompt(plugin_module):
    cmd = _plugin_cmd(plugin_module, is_macos=False)

    docker_exec = cmd[3]
    assert "psql" in docker_exec
    assert " -w " in docker_exec
