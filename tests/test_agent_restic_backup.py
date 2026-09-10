"""agent-restic-backup platform-adaptation tests.

The backup script must run identically on Arch, Debian-family (Mint) and
macOS: restic is the universal engine; only the recipe pieces (package
manifest, system config sources, service snapshot) differ per OS.
"""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "ops" / "scripts" / "agent" / "agent-restic-backup.py"


def _load():
    spec = importlib.util.spec_from_file_location("agent_restic_backup", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def backup_mod():
    return _load()


def test_platform_detection_arch(backup_mod):
    assert backup_mod.OS_FAMILY == "linux"
    assert backup_mod.DISTRO_FAMILY in ("arch", "debian", "rhel", "other")


def test_repo_targets_are_both_defined(backup_mod):
    assert backup_mod.LOCAL_REPO
    assert backup_mod.REMOTE_REPO
    assert backup_mod.LOCAL_REPO != backup_mod.REMOTE_REPO


def test_package_manifest_commands_cover_all_families(backup_mod):
    cmds = backup_mod.package_manifest_commands("arch")
    assert cmds and "pacman" in cmds[0][0]
    cmds = backup_mod.package_manifest_commands("debian")
    assert cmds and "dpkg" in cmds[0][0]
    cmds = backup_mod.package_manifest_commands("macos")
    assert cmds and "brew" in cmds[0][0]


def test_system_config_sources_cover_platforms(backup_mod):
    linux = backup_mod.system_config_sources("linux")
    mac = backup_mod.system_config_sources("macos")
    assert any("/etc" in s for s in linux)
    assert any("homebrew" in s or "LaunchAgents" in s for s in mac)


def test_sources_always_present(backup_mod):
    s = backup_mod.SOURCES
    assert len(s) >= 2  # hermes data + staging at minimum


def test_ensure_repo_inits_when_missing(backup_mod, monkeypatch):
    calls = []

    def fake_run(cmd, env, **kw):
        calls.append(cmd)
        class R:
            returncode = 1 if cmd and cmd[-1] == "config" else 0
            stdout = ""
        return R()
    monkeypatch.setattr(backup_mod.subprocess, "run", fake_run)
    backup_mod.log = lambda msg: None
    backup_mod._ensure_repo("sftp:example:~/backups/x/restic-repo", {})
    assert any("init" in c for c in calls)


def test_ensure_repo_skips_when_initialized(backup_mod, monkeypatch):
    calls = []

    def fake_run(cmd, env, **kw):
        calls.append(cmd)
        class R:
            returncode = 0
            stdout = ""
        return R()
    monkeypatch.setattr(backup_mod.subprocess, "run", fake_run)
    backup_mod.log = lambda msg: None
    backup_mod._ensure_repo("sftp:example:~/backups/x/restic-repo", {})
    assert not any("init" in c for c in calls)