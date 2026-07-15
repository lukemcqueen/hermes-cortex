# A2A Deployment Notes — OBSOLETE

> **⚠️ A2A is now merged into the Agent Bus (previously Agent Inbox).**
> As of 2026-07-05, there is no separate A2A server process.
> The standalone `docs/templates/a2a-server.service` was **deleted on 2026-07-09**. Do not recreate it.
> All A2A JSON-RPC endpoints are served by the Agent Bus on port 8905.
> See [`a2a-architecture.md`](a2a-architecture.md) for the current design.

## What Changed

| Before | After |
|--------|-------|
| Separate `a2a-server.py` on port 8906 | Merged into Agent Bus `server.py` on port 8905 |
| Separate `a2a-mcp.py` MCP server | Tools merged into `agent-bus-mcp.py` as `inbox_*` prefix |
| Systemd service `a2a-server.service` | Not needed — Agent Bus handles A2A |
| nginx upstream `a2a_backend` | Routes to existing `agent_bus_backend` |

## Migration (if upgrading from standalone A2A)

1. Stop the old A2A server: `kill $(lsof -t -i:8906)`
2. Remove the systemd service: `sudo systemctl disable --now a2a-server; sudo rm /etc/systemd/system/a2a-server.service`
3. Update inbox server: `cp ops/services/agent-bus/server.py ~/.hermes-cortex/agent-bus/server.py`
4. Update MCP server: `cp runtime/mcp-servers/agent-bus-mcp.py ~/.hermes/scripts/agent-bus-mcp.py`
5. Disable old A2A MCP in `~/.hermes/config.yaml`: set `a2a-bridge.enabled: false`
6. Restart inbox server
7. All A2A endpoints are now at `/a2a/*` on the same port (8903)

## Testing

```bash
# Test A2A endpoint on the merged server:
curl -s http://127.0.0.1:8903/a2a/task/invalid
# Expected: {"jsonrpc":"2.0","error":{"code":-32000,"message":"Task not found: invalid"}}

# Test through nginx gateway:
curl -s https://your-domain.com:13004/a2a/task/invalid
# Expected: same error (if nginx routes /a2a/* to agent_inbox_backend)
```

## nginx Routing

Add this to your nginx config to route `/a2a/*` through the same upstream:

```nginx
upstream agent_inbox_backend {
    server 127.0.0.1:8903;
}

server {
    listen 13004 ssl;
    ssl_certificate     __SSL_CERT__;
    ssl_certificate_key __SSL_CERT_KEY__;
    ...
    location /a2a/ {
        proxy_pass http://agent_inbox_backend;
        # A2A uses JSON-RPC over POST/GET, no special config needed
    }
}
```
