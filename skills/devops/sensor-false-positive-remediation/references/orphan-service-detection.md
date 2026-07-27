# Orphan Service Detection & Port-to-Service Mapping

Detect services whose systemd unit files are missing but whose processes are still running — orphan processes that won't survive a reboot.

## Detection Pattern

A service is "orphaned" when `systemctl --user status` shows:

```
● hermes-agent-inbox.service
     Loaded: not-found (Reason: Unit hermes-agent-inbox.service not found.)
     Active: active (running) since ...
```

**Loaded: not-found** + **Active: active (running)** = the unit file was deleted/removed
but the process from a previous load is still alive. It will NOT auto-start on reboot.

## How to Check

### 1. Systemd state vs running processes

```bash
# List all tracked user services
systemctl --user list-units --type=service | grep -v 'not-found'

# Check a specific service for orphan state
systemctl --user status <service-name> 2>&1 | grep -E 'Loaded:|Active:'

# Find services that are loaded: not-found but still active
systemctl --user list-units --type=service --all 2>/dev/null | grep 'not-found'
```

### 2. Port-to-PID mapping

Cross-reference systemd state with actual listening processes:

```bash
# See which python processes serve which ports
ss -tlnp | grep python3

# Output format:
# LISTEN 0 2048 127.0.0.1:8904 0.0.0.0:* users:(("python3",pid=3917624,fd=14))
#              ^---port         ^---PID
```

### 3. Match PID to systemd unit

```bash
# Check which unit a PID belongs to
systemctl --user status <PID> 2>&1 | head -3
# Or check the process's cgroup
cat /proc/<PID>/cgroup 2>/dev/null
```

## What to Do When Found

**If the unit file exists elsewhere** (e.g., in the repo at one of the expected paths):
```bash
cp /path/to/repo/<service>.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user restart <service>
```

**If the unit file is gone from the repo too** (service was intentionally removed):
- Stop the orphan cleanly: `systemctl --user stop <service>`
- Or recreate the unit from the installer if the service is still needed

## Pitfalls

- **Don't restart blindly** — restarting an orphan service when the unit file is missing will fail. Check `Loaded:` line first.
- **`systemctl --user list-units` won't show orphans by default** — use `--all` to see not-found units.
- **Process may be unmanaged** — if `systemctl --user status <PID>` shows no matching unit, the process was started manually, not via systemd.
