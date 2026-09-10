#!/usr/bin/env python3
"""agent-restic-backup.py — fleet-wide cross-platform restic backup (weekly).

One backup engine (restic) on every fleet host: Arch, Debian-family (Mint),
RHEL-family, and macOS. Two restic repos per agent, both snapshotted on the
same weekly run:
  LOCAL_REPO   ~/backups/restic-repo          (same-disk, fast rollback)
  REMOTE_REPO  sftp:<backup_host>:~/backups/<agent>/restic-repo  (off-box)

Only the *recipe* differs per OS — package manifest, system config paths,
service snapshot. restic itself is byte-identical everywhere.

Env / files:
  RESTIC_BIN            restic binary (default ~/.local/bin/restic, else PATH)
  RESTIC_EXCLUDES       exclude file (default ~/.local/bin/restic-excludes.txt)
  RESTIC_PASSWORD_FILE  passphrase file (default ~/.hermes-cortex/state/restic/passphrase)
  RESTIC_REMOTE         remote repo spec (default sftp:<BACKUP_HOST>:~/backups/<agent>/restic-repo)
  BACKUP_HOST           hostname used in the default remote repo (default esther)

Watchdog pattern: empty stdout = silent; alert text on failure is delivered.
"""
from __future__ import annotations

import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from datetime import date
from pathlib import Path

HOME = Path.home()
LOG = HOME / "backups" / "restic-backup.log"
STAGING = HOME / "backups" / "restic-staging"

# ── Platform detection -----------------------------------------------------
OS_FAMILY = "macos" if platform.system() == "Darwin" else "linux"
DISTRO_FAMILY = "other"
if OS_FAMILY == "linux":
    try:
        _osr = Path("/etc/os-release").read_text()
    except OSError:
        _osr = ""
    if "ID=arch" in _osr or "ID=manjaro" in _osr or "ID=endeavouros" in _osr:
        DISTRO_FAMILY = "arch"
    elif "ID=debian" in _osr or "ID=ubuntu" in _osr or "ID=linuxmint" in _osr:
        DISTRO_FAMILY = "debian"
    elif "ID=fedora" in _osr or "ID=rhel" in _osr or "ID=centos" in _osr:
        DISTRO_FAMILY = "rhel"

# Agent identity: env first (cron sets it), else cortex-bus.conf, else HOME name
AGENT_NAME = os.environ.get("AGENT_NAME", "")
if not AGENT_NAME:
    bus_conf = HOME / ".hermes-cortex" / "cortex-bus.conf"
    if bus_conf.exists():
        for line in bus_conf.read_text().splitlines():
            if line.startswith("AGENT_NAME="):
                AGENT_NAME = line.split("=", 1)[1].strip().strip("\"'")
                break
AGENT_NAME = AGENT_NAME or HOME.name

# ── Targets (per-host local + off-box copy) --------------------------------
RESTIC_BIN = os.environ.get("RESTIC_BIN") or str(HOME / ".local" / "bin" / "restic")
if not Path(RESTIC_BIN).exists():
    RESTIC_BIN = shutil.which("restic") or RESTIC_BIN
EXCLUDES = Path(os.environ.get("RESTIC_EXCLUDES") or (HOME / ".local" / "bin" / "restic-excludes.txt"))
PASSFILE = Path(os.environ.get("RESTIC_PASSWORD_FILE") or (HOME / ".hermes-cortex" / "state" / "restic" / "passphrase"))
LOCAL_REPO = HOME / "backups" / "restic-repo"
BACKUP_HOST = os.environ.get("BACKUP_HOST", "esther")
REMOTE_REPO = os.environ.get("RESTIC_REMOTE") or f"sftp:{BACKUP_HOST}:~/backups/{AGENT_NAME}/restic-repo"

# ── Sources (same on every OS; existence-checked) --------------------------
SOURCES = [s for s in [
    str(HOME / ".hermes"),
    str(HOME / "brain") if (HOME / "brain").exists() else None,
    str(HOME / ".brain") if (HOME / ".brain").exists() else None,
    str(HOME / "backups" / "os-level-2026-08-02-v3.tar.gz") if (HOME / "backups" / "os-level-2026-08-02-v3.tar.gz").exists() else None,
    str(HOME / "backups" / "checksums.local.txt") if (HOME / "backups" / "checksums.local.txt").exists() else None,
    str(HOME / "backups" / "checksums.remote.txt") if (HOME / "backups" / "checksums.remote.txt").exists() else None,
    str(STAGING),
] if s]


def log(msg: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a") as fh:
            fh.write(f"[{date.today().isoformat()}] {msg}\n")
    except OSError:
        pass  # logging is best-effort — never fail the backup over it


def _run(cmd: list[str], env: dict, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    if check and result.returncode != 0:
        raise SystemExit(f"command failed (exit {result.returncode}): {result.stdout[-500:]}")
    return result


def _ensure_repo(repo: str, env: dict) -> None:
    """Init the restic repo if it does not exist yet (first run on a host)."""
    probe = subprocess.run([RESTIC_BIN, "cat", "config"], env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if probe.returncode == 0:
        return  # repo already initialized
    init = subprocess.run([RESTIC_BIN, "init"], env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if init.returncode != 0:
        raise SystemExit(f"restic init failed for {repo} (exit {init.returncode}): {init.stdout[-500:]}")
    log(f"initialized restic repo -> {repo}")


# ── Per-OS recipe (the only thing that varies) -----------------------------
def package_manifest_commands(family: str) -> list[list[str]] | None:
    """Command(s) that dump the package manifest for a distro family."""
    if family == "arch":
        return [["pacman", "-Qqe"], ["pacman", "-Qmq"]]  # explicit + AUR/foreign
    if family == "debian":
        return [["dpkg", "--get-selections"], ["apt-mark", "showmanual"]]
    if family == "rhel":
        return [["rpm", "-qa"]]
    if family == "macos":
        return [["brew", "list", "--formula"]]
    return None


def system_config_sources(family: str) -> list[str]:
    """System-level config dirs to snapshot (recipe, not a full image)."""
    if family == "macos":
        return [s for s in [
            "/opt/homebrew/etc" if Path("/opt/homebrew/etc").exists() else "/usr/local/etc",
            str(HOME / "Library" / "LaunchAgents") if (HOME / "Library" / "LaunchAgents").exists() else None,
            "/etc/pf.conf" if Path("/etc/pf.conf").exists() else None,
        ] if s]
    return [s for s in [
        "/etc",
        str(HOME / ".config") if (HOME / ".config").exists() else None,
    ] if s]


def service_snapshot(family: str) -> list[str] | None:
    if family == "macos":
        return ["launchctl", "list"]
    return ["systemctl", "list-units", "--type=service", "--no-pager"]


# ── Main -------------------------------------------------------------------
def main() -> None:
    # 1. staging: consistent snapshots of live state
    STAGING.mkdir(parents=True, exist_ok=True)

    # 1a. hermes state.db — WAL-consistent copy via sqlite online backup API
    state_db = HOME / ".hermes" / "state.db"
    if state_db.exists():
        src = sqlite3.connect(str(state_db))
        dst = sqlite3.connect(str(STAGING / "state.db"))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        log("staged state.db via sqlite backup API")

    # 1b. mycortex knowledge brain (Linux containers only; absent = skip)
    if shutil.which("docker") is not None and OS_FAMILY == "linux":
        probe = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                               capture_output=True, text=True)
        if "mycortex-postgres" in probe.stdout:
            with open(STAGING / "mycortex.dump", "wb") as out:
                proc = subprocess.run(
                    ["docker", "exec", "mycortex-postgres", "pg_dump", "-U", "mycortex",
                     "-d", "mycortex", "--format=custom"],
                    stdout=out,
                )
                if proc.returncode != 0:
                    raise SystemExit(f"pg_dump failed with exit {proc.returncode}")
            log("dumped mycortex-postgres")

    # 1c. host recipe — packages, configs, services, crontab
    host_dir = STAGING / f"hostinfo-{date.today().isoformat()}"
    host_dir.mkdir(exist_ok=True)
    for name in (".zshrc", ".bashrc", ".profile", ".gitconfig", ".git-credentials"):
        src_file = HOME / name
        if src_file.is_file():
            (host_dir / name).write_text(src_file.read_text())

    pkg_cmds = package_manifest_commands(DISTRO_FAMILY)
    if pkg_cmds:
        for i, cmd in enumerate(pkg_cmds):
            out = subprocess.run(cmd, capture_output=True, text=True)
            if out.returncode == 0:
                (host_dir / f"packages-{DISTRO_FAMILY}-{i}.txt").write_text(out.stdout)

    cfg_names = system_config_sources(OS_FAMILY)
    for i, cfg in enumerate(cfg_names):
        if not cfg or not Path(cfg).exists():
            continue
        tgz = STAGING / f"sysconfig-{i}.tar.gz"
        with tarfile.open(tgz, "w:gz") as tf:
            tf.add(cfg, arcname=Path(cfg).name)
        (host_dir / f"sysconfig-{i}.tar.gz").symlink_to(tgz)

    svc = service_snapshot(OS_FAMILY)
    if svc:
        out = subprocess.run(svc, capture_output=True, text=True)
        if out.returncode == 0:
            (host_dir / "services.txt").write_text(out.stdout)

    if shutil.which("crontab") is not None:  # absent on hosts without cron package
        crontab = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if crontab.returncode == 0:
            (host_dir / "crontab.txt").write_text(crontab.stdout)

    with tarfile.open(STAGING / f"host-info-{date.today().isoformat()}.tar", "w") as tf:
        tf.add(host_dir, arcname=host_dir.name)
    for child in host_dir.iterdir():
        child.unlink(missing_ok=True)
    host_dir.rmdir()

    # 2. restic backup — local repo, then remote repo
    env = dict(os.environ, RESTIC_PASSWORD_FILE=str(PASSFILE))
    cmd = [RESTIC_BIN, "backup", "--exclude-file", str(EXCLUDES), "--tag", "weekly"]
    for repo in (str(LOCAL_REPO), REMOTE_REPO):
        env_repo = dict(env, RESTIC_REPOSITORY=repo)
        _ensure_repo(repo, env_repo)
        result = subprocess.run(cmd + SOURCES, env=env_repo, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        if result.returncode != 0:
            raise SystemExit(f"restic backup to {repo} failed (exit {result.returncode}): {result.stdout[-500:]}")
        log(f"restic backup OK -> {repo}")

    # 3. retention (weekly kind: 8 weekly + 6 monthly + last 1)
    for repo in (str(LOCAL_REPO), REMOTE_REPO):
        env_ret = dict(env, RESTIC_REPOSITORY=repo)
        forget = [RESTIC_BIN, "forget", "--keep-weekly", "8", "--keep-monthly", "6", "--keep-last", "1"]
        if date.today().isoweekday() == 7:  # Sunday: prune
            forget.append("--prune")
        result = subprocess.run(forget, env=env_ret, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        if result.returncode != 0:
            raise SystemExit(f"restic forget failed for {repo} (exit {result.returncode}): {result.stdout[-500:]}")
        log(f"retention applied -> {repo}")

    log("backup OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # any failure -> alert on stdout (cron delivers it)
        print(f"BACKUP FAILED: {exc} (details: {LOG})")
        sys.exit(1)