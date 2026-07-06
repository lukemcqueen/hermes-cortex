#!/usr/bin/env python3
"""_port_arbitration.py — Shared port arbitration for Hermes systemd services.

Prevents crash-looping: checks if the target port is already in use by an
instance of the same service. If yes, exits 0 gracefully so systemd doesn't
restart. If no, claims the port, writes a PID file, and proceeds.

Usage in any Python server:
    from _port_arbitration import check_and_claim_port, release_port, setup_dirs

    setup_dirs("/path/to/data/dir")
    if not check_and_claim_port("127.0.0.1", PORT, "my-service-name"):
        sys.exit(0)  # Another instance is running

    ... start server ...

    release_port()  # In finally block or shutdown handler
"""

import logging
import os
import socket
import sys
from pathlib import Path

_log = logging.getLogger("port-arbitration")

_PID_FILE: Path | None = None
_SERVICE_NAME: str | None = None


def _get_pid_path(service_name: str) -> Path:
    """Return a writable PID file path under XDG_RUNTIME_DIR or /tmp.
    
    Uses XDG_RUNTIME_DIR when available (writable tmpfs), falls back to /tmp.
    Avoids ~/ paths which may be read-only under systemd ProtectHome=read-only.

    NOTE: Under systemd with ProtectHome=read-only + PrivateTmp=yes, this file
    may be invisible to other processes. For cross-process PID detection in that
    case, pass a pid_path override to check_and_claim_port() pointing to a
    ReadWritePaths carve-out directory.
    """
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return Path(runtime_dir) / f"{service_name}.pid"


def setup_dirs(data_dir: str | Path) -> None:
    """Create required directories if missing.
    
    Prevents crash-looping from 'Failed to set up standard output' (exit 209).
    Call before any I/O or bind attempt.
    """
    d = Path(data_dir) if isinstance(data_dir, str) else data_dir
    if not d.exists():
        d.mkdir(parents=True, exist_ok=True)
        _log.info("CREATED — directory: %s", d)


def check_and_claim_port(host: str, port: int, service_name: str, pid_path: str | Path | None = None) -> bool:
    """Check if *port* is free on *host*. If free, claim it and return True.
    
    If taken by another instance of *service_name* (detected via PID file),
    return False so the caller can exit 0 gracefully.
    If taken by an unknown process, exit 1 immediately.
    
    If *pid_path* is provided, use it for the PID file instead of the default
    XDG_RUNTIME_DIR path. This is needed under systemd ProtectHome=read-only
    where the caller should point to a ReadWritePaths carve-out directory.
    """
    global _PID_FILE, _SERVICE_NAME
    _SERVICE_NAME = service_name
    if pid_path:
        _PID_FILE = Path(pid_path) if isinstance(pid_path, str) else pid_path
    else:
        _PID_FILE = _get_pid_path(service_name)

    test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        test_sock.bind((host, port))
        test_sock.close()
        # Port is free — claim it
        _PID_FILE.write_text(str(os.getpid()))
        _log.info("PORT_CHECK — %s:%d is free, claiming", host, port)
        return True
    except OSError as e:
        test_sock.close()
        if e.errno == 98:  # EADDRINUSE
            _log.warning("PORT CONFLICT — %s:%d is already in use", host, port)

            # Check if the owner is another instance of our service via PID file
            if _PID_FILE.exists():
                try:
                    existing_pid = int(_PID_FILE.read_text().strip())
                    proc_path = Path(f"/proc/{existing_pid}/cmdline")
                    if proc_path.exists():
                        cmdline = proc_path.read_text().replace("\0", " ")
                        if service_name.replace("-", "_") in cmdline or service_name in cmdline:
                            _log.info(
                                "PORT HANDOFF — existing %s PID %d is running, exiting 0",
                                service_name, existing_pid,
                            )
                            return False  # Graceful handoff
                        else:
                            _log.warning(
                                "PORT CONFLICT — PID %d exists but is not %s (%s), exiting 1",
                                existing_pid, service_name, cmdline[:80],
                            )
                    else:
                        _log.info("PORT CLEANUP — stale PID file (PID %d gone), removing", existing_pid)
                        _PID_FILE.unlink(missing_ok=True)
                except (ValueError, OSError, IOError) as e2:
                    _log.warning("PORT CONFLICT — could not read PID file: %s", e2)

            _log.error("PORT CONFLICT — %s:%d in use by unknown process, exiting 1", host, port)
            sys.exit(1)
        else:
            _log.error("PORT CHECK — unexpected socket error: %s", e)
            sys.exit(1)


def release_port() -> None:
    """Clean up the PID file. Call in finally block or shutdown handler."""
    if _PID_FILE and _PID_FILE.exists():
        _PID_FILE.unlink(missing_ok=True)
        _log.info("PORT RELEASE — cleaned up PID file: %s", _PID_FILE)
