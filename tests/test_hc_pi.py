#!/usr/bin/env python3
"""Tests for `hc pi` — the host-level Pi wiring command (cycle 13505).

Edge cases matter more than the happy path here: the command decides whether a host is
wired from PRESENCE (a host without Pi is not a fault) and REPORTS an owner's rc rather
than inventing one. Both are places where a wrong branch turns a real failure into a
green, so each is asserted in both directions.

Everything runs against a fabricated HOME; no test touches the live ~/.pi or the real
installers.
"""

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HC = REPO / "ops" / "scripts" / "hc" / "hc.py"


def _load_hc():
    spec = importlib.util.spec_from_file_location("hc_under_test", HC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def hc(tmp_path, monkeypatch):
    """hc with HOME pointed at a scratch dir, so every path decision is controlled."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HC_AGENT", raising=False)
    mod = _load_hc()
    return mod


def _cfg():
    return {"agent": "testagent"}


def _pi_agent(tmp_path, present=True):
    d = tmp_path / ".pi" / "agent"
    if present:
        d.mkdir(parents=True, exist_ok=True)
    return d


def _exit_code(fn):
    try:
        fn()
    except SystemExit as exc:
        return exc.code
    return None


# ── dispatch / usage ──────────────────────────────────────────────────────

def test_no_subcommand_defaults_to_check(hc, tmp_path, monkeypatch):
    _pi_agent(tmp_path)
    seen = []
    monkeypatch.setattr(hc, "_resolve_script", lambda name: Path("/bin/true"))
    monkeypatch.setattr(hc, "_run_script", lambda p, a: seen.append((p, tuple(a))) or 0)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), [])) == 0
    assert any("--check" in args for _, args in seen), "default must be the check path"


@pytest.mark.parametrize("flag", ["help", "-h", "--help"])
def test_help_exits_zero_on_every_spelling(hc, flag, capsys):
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), [flag])) == 0
    assert "hc pi install" in capsys.readouterr().out


def test_unknown_subcommand_is_usage_error_not_success(hc, capsys):
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["wibble"])) == 2
    assert "unknown subcommand" in capsys.readouterr().err


def test_unknown_subcommand_checked_before_pi_presence(hc, tmp_path):
    """A typo must not be answered with 'no Pi on this host' — that reads as a skip."""
    _pi_agent(tmp_path, present=False)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["instal"])) == 2


# ── a host without Pi is NOT a fault ──────────────────────────────────────

@pytest.mark.parametrize("sub", ["install", "check"])
def test_absent_pi_is_skipped_not_failed(hc, tmp_path, sub, capsys):
    _pi_agent(tmp_path, present=False)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), [sub])) == 0
    assert "not a fault" in capsys.readouterr().out


def test_absent_pi_never_runs_the_installers(hc, tmp_path, monkeypatch):
    _pi_agent(tmp_path, present=False)
    monkeypatch.setattr(hc, "_resolve_script",
                        lambda name: pytest.fail("must not resolve scripts with no Pi"))
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["install"])) == 0


# ── install: both halves run, the worst rc wins ───────────────────────────

def test_install_runs_both_halves_in_order(hc, tmp_path, monkeypatch):
    """MCP first, then the integration — asserted so a future reorder is a deliberate
    change rather than an accident."""
    _pi_agent(tmp_path)
    resolved, ran = [], []
    monkeypatch.setattr(hc, "_resolve_script",
                        lambda name: resolved.append(name) or Path("/bin/true"))
    monkeypatch.setattr(hc, "_run_script", lambda p, a: ran.append(p) or 0)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["install"])) == 0
    assert resolved == ["install-pi-mcp.sh", "install-pi-integration.sh"]
    assert len(ran) == 2


def test_install_reports_a_failure_rc(hc, tmp_path, monkeypatch):
    _pi_agent(tmp_path)
    monkeypatch.setattr(hc, "_resolve_script", lambda name: Path("/bin/true"))
    monkeypatch.setattr(hc, "_run_script", lambda p, a: 3)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["install"])) == 3


def test_install_missing_script_is_a_failure_not_a_pass(hc, tmp_path, monkeypatch, capsys):
    """A script that is not on the host must fail loudly: bash <missing> would exit 127
    and read as a failed install rather than a missing prerequisite."""
    _pi_agent(tmp_path)
    monkeypatch.setattr(hc, "_resolve_script", lambda name: None)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["install"])) == 1
    assert "cortex-update.sh" in capsys.readouterr().err


def test_install_passes_extra_args_through(hc, tmp_path, monkeypatch):
    _pi_agent(tmp_path)
    seen = []
    monkeypatch.setattr(hc, "_resolve_script", lambda name: Path("/bin/true"))
    monkeypatch.setattr(hc, "_run_script", lambda p, a: seen.append(tuple(a)) or 0)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["install", "--check"])) == 0
    assert ("--check",) in seen


# ── check: both verdicts run, the worst rc wins ───────────────────────────

def test_check_runs_installer_then_audit_and_takes_the_worst_rc(hc, tmp_path, monkeypatch):
    """The installer check failing must NOT stop the audit — both verdicts are wanted,
    and the worst rc is the command's answer."""
    _pi_agent(tmp_path)
    calls = []

    def fake_run(p, a):
        calls.append(Path(str(p)).name)
        return 1 if "install" in str(p) else 0

    monkeypatch.setattr(hc, "_resolve_script", lambda name: Path("/bin/" + name))
    monkeypatch.setattr(hc, "_run_script", fake_run)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["check"])) == 1
    assert len(calls) == 2, f"the audit must still run (calls={calls})"


def test_a_later_worse_rc_is_not_masked(hc, tmp_path, monkeypatch):
    """`rc or r` keeps the FIRST nonzero rc, so a later failure carrying a HIGHER
    one is reported as the earlier, milder value — the command answers "rc=1"
    while the run that actually broke returned 3. Worst must win."""
    _pi_agent(tmp_path)
    monkeypatch.setattr(hc, "_resolve_script", lambda name: Path("/bin/" + name))
    monkeypatch.setattr(hc, "_run_script", lambda p, a: 1 if "install" in str(p) else 3)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["check"])) == 3


def test_install_reports_the_worst_rc_not_the_first(hc, tmp_path, monkeypatch):
    _pi_agent(tmp_path)
    monkeypatch.setattr(hc, "_resolve_script", lambda name: Path("/bin/" + name))
    monkeypatch.setattr(hc, "_run_script", lambda p, a: 1 if "mcp" in str(p) else 3)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["install"])) == 3


def test_a_missing_script_does_not_mask_a_later_worse_rc(hc, tmp_path, monkeypatch):
    """A missing half is rc 1; a later real failure at rc 2 must still surface."""
    _pi_agent(tmp_path)
    monkeypatch.setattr(hc, "_resolve_script",
                        lambda name: None if "mcp" in name else Path("/bin/" + name))
    monkeypatch.setattr(hc, "_run_script", lambda p, a: 2)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["install"])) == 2


def test_check_missing_audit_is_a_failure(hc, tmp_path, monkeypatch, capsys):
    _pi_agent(tmp_path)
    monkeypatch.setattr(hc, "_resolve_script",
                        lambda name: None if "audit" in name else Path("/bin/true"))
    monkeypatch.setattr(hc, "_run_script", lambda p, a: 0)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["check"])) == 1
    assert "cortex-update.sh" in capsys.readouterr().err


# ── skills: reports the registration, delegates the verdict ───────────────

def test_skills_missing_settings_is_not_a_silent_pass(hc, tmp_path, capsys):
    _pi_agent(tmp_path)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["skills"])) == 1
    assert "hc pi install" in capsys.readouterr().err


def test_skills_invalid_json_fails_closed(hc, tmp_path, capsys):
    agent = _pi_agent(tmp_path)
    (agent / "settings.json").write_text("{not json")
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["skills"])) == 1
    assert "cannot read" in capsys.readouterr().err


def test_skills_prints_every_registered_entry(hc, tmp_path, monkeypatch, capsys):
    agent = _pi_agent(tmp_path)
    (agent / "settings.json").write_text(json.dumps(
        {"skills": ["/home/x/.agents/skills", "/tmp/other"]}))
    monkeypatch.setattr(hc, "_resolve_script", lambda name: Path("/bin/true"))
    monkeypatch.setattr(hc, "_run_script", lambda p, a: 0)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["skills"])) == 0
    out = capsys.readouterr().out
    assert "/home/x/.agents/skills" in out and "/tmp/other" in out


def test_skills_with_no_entries_says_so(hc, tmp_path, monkeypatch, capsys):
    agent = _pi_agent(tmp_path)
    (agent / "settings.json").write_text(json.dumps({"skills": []}))
    monkeypatch.setattr(hc, "_resolve_script", lambda name: Path("/bin/true"))
    monkeypatch.setattr(hc, "_run_script", lambda p, a: 0)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["skills"])) == 0
    assert "none" in capsys.readouterr().out


def test_skills_propagates_the_delegated_rc(hc, tmp_path, monkeypatch):
    """The visibility verdict belongs to the installer; hc pi must not soften it."""
    agent = _pi_agent(tmp_path)
    (agent / "settings.json").write_text(json.dumps({"skills": ["/x"]}))
    monkeypatch.setattr(hc, "_resolve_script", lambda name: Path("/bin/true"))
    monkeypatch.setattr(hc, "_run_script", lambda p, a: 1)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["skills"])) == 1


def test_skills_works_without_pi_present_but_reports_the_missing_config(hc, tmp_path, capsys):
    _pi_agent(tmp_path, present=False)
    assert _exit_code(lambda: hc.cmd_pi(_cfg(), ["skills"])) == 1


# ── _resolve_script: repo before deployed, None when absent ───────────────

def test_resolve_script_prefers_the_repo_checkout(hc, tmp_path, monkeypatch):
    repo = tmp_path / "hermes-cortex" / "ops" / "scripts" / "install"
    dep = tmp_path / ".hermes-cortex" / "scripts"
    repo.mkdir(parents=True); dep.mkdir(parents=True)
    (repo / "install-pi-mcp.sh").write_text("#!/bin/sh\n")
    (dep / "install-pi-mcp.sh").write_text("#!/bin/sh\n")
    assert hc._resolve_script("install-pi-mcp.sh") == repo / "install-pi-mcp.sh"


def test_resolve_script_falls_back_to_the_deployed_tree(hc, tmp_path):
    """A script that exists ONLY in the deployed tree must still be found.

    (The repo-side candidates are checked first and legitimately win when they exist —
    that is why this test uses a name the checkout cannot have.)
    """
    dep = tmp_path / ".hermes-cortex" / "scripts"
    dep.mkdir(parents=True)
    name = "audit-not-in-the-checkout.sh"
    (dep / name).write_text("#!/bin/sh\n")
    assert hc._resolve_script(name) == dep / name


def test_resolve_script_absent_returns_none(hc, tmp_path):
    assert hc._resolve_script("does-not-exist.sh") is None


# ── _run_script: flushes first so the report cannot read out of order ──────

def test_run_script_flushes_stdout_before_delegating(hc, monkeypatch, tmp_path):
    events = []

    class FakeOut:
        def flush(self):
            events.append("flush")

        def write(self, s):
            events.append("write")

    def fake_run(cmd, *a, **kw):
        events.append("run")

        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(hc.sys, "stdout", FakeOut())
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert hc._run_script(Path("/bin/true"), []) == 0
    assert events == ["flush", "run"], f"unexpected order: {events}"


# ── end-to-end: the real command, no Pi on the host ───────────────────────

def test_end_to_end_without_pi_exits_zero_and_says_why(tmp_path):
    """The real command, real argv, real exit status — with an agent identity because
    hc refuses to run without one (that refusal is its own correct behaviour)."""
    env = dict(os.environ, HOME=str(tmp_path), HC_AGENT="testagent")
    env.pop("PYTHONPATH", None)
    r = subprocess.run([sys.executable, str(HC), "pi", "check"],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "not a fault" in r.stdout


def test_end_to_end_bad_subcommand_keeps_hc_usage_exit_code(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), HC_AGENT="testagent")
    r = subprocess.run([sys.executable, str(HC), "pi", "nonsense"],
                       capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "unknown subcommand" in r.stderr
