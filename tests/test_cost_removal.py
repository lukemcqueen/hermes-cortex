#!/usr/bin/env python3
"""Tests for remove_cost_tracking() — the fleet-wide cost-tracking cleanup.

The function lives in ops/scripts/cortex-update.sh and runs on every deploy, so it
is exercised here against a THROWAWAY HOME: artifacts (the cron.provider plugin,
the cost DB, the deployed scripts, the retired skill) plus a config.yaml carrying
the cost keys. Assertions:

  1. every artifact is gone, and the cost keys are dropped from config.yaml while
     unrelated config survives (the config edit is the half a "files removed" test
     would miss);
  2. a second run is a no-op — zero artifacts removed, config byte-identical
     (idempotent, safe on the 3 hosts that never had it);
  3. a host with nothing to remove still exits 0 (cortex-update keeps going).

Run: python3 -m pytest tests/test_cost_removal.py -v
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
UPDATE_SH = REPO / "ops" / "scripts" / "cortex-update.sh"

COST_SCRIPTS = [
    "cost_store.py",
    "max_cost_guard.py",
    "fleet-costs.py",
    "fleet-cost-query.py",
    "orch-daily-cost-report.py",
    "orch-axi-telemetry.py",
    "agent-budget-enforcer.py",
    "install-cron-cost-tracking.py",
]


def function_body(name: str = "remove_cost_tracking") -> str:
    """Extract the function verbatim from cortex-update.sh (no copy to drift)."""
    text = UPDATE_SH.read_text(encoding="utf-8")
    start = text.index(f"{name}() {{")
    end = text.index("\n}\n", start)
    return text[start:end] + "\n}\n"


def make_host(tmp: Path) -> tuple[Path, Path]:
    """Build a throwaway host tree carrying every artifact the cleanup targets."""
    home = tmp / "home"
    deploy = tmp / "deploy-home"
    (home / ".hermes/plugins/cost-guard").mkdir(parents=True)
    (home / ".hermes/plugins/cost-guard/__init__.py").write_text("# provider\n", encoding="utf-8")
    (home / ".hermes/cron").mkdir(parents=True)
    (home / ".hermes/cron/cron-costs.db").write_text("sqlite\n", encoding="utf-8")
    (home / ".hermes/skills/devops/cron-cost-tracking").mkdir(parents=True)
    (home / ".hermes/skills/devops/cron-cost-tracking/SKILL.md").write_text("--\n", encoding="utf-8")
    (deploy / "scripts").mkdir(parents=True)
    for name in COST_SCRIPTS:
        (deploy / "scripts" / name).write_text("# cost\n", encoding="utf-8")
    (home / ".hermes/config.yaml").write_text(
        "model:\n  default: keep-me\n"
        "cron:\n  provider: cost-guard\n  cost_guard:\n    enabled: true\n"
        "  cost_tracking:\n    enabled: true\n"
        "display:\n  skin: default\n",
        encoding="utf-8",
    )
    return home, deploy


def run_cleanup(home: Path, deploy: Path) -> subprocess.CompletedProcess:
    script = f"""
set -uo pipefail
export HOME="{home}"
export CORTEX_DEPLOY_HOME="{deploy}"
info() {{ printf 'INFO %s\\n' "$*"; }}
warn() {{ printf 'WARN %s\\n' "$*" >&2; }}
{function_body()}
remove_cost_tracking
echo "rc=$?"
"""
    path = script_path = Path(home).parent / "run-cleanup.sh"
    script_path.write_text(script, encoding="utf-8")
    env = dict(os.environ)
    # the function's config edit needs ruamel, which ships in the agent venv
    venv_bin = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin"
    if venv_bin.is_dir():
        env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(["bash", str(path)], capture_output=True, text=True, env=env, timeout=120)


def test_removes_every_artifact_and_drops_the_cost_keys(tmp_path):
    home, deploy = make_host(tmp_path)
    proc = run_cleanup(home, deploy)
    assert proc.returncode == 0, f"script failed: {proc.stdout}{proc.stderr}"
    assert "rc=0" in proc.stdout
    assert "cost tracking removed from this host" in proc.stdout

    assert not (home / ".hermes/plugins/cost-guard").exists()
    assert not (home / ".hermes/cron/cron-costs.db").exists()
    assert not (home / ".hermes/skills/devops/cron-cost-tracking").exists()
    leftover = [n for n in COST_SCRIPTS if (deploy / "scripts" / n).exists()]
    assert leftover == [], leftover

    # The config half: cost keys gone, everything else intact. This is what a
    # files-only test would miss, and leaving `provider: cost-guard` behind would
    # make Hermes warn about a provider we deliberately removed.
    import yaml

    cfg = yaml.safe_load((home / ".hermes/config.yaml").read_text(encoding="utf-8"))
    assert cfg["model"]["default"] == "keep-me"
    assert cfg["display"]["skin"] == "default"
    assert cfg.get("cron", {}) == {}
    assert "dropped cron.provider=cost-guard" in proc.stdout + proc.stderr


def test_second_run_is_a_noop_and_leaves_the_config_untouched(tmp_path):
    home, deploy = make_host(tmp_path)
    run_cleanup(home, deploy)
    before = (home / ".hermes/config.yaml").read_bytes()

    proc = run_cleanup(home, deploy)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "cost tracking removed from this host" not in proc.stdout  # nothing to remove
    assert (home / ".hermes/config.yaml").read_bytes() == before


def test_clean_host_exits_zero(tmp_path):
    home = tmp_path / "clean-home"
    (home / ".hermes").mkdir(parents=True)
    deploy = tmp_path / "clean-deploy"
    deploy.mkdir()
    proc = run_cleanup(home, deploy)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "rc=0" in proc.stdout


def test_missing_yaml_loader_warns_and_leaves_the_keys(tmp_path):
    """Non-vacuity: the config half really depends on the loader.

    With a python3 that cannot import ruamel.yaml, the function must NOT claim
    success on the config, must leave the keys in place, and must still let the
    deploy continue (warn, not abort).
    """
    home, deploy = make_host(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    stub = fake_bin / "python3"
    stub.write_text(
        "#!/bin/sh\n"
        "echo 'cost keys NOT dropped: ruamel.yaml missing in this interpreter' >&2\n"
        "exit 3\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)

    script = f"""
set -uo pipefail
export HOME="{home}"
export CORTEX_DEPLOY_HOME="{deploy}"
info() {{ printf 'INFO %s\\n' "$*"; }}
warn() {{ printf 'WARN %s\\n' "$*" >&2; }}
{function_body()}
remove_cost_tracking
echo "rc=$?"
"""
    path = tmp_path / "run-cleanup-noyaml.sh"
    path.write_text(script, encoding="utf-8")
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    proc = subprocess.run(["bash", str(path)], capture_output=True, text=True, env=env, timeout=120)

    assert proc.returncode == 0, proc.stdout + proc.stderr            # deploy continues
    assert "WARN" in proc.stderr and "not dropped" in proc.stderr     # loud, not silent
    import yaml

    cfg = yaml.safe_load((home / ".hermes/config.yaml").read_text(encoding="utf-8"))
    assert cfg["cron"]["provider"] == "cost-guard"                    # keys survive
    assert not (home / ".hermes/plugins/cost-guard").exists()         # files still removed


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
