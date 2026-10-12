#!/usr/bin/env python3
"""Regression: the store must reach Postgres WITHOUT a group switch.

Context (2026-10-08): the pi backend of @Esther0001Bot reported "memory
unavailable — the cortex store is not reachable from this host" while Hermes
Esther on the same host had memory. Root cause: both access layers
(`ops/services/mycortex-mem/store.py` and `plugins/mycortex-mem/__init__.py`)
reached Postgres on Linux ONLY through `sg docker -c "docker exec …"`. `sg`
calls setgroups()/setgid() unconditionally, and the kernel refuses that under
`NoNewPrivileges=true` (the serving unit sets it) — even though the process
already holds the docker group. Direct `docker exec` needs no group switch, so
it works under the same hardening.

These tests drive the SEAM (the argv the store builds and how it reacts), with a
runner injected, so they are hermetic and do not flap:

  * the DIRECT form is attempted FIRST and contains no `sg`;
  * when the direct form fails, the `sg` form is still tried (it is the only path
    on a host where the user is not in the docker group) — so removing `sg`
    outright would be a regression, and this asserts the fallback survives;
  * when BOTH fail, the raised error names BOTH causes instead of a bare
    "unavailable" (the old code swallowed the reason, so a hardening setting read
    as a database outage);
  * `available()` keeps its fail-open contract (False, never raises) but records
    why, so the reason is recoverable.

One live test asserts the real thing end-to-end — the store's own connection
answering under `setpriv --no-new-privs` — and skips when the host cannot run it.

Run: pytest -q tests/test_store_access_under_no_new_privs.py
     python3 tests/test_store_access_under_no_new_privs.py -v
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STORE_PY = REPO / "ops" / "services" / "mycortex-mem" / "store.py"
CONTAINER = "mycortex-postgres"


def _load_store():
    """Import store.py by path (it is not an installed package)."""
    spec = importlib.util.spec_from_file_location("cortex_store_under_test", STORE_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class _Result:
    def __init__(self, returncode=0, stdout="1\n", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakeRunner:
    """Records argv and returns canned results per first-token."""

    def __init__(self, behaviour=None):
        self.calls: list[list[str]] = []
        self.behaviour = behaviour or {}

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        key = cmd[0] if cmd else ""
        outcome = self.behaviour.get(key, _Result())
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class AccessSeamTest(unittest.TestCase):
    """Hermetic: drives the argv + failure handling, no docker, no database."""

    def setUp(self):
        self.mod = _load_store()
        self.runner = _FakeRunner()
        self.pg = self.mod.PgConnection(runner=self.runner)
        # Force the Linux branch regardless of the host running the suite.
        if hasattr(self.pg, "_is_macos"):
            self.pg._is_macos = False

    def _commands(self, pg):
        """The argv ladder the store would use for the reader role."""
        return [argv for argv, _env in pg._attempts(self.mod._READER)]

    def test_direct_docker_exec_is_attempted_first(self):
        cmds = self._commands(self.pg)
        self.assertTrue(cmds, "the store built no command at all")
        first = cmds[0]
        self.assertEqual(first[0], "docker",
                         f"first attempt must be direct docker exec, got {first!r}")
        if self.mod._DEFAULT_CONTAINER in first:
            self.assertNotIn("sg", first,
                             "the first attempt must not go through sg (setgid/NoNewPrivileges)")

    def test_sg_fallback_is_kept_for_hosts_without_the_docker_group(self):
        """sg is the ONLY path when the user is not in the docker group."""
        cmds = self._commands(self.pg)
        sg_forms = [c for c in cmds if "sg" in c]
        self.assertTrue(sg_forms,
                        "the sg fallback was dropped — a host without the docker group "
                        "would lose memory entirely")

    def test_direct_path_success_never_runs_sg(self):
        self.runner.behaviour = {"docker": _Result(returncode=0, stdout="42\n")}
        out = self.pg.query("SELECT 42;")
        self.assertEqual(out, [["42"]])
        self.assertNotIn("sg", [c[0] for c in self.runner.calls],
                         "sg ran even though the direct form answered")

    def test_when_direct_fails_sg_is_tried(self):
        self.runner.behaviour = {
            "docker": _Result(returncode=1, stderr="permission denied"),
            "sg": _Result(returncode=0, stdout="7\n"),
        }
        out = self.pg.query("SELECT 7;")
        self.assertEqual(out, [["7"]])
        self.assertIn("sg", [c[0] for c in self.runner.calls],
                      "the sg fallback was not attempted after a direct failure")

    def test_both_paths_failing_reports_BOTH_causes(self):
        self.runner.behaviour = {
            "docker": _Result(returncode=1, stderr="setgid refused under NoNewPrivileges "
                                                   "(direct)"),
            "sg": _Result(returncode=1, stderr="setgid refused under NoNewPrivileges (sg)"),
        }
        with self.assertRaises(self.mod.StoreUnavailable) as ctx:
            self.pg.query("SELECT 1;")
        msg = str(ctx.exception)
        self.assertIn("docker", msg.lower())
        self.assertIn("sg", msg.lower()), f"the sg cause is missing from: {msg!r}"

    def test_available_is_fail_open_but_records_the_reason(self):
        self.runner.behaviour = {
            "docker": _Result(returncode=1, stderr="boom-direct"),
            "sg": _Result(returncode=1, stderr="boom-sg"),
        }
        self.assertFalse(self.pg.available(), "available() must stay fail-open (False)")
        reason = (getattr(self.pg, "last_error", "") or "")
        self.assertTrue(reason, "available() returned False without recording why")
        self.assertIn("boom", reason, f"recorded reason lacks the cause: {reason!r}")


@unittest.skipUnless(shutil.which("setpriv") and shutil.which("docker"),
                     "needs setpriv + docker")
class LiveNoNewPrivsTest(unittest.TestCase):
    """Live: the store's OWN connection, under the hardening, must answer."""

    def setUp(self):
        r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
                           capture_output=True, text=True)
        if r.returncode != 0 or r.stdout.strip() != "true":
            self.skipTest(f"{CONTAINER} is not running")

    def test_store_connects_under_no_new_privs(self):
        code = (
            "import importlib.util,sys;"
            f"spec=importlib.util.spec_from_file_location('s',{str(STORE_PY)!r});"
            "m=importlib.util.module_from_spec(spec);sys.modules['s']=m;"
            "spec.loader.exec_module(m);"
            "print(m.PgConnection().scalar('SELECT 1;'))"
        )
        r = subprocess.run(["setpriv", "--no-new-privs", "--",
                            sys.executable, "-c", code],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0,
                         f"store unreachable under NoNewPrivileges: {r.stderr.strip()!r}")
        self.assertEqual(r.stdout.strip(), "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
