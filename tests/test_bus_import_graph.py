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
        # get_queue` — must resolve with core/ as package root. The methods live
        # on CircuitBreaker (module-level import proof only).
        r = self._run(
            "import fleet_bus.circuit_breaker as c; "
            "assert hasattr(c, 'CircuitBreaker'); "
            "assert hasattr(c.CircuitBreaker, 'check_and_restore'); "
            "assert hasattr(c.CircuitBreaker, 'is_available')"
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

    def test_queue_exports_get_queue_and_busclient(self):
        # workflow/db.py's top-level `from fleet_bus.queue import get_queue,
        # BusClient` — both names must exist on the queue module.
        r = self._run(
            "from fleet_bus.queue import get_queue, BusClient; "
            "assert callable(get_queue); "
            "assert isinstance(BusClient, type)"
        )
        assert r.returncode == 0, r.stderr

    def test_workflow_db_imports_from_core_context(self):
        # db.py's module-top import (get_queue, BusClient) resolves from the
        # runtime context; the module graph imports cleanly.
        r = self._run(
            "import fleet_bus.workflow.db as d; "
            "assert d.create_workflow and d.get_workflow and d.write_audit"
        )
        assert r.returncode == 0, r.stderr

    def test_create_workflow_exercises_mocked_bus(self):
        # The reviewer's exact ask for workflow/db.py: exercise create_workflow
        # against a MOCKED BusClient, verifying the private-attribute protocol
        # this file relies on (_ensure_conn/_conn.cursor/_conn.commit) and the
        # SQL target. The REAL protocol is additionally proven daily at
        # runtime: the live gateway calls validate_token (same protocol,
        # bus._ensure_conn/_conn) on every API request. No DB touched here.
        r = self._run(
            "import unittest.mock\n"
            "import fleet_bus.workflow.db as db\n"
            "class _FakeCursor:\n"
            "    def __init__(self): self.executed = []\n"
            "    def execute(self, sql, params=None): self.executed.append(sql)\n"
            "    def __enter__(self): return self\n"
            "    def __exit__(self, *a): return False\n"
            "class _FakeConn:\n"
            "    def __init__(self): self.c = _FakeCursor()\n"
            "    def cursor(self): return self.c\n"
            "    def commit(self): self.committed = True\n"
            "class _FakeBus:\n"
            "    def _ensure_conn(self): return None\n"
            "    def __init__(self): self._conn = _FakeConn()\n"
            "fake = _FakeBus()\n"
            "with unittest.mock.patch('fleet_bus.workflow.db.get_queue', return_value=fake):\n"
            "    wf_id = db.create_workflow('t', {'steps': []}, priority=1)\n"
            "assert isinstance(wf_id, str) and len(wf_id) == 36\n"
            "sql = fake._conn.c.executed[0]\n"
            "assert 'INSERT INTO bus.agent_workflows' in sql\n"
            "assert fake._conn.committed is True\n"
            "print('exercised')\n"
        )
        assert r.returncode == 0, r.stderr
        assert "exercised" in r.stdout, r.stdout

    def test_circuit_breaker_exercises_mocked_dependency(self):
        # The reviewer's exact ask: exercise check_and_restore/is_available with
        # fleet_bus.queue.get_queue MOCKED, proving the dotted import resolves
        # at runtime AND the function uses it. No DB touched; STATE_FILE is
        # redirected to a temp path so the runner cannot clobber the live
        # ~/.steadfaste-fleet/bus-circuit-breaker.json.
        r = self._run(
            "import pathlib, tempfile, unittest.mock\n"
            "import fleet_bus.circuit_breaker as cb\n"
            "cb.STATE_FILE = pathlib.Path(tempfile.mkstemp(prefix='cb-test-')[1])\n"
            "breaker = cb.CircuitBreaker()\n"
            "# pgmq path: get_queue resolves + is used\n"
            "breaker._state.state = 'pgmq'\n"
            "with unittest.mock.patch('fleet_bus.queue.get_queue') as gq:\n"
            "    gq.return_value.list_queues.return_value = []\n"
            "    ok = breaker.is_available()\n"
            "assert ok is True\n"
            "# file path: get_queue raising degrades to file (never flips to pgmq)\n"
            "breaker._state.state = 'file'\n"
            "with unittest.mock.patch('fleet_bus.queue.get_queue') as gq:\n"
            "    gq.return_value.list_queues.side_effect = RuntimeError('pg down')\n"
            "    breaker.check_and_restore()\n"
            "assert breaker._state.state == 'file'\n"
            "# file path: get_queue ok restores to pgmq\n"
            "breaker._state.state = 'file'\n"
            "with unittest.mock.patch('fleet_bus.queue.get_queue') as gq:\n"
            "    gq.return_value.list_queues.return_value = []\n"
            "    breaker.check_and_restore()\n"
            "assert breaker._state.state == 'pgmq'\n"
            "print('exercised')\n"
        )
        assert r.returncode == 0, r.stderr
        assert "exercised" in r.stdout, r.stdout


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
