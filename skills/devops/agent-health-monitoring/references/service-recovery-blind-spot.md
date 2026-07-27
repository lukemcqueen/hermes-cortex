# Service-Recovery Blind Spot

## The Problem

The `service-recovery.py` script runs every 5 minutes and auto-restarts
critical services — but it only knows about services in its `SERVICES` list.
If you deploy a new critical service (like the health-server) and forget
to add it to that list, any crash or SIGTERM leaves it dead until a human
notices.

**Real incident (Jul 2026):** `com.hermes.health-server` received a SIGTERM
and exited cleanly after 2 days of uptime. The nginx proxy returned 502s for
44 minutes. Root cause wasn't a crash — the service wasn't in the recovery list.

## Prevention

### When deploying a new service (checklist)

1. Create the systemd service (or launchd plist).
2. Enable + start it.
3. **Verify the service is in `service-recovery.py`'s `SERVICES` list.**
4. If not, add it:
   ```python
   _make_service("<short-name>", label="<systemd-unit-name>", pgrep="<pgrep-pattern>"),
   ```
5. Patch both the deployed copy AND the repo source.
6. Verify: `systemctl --user stop <service>` should be auto-restored by
   `service-recovery` within 5 minutes.

### Example entry

For the health-server (systemd user service):
```python
_make_service("health-server", label="com.hermes.health-server", pgrep="health-server"),
```

### How to check if a service is in the recovery list

```bash
grep '_make_service' ~/.hermes-cortex/scripts/service-recovery.py
```

Each `_make_service` call is one monitored service. Missing = not monitored.

### How `service-recovery.py` decides to restart

```python
SERVICES: list[dict] = [
    _make_service("nginx", ...),
    _make_service("Ollama", ...),
    _make_service("gbrain", ...),
    # ... add new ones here
]
```

On every tick (5 min), it iterates `SERVICES`, checks if each is running,
and restarts any that aren't. Services NOT in this list are invisible.
