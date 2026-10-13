#!/usr/bin/env python3
"""The Pi adapter must actually RUN, and the deploy must actually run IT.

  A. `install-pi-integration.sh` needs PyYAML to read the skills manifest, and it
     picked its interpreter by PATH existence (`command -v python3`) — the
     interpreter most likely to LACK it. Measured on esther: the deployed adapter
     answered "PyYAML required (pip install pyyaml)" and exited 1, silently
     skipping the skills half on a host that had everything it needed. It must
     resolve an interpreter that can IMPORT yaml, not one that merely exists.

  B. `cortex-update.sh` registered the installer and never ran it, with no
     Pi-presence check anywhere in the deploy: a host with Pi installed could sit
     unwired with nothing reporting it. The deploy must run the adapters WHEN PI IS
     PRESENT, and leave a host without Pi alone.

Hermetic: no Pi config is touched — the resolver is exercised on its own, and the
deploy assertion is over its source.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ADAPTER = REPO / "ops" / "scripts" / "install" / "install-pi-integration.sh"
DEPLOY = REPO / "ops" / "scripts" / "cortex-update.sh"
RESOLVER = REPO / "ops" / "scripts" / "lib" / "python-with-module.sh"


def test_the_adapter_resolves_yaml_before_falling_back_to_a_bare_python3():
    """A PATH pick is an allowed LAST RESORT; what broke the host was picking by PATH
    FIRST. The order is the property, so the order is what is pinned."""
    src = ADAPTER.read_text()
    assert "python-with-module.sh" in src, "the adapter must use the shared resolver"
    assert "--print yaml" in src, "it must ask for an interpreter that imports yaml"
    assert src.index("python-with-module.sh") < src.index("command -v python3"), (
        "the yaml-capable resolver must be consulted BEFORE a bare PATH pick — "
        "picking by PATH first is what answered 'PyYAML required' on a host that had it")


def test_the_resolver_returns_an_interpreter_that_really_imports_yaml():
    """The mechanism the adapter now depends on, exercised rather than assumed."""
    proc = subprocess.run(["bash", str(RESOLVER), "--print", "yaml"],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    interp = proc.stdout.strip()
    assert interp, "the resolver printed no interpreter"
    proof = subprocess.run([interp, "-c", "import yaml; print(yaml.__version__)"],
                           capture_output=True, text=True, timeout=120)
    assert proof.returncode == 0, (interp, proof.stdout, proof.stderr)
    assert proof.stdout.strip(), "no PyYAML version reported"


def test_the_deploy_runs_the_pi_adapters_and_guards_on_pi_being_present():
    src = DEPLOY.read_text()
    assert "install-pi-integration.sh" in src and "install-pi-mcp.sh" in src
    # The RUNNER, not the register line: the guard block is what makes it happen.
    i = src.index("Pi harness integration")
    block = src[i:i + 1800]
    assert ".pi/agent/bin/pi" in block, "presence of Pi must be what decides"
    assert "bash \"$_pi_script\"" in block, "the deploy must RUN the installer, not just copy it"
    assert "install-pi-mcp.sh install-pi-integration.sh" in block, "both halves are run"
