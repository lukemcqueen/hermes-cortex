# A2A Deployment Notes

## Sudo Commands Required

After pulling the latest `hermes-cortex`, run these commands to activate
the A2A server and nginx routes on this machine.

### 1. Deploy nginx config

```bash
# Deploy the updated template (adds a2a_backend upstream + /a2a/ location)
bash ~/hermes-cortex/src/scripts/cortex-update.sh
```

### 2. Start the A2A server

```bash
# Create systemd service from template
sudo cp ~/hermes-cortex/docs/templates/a2a-server.service /etc/systemd/system/a2a-server.service

# Replace placeholders
sudo sed -i "s|__USER__|moses|g; s|__HERMES_VENV__|$HOME/.hermes/hermes-agent/venv|g; s|__CORTEX_REPO__|$HOME/hermes-cortex|g; s|__INBOX_DIR__|$HOME/hermes-cortex-private/messages/inbox|g; s|__CORTEX_HOME__|$HOME|g" /etc/systemd/system/a2a-server.service

# Reload, enable, start
sudo systemctl daemon-reload
sudo systemctl enable a2a-server
sudo systemctl start a2a-server
sudo systemctl status a2a-server
```

### 3. Test the A2A endpoint

```bash
# After nginx reloads, test the A2A endpoint through the gateway:
curl -s https://bus.example.org:13004/a2a/agent-card
# Expected: Agent Card JSON

# Test the health endpoint:
curl -s http://127.0.0.1:8906/health
# Expected: {"status":"ok","service":"a2a-server","agent":"moses"}
```

### 4. Test task submission

```bash
# Submit a task to yourself (loopback test):
curl -s -X POST http://127.0.0.1:8906/a2a/task \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tasks/send","params":{"task":{"state":"submitted","messages":[{"role":"user","parts":[{"type":"text","text":"Hello A2A world"}]}]}}}'
# Expected: task ID returned

# Poll the task:
curl -s http://127.0.0.1:8906/a2a/task/<TASK_ID>
# Expected: current state
```

### 5. Verify Agent Card is served publicly

```bash
curl -s https://bus.example.org:13004/.well-known/agent-card.json
# Expected: Agent Card JSON (no auth required)
```

## Cross-Server Setup (When Adding a Second Agent Server)

When connecting to Esther or another server, you'll need:

### 5. Generate per-server client certs

```bash
# On Moses' machine (has the CA key):
cd ~/.hermes-cortex/certs

# For each server:
openssl genrsa -out server-esther.key 2048
openssl req -new -key server-esther.key -out server-esther.csr \
  -subj "/CN=esther.her-server.com/O=Hermes Cortex"
openssl x509 -req -CA hermes-ca.crt -CAkey hermes-ca.key \
  -CAcreateserial -out server-esther.crt -days 365

# Deploy to the target server:
scp hermes-ca.crt server-esther.crt server-esther.key esther-server:/etc/nginx/certs/
```

### 6. Add mTLS to the nginx config on each server

```nginx
# In the 13004 server block, for the /a2a/ location:
location /a2a/ {
    ssl_verify_client on;
    ssl_client_certificate /etc/nginx/hermes-ca.crt;
    ssl_verify_depth 2;
    
    allow <peer-server-ip>;
    deny all;
    
    limit_req zone=general burst=40 nodelay;
    proxy_pass http://a2a_backend;
}
```

### 7. Add the new server to the agent registry

```bash
# Edit ~/.hermes-cortex/a2a/agent-registry.json
# Add the new agent's URL and commit the template to git
```
