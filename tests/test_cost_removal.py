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
import shutil
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


def run_cleanup(home: Path, deploy: Path, path_prefix: Path | None = None,
                extra_env: dict | None = None) -> subprocess.CompletedProcess:
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
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env.get('PATH', '')}"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(["bash", str(path)], capture_output=True, text=True, env=env, timeout=120)


def stub_python3_without_ruamel(tmp: Path) -> Path:
    """A directory whose `python3` cannot import ruamel.yaml — the fleet's real shape.

    Measured on a fleet host: PATH python3 is /usr/bin/python3 and `import ruamel.yaml`
    raises ModuleNotFoundError there, while the cortex venv has no ruamel either.
    """
    fake_bin = tmp / "yamlless-bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    stub = fake_bin / "python3"
    stub.write_text(
        "#!/bin/sh\n"
        "echo 'cost keys NOT dropped: ruamel.yaml missing in this interpreter' >&2\n"
        "exit 3\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return fake_bin


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


def test_converged_host_writes_NOTHING_to_stderr_even_with_a_yamlless_python3(tmp_path):
    """The defect that failed the fleet's updates — a warning read as a failure.

    A host that already dropped the cost keys has NOTHING for this step to do, so it must
    produce no stderr at all, whatever interpreter its PATH resolves. The queue-driven
    updater treats exit=1 (cortex-update's soft "nothing to update" code) as success ONLY
    when stderr is empty (ops/scripts/agent/agent-message-handler.py l.519-522), so the
    ruamel warning turned a completed update into "❌ cortex-update failed" on every host
    whose python3 lacks ruamel — measured on a real fleet host, whose config carries no
    cost keys and whose PATH python3 is /usr/bin/python3.
    """
    home, deploy = make_host(tmp_path)
    cfg = home / ".hermes/config.yaml"
    cfg.write_text(
        "model:\n  default: keep-me\ncron:\n  enabled: true\n"
        "display:\n  skin: default\n",
        encoding="utf-8",
    )
    before = cfg.read_bytes()

    proc = run_cleanup(home, deploy, path_prefix=stub_python3_without_ruamel(tmp_path))

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stderr == "", f"converged host still wrote to stderr: {proc.stderr!r}"
    assert cfg.read_bytes() == before
    assert "not dropped" not in proc.stdout


def test_keys_present_finds_an_interpreter_that_can_import_ruamel(tmp_path):
    """When there IS something to drop, the step must not settle for a useless python3.

    PATH is deliberately poisoned with a python3 that fails, so a pass means the function
    looked PAST it (CORTEX_PYTHON, then the candidates) instead of using the first python3
    it met. This is the other direction of the same fix, and it must NOT weaken
    test_missing_yaml_loader_warns_and_leaves_the_keys: with no capable interpreter at all,
    the warning and the surviving keys are still correct.

    Skipped only when THIS host has no interpreter that can import ruamel.yaml — which is
    itself a real host state (a fleet host measured with none), so the skip is reported
    rather than counted as a pass.
    """
    capable = _interpreter_with_ruamel()
    if capable is None:
        pytest.skip("no interpreter on this host can import ruamel.yaml — no capability to test")
    home, deploy = make_host(tmp_path)
    proc = run_cleanup(home, deploy, path_prefix=stub_python3_without_ruamel(tmp_path),
                       extra_env={"CORTEX_PYTHON": capable})

    assert proc.returncode == 0, proc.stdout + proc.stderr
    import yaml

    cfg = yaml.safe_load((home / ".hermes/config.yaml").read_text(encoding="utf-8"))
    assert cfg["model"]["default"] == "keep-me"
    assert cfg["display"]["skin"] == "default"
    assert cfg.get("cron", {}) == {}, "the retired keys must actually be dropped"
    assert "dropped cron.provider=cost-guard" in proc.stdout


def _interpreter_with_ruamel() -> str | None:
    """An interpreter that can import ruamel.yaml, probed with a CLEAN environment.

    PYTHONPATH/PYTHONHOME are removed for the probe: an inherited site-packages decides a
    capability test for you, and would otherwise make this test exercise the wrong branch.
    """
    candidates = [sys.executable, shutil.which("python3"), "/usr/bin/python3"]
    candidates += [str(Path.home() / v) for v in (
        ".hermes-cortex/venv/bin/python", ".hermes/hermes-agent/venv/bin/python",
        "hermes-cortex/.venv/bin/python",
    )]
    for cand in candidates:
        if not cand or not Path(cand).exists():
            continue
        probe = subprocess.run(["env", "-u", "PYTHONPATH", "-u", "PYTHONHOME", cand,
                                "-c", "import ruamel.yaml"],
                               capture_output=True, text=True, timeout=60)
        if probe.returncode == 0:
            return cand
    return None


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
