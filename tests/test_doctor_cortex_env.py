#!/usr/bin/env python3
"""The deploy-dir .env must be the SANCTIONED symlink, never a real file.

The 2026-10-17 env-symlink rename made `~/.hermes-cortex/.env` the sanctioned
back-compat symlink to the canonical `~/hermes-cortex/.env`, and retired
`cortex-bus.conf`. `check_cortex_env` must FAIL on a REAL file (not a symlink) at
the deploy-dir .env path — historically that path held a stray symlink to
`~/langfuse/.env` — and PASS when the symlink correctly resolves.

Driven BOTH ways against fixtures: a correct symlink must PASS, a real file must
FAIL, a missing symlink must FAIL. Never against the live host, whose env state
is real and must not be disturbed.

Run: python3 -m pytest tests/test_doctor_cortex_env.py -q
"""

import importlib
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "ops" / "scripts" / "manage") not in sys.path:
    sys.path.insert(0, str(_REPO / "ops" / "scripts" / "manage"))


class _Result:
    def __init__(self):
        self.rows = []

    def add(self, name, status, detail="", fix=""):
        self.rows.append({"name": name, "status": status, "detail": detail, "fix": fix})

    def status(self):
        return self.rows[-1]["status"]

    def detail(self):
        return self.rows[-1]["detail"]


def _checks():
    """Import the REPO's ``cortex_doctor.checks`` deterministically.

    Same isolation as test_doctor_paused_cron_reasons: a plain import_module can
    return a package cached from the DEPLOYED tree, so drop the cached package
    and put the repo's manage dir first — the test measures the source it ships.
    """
    manage = str(_REPO / "ops" / "scripts" / "manage")
    while manage in sys.path:
        sys.path.remove(manage)
    sys.path.insert(0, manage)
    for name in [n for n in sys.modules if n == "cortex_doctor" or n.startswith("cortex_doctor.")]:
        del sys.modules[name]
    return importlib.import_module("cortex_doctor.checks")


def _host(tmp_path):
    """Point HOME and CORTEX_HOME at fixtures so check_cortex_env is hermetic.

    The check derives paths from these two module constants exactly as the real
    host does: canon = HOME/"hermes-cortex"/.env, deploy = CORTEX_HOME/.env.
    """
    c = _checks()
    home = tmp_path / "home"
    deploy = home / ".hermes-cortex"          # ~/.hermes-cortex (deploy dir)
    cortex = home / "hermes-cortex"           # ~/hermes-cortex (canonical)
    deploy.mkdir(parents=True); cortex.mkdir(parents=True)
    c.HOME = home
    c.CORTEX_HOME = deploy
    return c, home, cortex, deploy


def test_sanctioned_symlink_is_a_pass(tmp_path):
    c, home, cortex, deploy = _host(tmp_path)
    canon = cortex / ".env"
    canon.write_text("CORTEX_BUS_URL=http://localhost\n")
    canon.chmod(0o600)
    (deploy / ".env").symlink_to(canon)
    res = _Result()
    c.check_cortex_env(res)
    assert res.status() == "PASS", res.rows
    assert "sanctioned symlink" in res.detail(), res.detail()
    print("  deploy-dir .env symlink -> canonical => PASS ✓")


def test_real_file_at_deploy_dot_env_is_a_fail(tmp_path):
    """The stray trap the check exists to catch: a REAL file, not a symlink."""
    c, home, cortex, deploy = _host(tmp_path)
    canon = cortex / ".env"
    canon.write_text("CORTEX_BUS_URL=http://localhost\n")
    canon.chmod(0o600)
    (deploy / ".env").write_text("SOME_OTHER_ENV=1\n")        # real file, not ours
    res = _Result()
    c.check_cortex_env(res)
    assert res.status() == "FAIL", res.rows
    assert "REAL file" in res.detail(), res.detail()
    assert "sanctioned symlink" in res.detail(), res.detail()
    print("  deploy-dir .env is a REAL file => FAIL ✓")


def test_missing_sanctioned_symlink_is_a_fail(tmp_path):
    c, home, cortex, deploy = _host(tmp_path)
    canon = cortex / ".env"
    canon.write_text("CORTEX_BUS_URL=http://localhost\n")
    canon.chmod(0o600)
    # No .env in the deploy dir at all.
    res = _Result()
    c.check_cortex_env(res)
    assert res.status() == "FAIL", res.rows
    assert "symlink is MISSING" in res.detail(), res.detail()
    print("  missing deploy-dir .env symlink => FAIL (run consolidate-env.sh) ✓")


def test_leftover_retired_cortex_bus_conf_is_flagged(tmp_path):
    c, home, cortex, deploy = _host(tmp_path)
    canon = cortex / ".env"
    canon.write_text("CORTEX_BUS_URL=http://localhost\n")
    canon.chmod(0o600)
    (deploy / ".env").symlink_to(canon)
    (deploy / "cortex-bus.conf").symlink_to(canon)   # retired name left behind
    res = _Result()
    c.check_cortex_env(res)
    assert res.status() == "FAIL", res.rows
    assert "cortex-bus.conf" in res.detail(), res.detail()
    print("  leftover retired cortex-bus.conf symlink => FAIL ✓")


def test_no_cortex_env_is_a_skip(tmp_path):
    c, home, cortex, deploy = _host(tmp_path)
    res = _Result()
    c.check_cortex_env(res)
    assert res.status() == "SKIP", res.rows
    print("  no cortex env on the host => SKIP ✓")


def test_stray_mispointed_symlink_is_a_fail(tmp_path):
    c, home, cortex, deploy = _host(tmp_path)
    canon = cortex / ".env"
    canon.write_text("CORTEX_BUS_URL=http://localhost\n")
    canon.chmod(0o600)
    other = home / "elsewhere.env"
    other.write_text("x=1\n")
    (deploy / ".env").symlink_to(other)                 # points elsewhere
    res = _Result()
    c.check_cortex_env(res)
    assert res.status() == "FAIL", res.rows
    assert "points elsewhere" in res.detail(), res.detail()
    print("  deploy-dir .env symlink pointing elsewhere => FAIL ✓")


def test_the_live_host_reports_without_crashing():
    """Smoke only — no assertion on verdict; the live host's real state decides."""
    c = _checks()
    res = _Result()
    c.check_cortex_env(res)
    assert res.status() in {"PASS", "FAIL", "SKIP"}, res.rows
    print(f"  live host -> {res.status()}: {res.detail()[:70]} ✓")


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-q"]))