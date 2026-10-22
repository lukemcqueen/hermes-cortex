# Agent Bus False-Positive Detection

## The Problem

The `remediation-sensor.py` checks for a single hardcoded service name and port:
- Service: `hermes-agent-bus.service` (Linux) / `com.hermes.agent-bus` (macOS)
- Port: `:8905`

But the actual bus can use different names and ports depending on the deployment configuration.

**Discovered:** 2026-07-17 — this deployment had the bus running as `agent-bus.service` on port `:8903`, causing a persistent false-positive "Agent Bus down" alert on every sensor cycle.

## How the Bus Is Actually Configured

| Deployment | Service name | Port | 
|------------|-------------|------|
| Esther (this node) | `agent-bus.service` | `:8903` |
| Canonical default | `hermes-agent-bus.service` | `:8905` |

The bus server is declared in the systemd service unit's `ExecStart`. To find the actual port:
```bash
systemctl --user show <service-name> | grep ExecStart
```

## Detection Procedure (for Auto-Remediation)

Do NOT trust the sensor's "down" verdict alone. Instead:

```bash
# 1. Find all bus-related services
systemctl --user list-units --all --type=service 2>&1 | grep -i bus

# 2. Check if any is active
systemctl --user is-active <found-service>

# 3. Find the port it listens on
ss -tlnp | grep 89

# 4. Verify health
curl -s http://127.0.0.1:<port>/health
```

Expected health response: `{"status":"ok","backend":"pgmq","queues":N,...}`

## Fix

```bash
systemctl --user restart <found-service>
```

## Related

- `agent-bus` skill — full queue inspection, DLQ management, and bus diagnostics
- `references/cortex-inbox-url.md` — `CORTEX_INBOX_URL` points to nginx proxy, not the local bus port
