#!/usr/bin/env python3
"""Regression: the store's `sg docker` path dies under systemd NoNewPrivileges.

Context (2026-10-08): the pi backend of @Esther0001Bot reported "memory
unavailable — the cortex store is not reachable from this host" while Hermes
Esther on the same host had memory. Root cause: the serving unit
(cortex-gateway-esther0001.service) sets `NoNewPrivileges=true`, and the store's
Linux path reaches Postgres only through `sg docker -c "docker exec …"`.
sg/newgrp calls setgroups()/setgid() unconditionally and the kernel refuses under
NoNewPrivileges — even though the process already holds the docker group. The
store's available() swallows the exception and returns the bare "unavailable"
string, so a hardening setting reads as a database outage.

This drives the DETECTOR (the primitive), not live memory, so it does not flap:
it asserts sg is refused AND that the direct-docker path works under the SAME
hardening, plus the silent direction (plain sg still works) so it cannot pass for
the wrong reason. Skips when the host has no setpriv/sg/docker or no running
mycortex-postgres container.

Run: python3 tests/test_no_new_privs_sg_store.py -v      (or pytest -q)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import unittest

CONTAINER = "mycortex-postgres"
PSQL = ["psql", "-U", "mycortex_mem_reader", "-d", "mycortex",
        "-w", "-v", "ON_ERROR_STOP=1", "-t", "-A"]


def _have(*cmds: str) -> bool:
    return all(shutil.which(c) for c in cmds)


def _container_up() -> bool:
    if not _have("docker"):
        return False
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
                       capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def _sg_cmd() -> list[str]:
    return ["sg", "docker", "-c", f"docker exec -i {CONTAINER} " + " ".join(PSQL)]


def _direct_cmd() -> list[str]:
    return ["docker", "exec", "-i", CONTAINER, *PSQL]


def _run(cmd: list[str], harden: bool):
    argv = (["setpriv", "--no-new-privs", "--"] + cmd) if harden else cmd
    return subprocess.run(argv, input="SELECT 1;", capture_output=True,
                          text=True, timeout=30)


@unittest.skipUnless(_have("setpriv", "sg", "docker") and _container_up(),
                     "needs setpriv + sg + docker + a running " + CONTAINER)
class NoNewPrivsSgStoreTest(unittest.TestCase):

    def setUp(self) -> None:
        # Precondition: the caller really is in the docker group, so the DIRECT
        # path is expected to work. Without this the assertions below could pass
        # because docker itself is denied, which would prove nothing.
        r = _run(_direct_cmd(), harden=True)
        if r.returncode != 0:
            self.skipTest(f"direct docker exec unavailable: {r.stderr.strip()}")

    def test_plain_sg_still_works_silent_direction(self) -> None:
        """Control: WITHOUT hardening the sg path succeeds (the flag is the cause)."""
        r = _run(_sg_cmd(), harden=False)
        self.assertEqual(r.returncode, 0,
                         f"sg path unexpectedly failed without hardening: {r.stderr!r}")
        self.assertEqual(r.stdout.strip(), "1")

    def test_sg_indirection_is_refused_under_no_new_privs(self) -> None:
        """The detector: sg's setgid is refused -> the store sees 'unreachable'."""
        r = _run(_sg_cmd(), harden=True)
        self.assertEqual(r.returncode, 1,
                         f"expected sg to fail under NoNewPrivileges, got rc={r.returncode} "
                         f"stdout={r.stdout!r}")
        self.assertIn("setgid", r.stderr.lower(),
                      f"expected a setgid refusal, got stderr={r.stderr!r}")

    def test_direct_docker_exec_succeeds_under_no_new_privs(self) -> None:
        """The fix path: no group switch needed, so hardening does not bite."""
        r = _run(_direct_cmd(), harden=True)
        self.assertEqual(r.returncode, 0, f"stderr={r.stderr!r}")
        self.assertEqual(r.stdout.strip(), "1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
