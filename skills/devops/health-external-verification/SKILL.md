---
name: health-external-verification
description: Verify your health endpoint is externally reachable by testing the URL end-to-end instead of assuming local-only based on process checks.
---

# Health External Verification

Never assume "local-only" — test the external URL to prove you're healthy.

## When to Use

- After setting up health monitoring
- When another agent reports you as unreachable
- Before declaring yourself "healthy" in any status report
- After nginx config changes or network reconfiguration
- When asked "Is your health externally accessible?"

## Workflow

### Phase 1: Find your health URL

1. Read `~/.hermes-cortex/state/agent-registry.json`
2. Find your agent entry by name
3. Extract `health_url` if present — this is your canonical health endpoint
4. If no `health_url` is set, construct one from convention:
   - `https://<hostname>:<port>/health` or
   - `https://<domain>:<port>/<path>`

### Phase 2: Test the external URL

Test the URL that OTHER agents would use to reach you:

```bash
curl -s -w "\nHTTP_CODE=%{http_code}" --connect-timeout 10 \
  -u "user:pass" \
  "https://your-external-domain:port/path"
```

If basic auth is required, provide credentials (from config or env).

### Phase 3: Interpret the result

| HTTP Code | Meaning | Action |
|-----------|---------|--------|
| 200 | Healthy — endpoint reachable | ✅ Report success, include health data |
| 401/403 | Reachable but auth required | ✅ Still reachable — check if credentials are needed |
| 502/503 | Service behind nginx is down | 🔧 Check upstream service (health server, dashboard) |
| 000 | Connection refused / timeout | ❌ Not externally accessible — diagnose |
| 404 | Wrong path | 🔧 Fix the URL path |

### Phase 4: Diagnose failures

If the external URL is unreachable:

1. **Is nginx running?** `systemctl is-active nginx` or `pgrep nginx`
2. **Is the health server running?** Check the upstream service on its internal port
3. **Is nginx configured for external access?**
   - Check site config: `grep 'listen.*ssl\|listen.*:PORT' /etc/nginx/sites-enabled/`
   - External access typically needs `listen PORT ssl;` not `listen 127.0.0.1:PORT;`
4. **Is the port open on the firewall?** Check iptables/nftables/ufw
5. **Is the DNS correct?** `dig +short your-domain.com` should resolve to your public IP
6. **Is there router port forwarding?** For LAN hosts, external access requires router to forward the port

### Phase 5: Report the result

Include in your report:
- URL tested
- HTTP status code
- Key health fields (server, uptime, healthy flag)
- If failed: what blocked it (nginx config, firewall, DNS, etc.)

## Important Rules

1. **Always test from outside.** Checking `curl http://127.0.0.1:PORT` only proves the local process is running, not that the world can reach you.
2. **Use the external DNS name**, not the local IP. Other agents use the external URL.
3. **Don't assume.** A listening process + a running nginx does not equal external reachability.
4. **Report facts, not interpretations.** Say "HTTP 000 — connection refused" not "I'm not externally accessible" (the second is a conclusion, the first is evidence).
5. **Credentials:** If basic auth is needed, locate credentials from `~/.hermes-cortex/state/agent-registry.json` or `~/.hermes/.htpasswd` or env vars.

## Integration Points

- `agent-registry.json` — canonical source of `health_url` per agent
- nginx site configs in `/etc/nginx/sites-enabled/` — check `listen` directives
- `report-agent-health.py` — push-based health reporter script
|- `agent-health-monitor.py` — cross-server health poller (deprecated, superseded by orch-fleet-watchdog)
