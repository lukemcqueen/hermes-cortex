# Hermes Cortex — Security Hardening Reference

Commands and patterns for hardening a Hermes Cortex installation on macOS.

## Permission Audit

Files in `~/.hermes/` that default to world-readable and should be 0600:

| File | Risk | Why |
|------|------|-----|
| `config.yaml` | API base URLs, provider config, internal paths | Credential metadata |
| `.hermes_history` | Conversation titles, session metadata | Privacy |
| `kanban.db` | Project/task content | Data exposure |
| `SOUL.md` | Agent personality/identity overrides | System prompt config |
| `gateway.lock` / `gateway.pid` | Runtime state | Low risk but lock early |
| `interrupt_debug.log` | Runtime output | Potential path/URL leakage |
| `config.yaml.bak.*` | Old config snapshots | Credential metadata |

**One-liner lockdown:**
```bash
chmod 600 ~/.hermes/config.yaml ~/.hermes/.hermes_history ~/.hermes/kanban.db ~/.hermes/SOUL.md ~/.hermes/interrupt_debug.log ~/.hermes/gateway.lock ~/.hermes/gateway.pid ~/.hermes/auth.json
for f in ~/.hermes/config.yaml.bak.*; do chmod 600 "$f" 2>/dev/null; done
```

**Quick verify:**
```bash
cd ~/.hermes
for f in config.yaml .hermes_history kanban.db SOUL.md auth.json .env interrupt_debug.log gateway.lock gateway.pid; do
  perm=$(stat -f "%Lp" "$f" 2>/dev/null)
  [ "$perm" = "600" ] && echo "✅ $f" || echo "❌ $f ($perm)"
done
```

## Bind Address Audit

Check every listening port for public exposure:

```bash
lsof -iTCP -sTCP:LISTEN -P -n 2>/dev/null | awk 'NR>1{print $1, $9}' | grep -v "127.0.0.1\|::1" | sort -u
```

Clean output means no user services are exposed. macOS system services that are safe to ignore:
- `ControlCe` — AirDrop/Handoff/Continuity (always `*:port`)
- `com.docke` — Docker Desktop internal ports (`*:port`) — Docker Desktop's own management plane, not user containers
- `rapportd` — Apple Remote Desktop / AirDrop helper

If a Cortex service appears (e.g. `Python *:8901`), it's binding to 0.0.0.0. Fix:
- **Flask**: `app.run(host="127.0.0.1", ...)` in the server code
- **Ollama**: `OLLAMA_HOST=127.0.0.1` in its launchd plist EnvironmentVariables
- **Docker port mappings**: In docker-compose.yml, use `127.0.0.1:3001:3000` not `3001:3000`

## nginx Local-Only Unload

nginx is installed as part of the Hermes Cortex stack for TLS reverse proxy. On local-only setups it should be unloaded to avoid log permission errors:

**Symptom:** `brew services list` shows nginx as `error`, or `nginx -t` fails with:
```
nginx: [emerg] open() "/opt/homebrew/var/log/nginx/access.log" failed (13: Permission denied)
```

The log files are owned by `root:admin` but nginx runs as user. **Fix — unload if not needed:**
```bash
launchctl unload ~/Library/LaunchAgents/homebrew.mxcl.nginx.plist
brew services stop nginx
```

**If external access is later needed, fix logs first:**
```bash
sudo chown "$(whoami):staff" /opt/homebrew/var/log/nginx/*.log
brew services start nginx
```

## macOS Firewall

Check if the built-in firewall is active:
```bash
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
```

Expected: `Firewall is enabled. (State = 1)`

## Restart Resilience

### Launchd Services

```bash
launchctl list | grep -E "(ollama|mycortex|cortex|hermes|docker)"
```

Required services (all should show a PID, not `-`):

| Label | Purpose | plist |
|-------|---------|-------|
| `com.ollama.serve` | Ollama LLM server | `~/Library/LaunchAgents/com.ollama.serve.plist` |
| `com.legacy-brain.sync-watch` | legacy auto-sync daemon | `~/Library/LaunchAgents/com.legacy-brain.sync-watch.plist` |
| `com.hermes.cortex-dashboard` | Cortex companion dashboard | `~/Library/LaunchAgents/com.hermes.cortex-dashboard.plist` |
| `ai.hermes.gateway` | Hermes messaging gateway | `~/Library/LaunchAgents/ai.hermes.gateway.plist` |
| `com.docker.docker` | Docker Desktop (triggers container restart) | `~/Library/LaunchAgents/com.docker.docker.plist` |

Each plist must have `<key>RunAtLoad</key><true/>` to auto-start on boot.

### Docker Container Restart Policies

Verify all Cortex containers survive Docker Desktop restart:

```bash
for c in $(docker ps -a -q); do
  name=$(docker inspect "$c" --format '{{.Name}}')
  policy=$(docker inspect "$c" --format '{{.HostConfig.RestartPolicy.Name}}')
  echo "$name → $policy"
done
```

Expected policies:
- Langfuse stack (`langfuse-*`) → `always`
- Project containers (`echokorean-*`, `acme-*`) → `always` or `unless-stopped`

Containers with `no` restart policy will NOT survive reboot and must be started manually.

## SSH Keys

```bash
ls -la ~/.ssh/
```

All private keys should be 0600 (`-rw-------`). Public keys (`.pub` files) can be 0644. If any private key is world-readable:

```bash
chmod 600 ~/.ssh/id_rsa ~/.ssh/id_ed25519 ~/.ssh/github ~/.ssh/gitlab
```

## Full Audit One-Liner

```bash
echo "=== File Permissions ===" && \
stat -f "%Lp %N" ~/.hermes/config.yaml ~/.hermes/.env ~/.hermes/.hermes_history ~/.hermes/kanban.db ~/.hermes/SOUL.md ~/.hermes/auth.json ~/.hermes/gateway_state.json && \
echo "=== Bind Audit ===" && \
lsof -iTCP -sTCP:LISTEN -P -n 2>/dev/null | awk 'NR>1{print $1, $9}' | grep -v "127.0.0.1\|::1" | sort -u && \
echo "=== Firewall ===" && \
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate && \
echo "=== Launchd Services ===" && \
launchctl list | grep -E "(ollama|mycortex|cortex|hermes|docker)" && \
echo "=== Docker Restart Policies ===" && \
for c in $(docker ps -a -q); do docker inspect "$c" --format '{{.Name}} {{.HostConfig.RestartPolicy.Name}}'; done 2>/dev/null && \
echo "=== SSH Keys ===" && \
ls -la ~/.ssh/ 2>/dev/null
```
