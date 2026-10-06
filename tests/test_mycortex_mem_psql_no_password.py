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
import os
import re
import sys
import time
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
    assert re.search(r"psql -U \S+ -d \S+ -w -v ON_ERROR_STOP=1", docker_exec), docker_exec


def _psql_standin(tmp_path: Path) -> Path:
    """A `psql` stand-in that implements the documented -w contract.

    With `-w` present it refuses immediately (no password supplied) — psql's real
    behaviour. Without it, it takes the prompt path: it writes the prompt text and
    BLOCKS, which is what an invisible /dev/tty prompt does to a harness call.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    psql = bindir / "psql"
    psql.write_text(
        '#!/bin/sh\n'
        'for arg in "$@"; do\n'
        '  if [ "$arg" = "-w" ]; then\n'
        '    echo "psql: error: connection failed: no password supplied" >&2\n'
        '    exit 2\n'
        '  fi\n'
        'done\n'
        'echo "Password for user mycortex_mem_reader: " > /dev/tty 2>/dev/null\n'
        'exit 2\n')
    psql.chmod(0o755)
    return bindir


def test_store_fails_fast_and_never_prompts_without_a_password(store_module, tmp_path, monkeypatch):
    """Runtime check, not just a flag check: the store's real code path, run against a
    psql that honours -w exactly as documented, with no usable password must raise
    StoreUnavailable PROMPTLY — the fail-open contract, without an invisible prompt.

    RED without the fix: the command loses -w, psql takes the prompt path and the store
    reports a duration/timeout failure instead of the auth refusal.
    """
    bindir = _psql_standin(tmp_path)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    monkeypatch.setenv("MYCORTEX_MEM_PASSWORD", "")

    connection = store_module.PgConnection()
    connection._is_macos = True  # the branch whose argv starts with `psql`
    started = time.monotonic()
    with pytest.raises(store_module.StoreUnavailable) as excinfo:
        connection.run_sql("SELECT 1;")
    elapsed = time.monotonic() - started

    assert "no password supplied" in str(excinfo.value), str(excinfo.value)
    assert elapsed < 5, f"the store did not fail fast ({elapsed:.1f}s) — the child was allowed to prompt"
    assert connection.available(timeout=3) is False
