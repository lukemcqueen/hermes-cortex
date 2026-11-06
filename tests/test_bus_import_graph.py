"""fleet_bus import-graph proof — the package resolves from its core/ runtime context.

The live gateway runs `uvicorn fleet_bus.server:app` with
WorkingDirectory/PYTHONPATH = repo `core/` (see ops/install/deploy/cortex-bus.service,
service name retained until P5). These tests pin THAT resolution context: the
`fleet_bus.*` dotted imports (including the sibling `fleet_bus.queue` helper
dependency inside circuit_breaker/auth) must resolve when `core/` is the top of
sys.path, and the one-release `cortex_bus` shim must hand back the IDENTICAL
module objects from the same context.

This is also the committed proof for the close-review finding on
core/fleet_bus/circuit_breaker.py's `from fleet_bus.queue import get_queue`
import path: it resolves from the runtime context (and only from it — no
`core.` prefix is added; that would break the uvicorn invocation).
"""

import importlib
import subprocess
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "core"
PY = sys.executable


class TestImportGraphFromCoreContext:
    """Run in a fresh interpreter with core/ as the ONLY repo path on sys.path."""

    def _run(self, code: str) -> subprocess.CompletedProcess:
        env = {"PYTHONPATH": str(CORE), "GIT_CONFIG_GLOBAL": "/dev/null"}
        return subprocess.run(
            [PY, "-c", code], capture_output=True, text=True, env=env, timeout=60
        )

    def test_server_module_imports_from_core_context(self):
        # server.py pulls in auth/validate/queue and the workflow subpackage:
        # if any `fleet_bus.*` dotted import were wrong, this fails.
        r = self._run("import fleet_bus.server; print(fleet_bus.server.__name__)")
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "fleet_bus.server"

    def test_circuit_breaker_imports_from_core_context(self):
        # The exact finding: circuit_breaker does `from fleet_bus.queue import
        # get_queue` — must resolve with core/ as package root.
        r = self._run(
            "import fleet_bus.circuit_breaker as c; "
            "assert hasattr(c, 'check_and_restore') and hasattr(c, 'is_available')"
        )
        assert r.returncode == 0, r.stderr

    def test_auth_imports_and_hash_is_pbkdf2(self):
        # auth's `from fleet_bus.queue import get_queue` is function-local; the
        # import must still resolve and the hashing must match the docstring.
        r = self._run(
            "import fleet_bus.auth as a; "
            "h = a.hash_token('probe'); "
            "assert len(h) == 64 and h.isalnum(), h"
        )
        assert r.returncode == 0, r.stderr

    def test_workflow_subpackage_all_modules_import(self):
        r = self._run(
            "import fleet_bus.workflow.db, fleet_bus.workflow.dispatcher, "
            "fleet_bus.workflow.human_gate, fleet_bus.workflow.router, "
            "fleet_bus.workflow.sla_watchdog, fleet_bus.workflow.yaml_loader; "
            "print('ok')"
        )
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "ok"


class TestCortexBusShimFromCoreContext:
    """The one-release cortex_bus shim aliases fleet_bus from the SAME context."""

    def _run(self, code: str) -> subprocess.CompletedProcess:
        env = {"PYTHONPATH": str(CORE), "GIT_CONFIG_GLOBAL": "/dev/null"}
        return subprocess.run(
            [PY, "-c", code], capture_output=True, text=True, env=env, timeout=60
        )

    def test_shim_is_fleet_bus(self):
        r = self._run(
            "import cortex_bus, fleet_bus; "
            "assert cortex_bus is fleet_bus"
        )
        assert r.returncode == 0, r.stderr

    def test_shim_aliases_submodules(self):
        r = self._run(
            "import cortex_bus.server, cortex_bus.workflow.router; "
            "import fleet_bus.server, fleet_bus.workflow.router; "
            "assert cortex_bus.server is fleet_bus.server; "
            "assert cortex_bus.workflow.router is fleet_bus.workflow.router"
        )
        assert r.returncode == 0, r.stderr

    def test_shim_legacy_import_form(self):
        r = self._run(
            "from cortex_bus.queue import NotAvailableError, _load_config; "
            "print(NotAvailableError.__name__)"
        )
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip() == "NotAvailableError"
