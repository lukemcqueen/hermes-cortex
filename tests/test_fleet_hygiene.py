#!/usr/bin/env python3
"""Tests for fleet-hygiene — unified fleet hygiene CLI (merged 2026-08-27).

Covers:
  - langfuse: auth resolution, traces/keys check, exit-code conventions.
  - shared reporting: PASS/FAIL/UNVERIFIABLE + exit codes 0/1/2.

Run: python3 -m pytest tests/test_fleet_hygiene.py -v
     (or: python3 tests/test_fleet_hygiene.py)
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

_MANAGE = Path(__file__).resolve().parent.parent / "ops" / "scripts" / "manage"
_spec = importlib.util.spec_from_file_location("fleet_hygiene", _MANAGE / "fleet-hygiene.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

class _Args:
    def __init__(self, json_out=False):
        self.json = json_out


# ────────────────────────────────────────────────────────────────
# langfuse subcommand
# ────────────────────────────────────────────────────────────────
def test_langfuse_auth_missing_env_returns_none():
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / ".hermes").mkdir()
        env = Path(td) / ".hermes" / ".env"
        env.write_text("SOMETHING_ELSE=1\n")
        _mod.HOME = Path(td)
        assert _mod._langfuse_auth() is None


def test_langfuse_auth_reads_keys():
    import base64
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / ".hermes").mkdir()
        env = Path(td) / ".hermes" / ".env"
        env.write_text("HERMES_LANGFUSE_PUBLIC_KEY=pubkey123\n"
                       "HERMES_LANGFUSE_SECRET_KEY=secret456\n")
        _mod.HOME = Path(td)
        auth = _mod._langfuse_auth()
        expected = base64.b64encode(b"pubkey123:secret456").decode()
        assert auth == expected


def test_check_langfuse_unverifiable_without_auth():
    with tempfile.TemporaryDirectory() as td:
        _mod.HOME = Path(td)
        checks = _mod.check_langfuse()
        assert len(checks) == 2
        assert checks[0][0] == "langfuse_auth"
        assert all(ok is None for _, ok, _ in checks)


def test_check_langfuse_traces_ok_auth_ok(monkeypatch):
    def fake_api(path, auth):
        assert "fromTimestamp" in path  # v3 API contract
        return {"data": [{"name": "job-x", "timestamp": "2026-08-27T00:00:00Z", "tags": []}]}
    monkeypatch.setattr(_mod, "_langfuse_api", fake_api)
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / ".hermes").mkdir()
        env = Path(td) / ".hermes" / ".env"
        env.write_text("HERMES_LANGFUSE_PUBLIC_KEY=pk\nHERMES_LANGFUSE_SECRET_KEY=sk\n")
        _mod.HOME = Path(td)
        checks = _mod.check_langfuse()
        assert len(checks) == 2
        assert all(ok is True for _, ok, _ in checks)


def test_check_langfuse_api_down():
    def fake_api(path, auth):
        return {"error": "ConnectionRefused", "body": "refused"}
    _mod._langfuse_api = fake_api
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / ".hermes").mkdir()
        env = Path(td) / ".hermes" / ".env"
        env.write_text("HERMES_LANGFUSE_PUBLIC_KEY=pk\nHERMES_LANGFUSE_SECRET_KEY=sk\n")
        _mod.HOME = Path(td)
        checks = _mod.check_langfuse()
        assert checks[0][0] == "traces"
        assert checks[1][0] == "langfuse_auth"
        assert all(ok is False for _, ok, _ in checks)


def test_langfuse_exit_code_fail():
    _mod._langfuse_api = lambda path, auth: {"error": "down", "body": "down"}
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / ".hermes").mkdir()
        env = Path(td) / ".hermes" / ".env"
        env.write_text("HERMES_LANGFUSE_PUBLIC_KEY=pk\nHERMES_LANGFUSE_SECRET_KEY=sk\n")
        _mod.HOME = Path(td)
        rc = _mod.cmd_langfuse(_Args())
        assert rc == 1


# ────────────────────────────────────────────────────────────────
# shared reporting
# ────────────────────────────────────────────────────────────────
def test_report_pass_json(capsys):
    rc = _mod._report(_Args(json_out=True), "langfuse", [
        ("a", True, "ok-a"), ("b", True, "ok-b"),
    ])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["overall"] == "PASS"
    assert out["subcommand"] == "langfuse"
    assert len(out["checks"]) == 2


def test_report_fail_text(capsys):
    rc = _mod._report(_Args(), "langfuse", [
        ("a", True, "ok"), ("b", False, "bad"),
    ])
    assert rc == 1
    out = capsys.readouterr().out
    assert "OVERALL: FAIL" in out
    assert "FAIL b: bad" in out


def test_report_unverifiable_exit_2():
    rc = _mod._report(_Args(), "langfuse", [
        ("a", None, "missing"), ("b", None, "missing2"),
    ])
    assert rc == 2


def test_main_unknown_subcommand_exits_2():
    import subprocess
    import sys as _sys
    proc = subprocess.run(
        [_sys.executable, str(_MANAGE / "fleet-hygiene.py"), "nope"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 2


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
