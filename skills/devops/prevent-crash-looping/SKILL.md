---
name: prevent-crash-looping
version: 1.0.0
description: How to prevent systemd service crash-looping from port conflicts, missing directories, and failed dependencies
category: devops
---

# Prevent Crash-Looping

## Problem
A systemd service fails to start → systemd restarts it (`Restart=on-failure`) → fails again → repeats every `RestartSec` seconds indefinitely. This happens from:
- **Port conflict**: Another process (manual or another instance) holds the port
- **Missing directory**: Log directory doesn't exist → `status=209/STDOUT`
- **Missing dependency**: Python packages not installed in the venv
- **Wrong Python**: System python vs venv python

## Three-Layer Defense

### Layer 1: Port Arbitration (in the service's Python/script)
Before binding, check if the port is already in use. If the owner is another instance of this service, **exit 0** (success) instead of failing. This prevents systemd from restarting.

**Pattern:**
```python
import os, socket, sys
from pathlib import Path

PID_FILE = Path.home() / ".service-name" / "service.pid"

def check_port(host: str, port: int) -> bool:
    """Returns True if port is free, False if owned by our process."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        sock.close()
        PID_FILE.write_text(str(os.getpid()))
        return True
    except OSError as e:
        sock.close()
        if e.errno == 98:  # EADDRINUSE
            if PID_FILE.exists():
                pid = int(PID_FILE.read_text())
                cmdline = Path(f"/proc/{pid}/cmdline")
                if cmdline.exists() and "service-name" in cmdline.read_text().replace("\0", " "):
                    return False  # Graceful handoff
            sys.exit(1)  # Unknown owner
        sys.exit(1)
```

### Layer 2: Systemd Service Hardening
```ini
[Service]
# Auto-create log directory before service starts
ExecStartPre=/bin/mkdir -p %h/.service-name/
# Carve out writable paths under ProtectHome=read-only
ProtectHome=read-only
ReadWritePaths=%h/.service-name/
# Clean up PID on exit
ExecStopPost=/bin/rm -f %h/.service-name/service.pid
```

### Layer 3: Graceful Recovery
- Systemd `Restart=on-failure` paired with port arbitration means:
  - Crash → port free → restart succeeds
  - Manual instance conflicts → exit 0 → no restart triggered
- `systemctl reset-failed` is a workaround, not a fix. Fix the root cause.

## Testing
1. Start the service: `systemctl --user start service-name`
2. Verify running: `systemctl --user status service-name`
3. Test port arbitration: start a second instance manually — should exit 0
4. Test crash recovery: `kill -9 $(pgrep -f service-name)` — systemd should restart cleanly

## Live Example: health-server on Moses
- Service: `com.hermes.health-server.service`
- Script: `~/hermes-cortex/ops/scripts/health/health-server.py` (see `_check_port_conflict()` function)
- Service file: `~/.config/systemd/user/com.hermes.health-server.service`
