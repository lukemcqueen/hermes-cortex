"""Coverage for the bridge KillMode auto-repair installer.

The behavioural proof ships INSIDE the installer (`--self-test`), so it travels
with the file a reviewer holds on its own; this module re-runs it as a
subprocess, and asserts the deploy wiring that cortex-update.sh carries so a
future edit cannot silently drop the repair from the update path.

The installer under test: ops/scripts/install/install-bridge-killmode.sh
Contract (exit codes): 0 = every bridge unit loads KillMode=process (or none
exists), 1 = a unit is still wrong after the repair (named on stderr),
2 = bridge units exist but the generator is missing, 3 = self-test could not run.
The self-test itself writes only inside a private mktemp dir and never
addresses the real systemd user manager (a fake systemctl is first on PATH).
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / "ops" / "scripts" / "install" / "install-bridge-killmode.sh"
UPDATER = REPO / "ops" / "scripts" / "cortex-update.sh"

_SELF_TEST_PASS = "self-test: all cases PASS"


def test_installer_self_test_passes():
    proc = subprocess.run(
        ["bash", str(INSTALLER), "--self-test"],
        capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _SELF_TEST_PASS in proc.stdout, proc.stdout


def test_self_test_covers_both_directions():
    """The documented cases must include the repair AND a refusal."""
    proc = subprocess.run(
        ["bash", str(INSTALLER), "--self-test"],
        capture_output=True, text=True, timeout=300,
    )
    for case in (
        "repair: file fixed",
        "repair: reloaded once",
        "idempotent: no reload",
        "override: file untouched",
        "unrepairable: exit 1",
        "reload-fails: exit 1",
    ):
        assert f"PASS {case}" in proc.stdout, f"case not passing: {case}\n{proc.stdout}"


def _shipped_invocation_block() -> str:
    """The verbatim if/invoke/warn/fi block for this installer in cortex-update.sh.

    Extracted rather than retyped, so the test drives the shipped text: if the
    invocation is ever rewritten, this block (and the test) changes with it.
    """
    lines = UPDATER.read_text().splitlines()
    marker = 'if [[ -f "${CORTEX_DEPLOY_HOME}/scripts/install-bridge-killmode.sh" ]]; then'
    start = next(i for i, line in enumerate(lines) if line.strip() == marker)
    block = lines[start:start + 4]
    assert block[3].strip() == "fi", f"unexpected block shape: {block}"
    return "\n".join(block)


def test_update_path_surfaces_a_failing_installer(tmp_path):
    """cortex-update.sh must WARN (not swallow) when the installer exits non-zero.

    The invocation pipes the installer through `sed`, whose exit status would
    hide the installer's own — unless pipefail is set, which cortex-update.sh
    does. This runs the shipped block verbatim under the same shell options
    against a stand-in deploy home whose installer exits 1.
    """
    updater = UPDATER.read_text()
    assert "set -euo pipefail" in updater, (
        "cortex-update.sh must set pipefail for the `| sed || warn` invocation "
        "to reflect the installer's exit status"
    )

    deploy = tmp_path / "deploy"
    scripts = deploy / "scripts"
    scripts.mkdir(parents=True)
    failing = scripts / "install-bridge-killmode.sh"
    failing.write_text("#!/usr/bin/env bash\necho 'installer says no'\nexit 1\n")
    failing.chmod(0o755)

    harness = tmp_path / "harness.sh"
    harness.write_text(
        "set -euo pipefail\n"
        'warn() { printf "WARN: %s\\n" "$*"; }\n'
        + _shipped_invocation_block() + "\n"
        'echo "reached the end of the update step"\n'
    )

    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
           "CORTEX_DEPLOY_HOME": str(deploy)}
    failed_run = subprocess.run(
        ["bash", str(harness)], capture_output=True, text=True, env=env, timeout=60)
    assert failed_run.returncode == 0, failed_run.stdout + failed_run.stderr
    assert "WARN:   install-bridge-killmode.sh failed (non-fatal)" in failed_run.stdout
    assert "reached the end of the update step" in failed_run.stdout, (
        "a non-fatal installer failure must not abort the deploy"
    )

    # The other direction: a succeeding installer must not warn.
    failing.write_text("#!/usr/bin/env bash\necho ok\nexit 0\n")
    ok_run = subprocess.run(
        ["bash", str(harness)], capture_output=True, text=True, env=env, timeout=60)
    assert ok_run.returncode == 0, ok_run.stdout + ok_run.stderr
    assert "WARN" not in ok_run.stdout, ok_run.stdout


def test_updater_registers_and_invokes_the_installer():
    src = UPDATER.read_text()
    assert (
        'register "ops/scripts/install/install-bridge-killmode.sh" '
        '"${CORTEX_DEPLOY_HOME}/scripts/install-bridge-killmode.sh"' in src
    ), "installer is not registered for deploy by cortex-update.sh"
    assert (
        'bash "${CORTEX_DEPLOY_HOME}/scripts/install-bridge-killmode.sh" 2>&1 | sed' in src
    ), "installer is not invoked from the cortex-update.sh update path"
    assert (
        'warn "  install-bridge-killmode.sh failed (non-fatal)"' in src
    ), "installer failure is not surfaced as a warning"
