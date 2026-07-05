# A2A Deployment Notes

## Sudo Commands Required

After pulling the latest `hermes-cortex`, run these commands to activate
the A2A server and nginx routes on **Joseph's server** (user: luke).

### 1. Deploy nginx config (adds A2A upstream backends)

```bash
# Run cortex-update to ensure templates are current
bash ~/hermes-cortex/src/scripts/cortex-update.sh
```

### 2. Create systemd service for A2A server

```bash
# Copy the service template
sudo cp ~/hermes-cortex/docs/templates/a2a-server.service /etc/systemd/system/a2a-server.service

# Replace placeholders for joseph/luke
sudo sed -i "s|__USER__|luke|g; s|__HERMES_VENV__|/home/luke/.hermes/hermes-agent/venv|g; s|__CORTEX_REPO__|/home/luke/hermes-cortex|g; s|__INBOX_DIR__|/home/luke/hermes-cortex-private/messages/inbox|g; s|__CORTEX_HOME__|/home/luke|g" /etc/systemd/system/a2a-server.service

# Reload, enable, start
sudo systemctl daemon-reload
sudo systemctl enable a2a-server
sudo systemctl start a2a-server
sudo systemctl status a2a-server
```

### 3. Add A2A upstream + nginx location block

```bash
# Open hermes-services.conf for editing
sudo nano /etc/nginx/sites-enabled/hermes-services.conf
```

Add this section after the health server block (at the end of the file):

```nginx
# ── A2A Upstream ──
upstream a2a_backend {
    server 127.0.0.1:8906;
}

# ── A2A Server — port 13006 (local, non-SSL) ──
server {
    listen 127.0.0.1:13006;
    server_name localhost;

    auth_basic "Hermes Cortex — A2A";
    auth_basic_user_file /etc/nginx/.htpasswd;

    client_max_body_size 10m;
    client_body_timeout 30s;
    client_header_timeout 30s;
    send_timeout 30s;
    keepalive_timeout 65s;

    add_header X-Content-Type-Options    "nosniff" always;
    add_header X-Frame-Options           "DENY" always;
    add_header X-XSS-Protection          "0" always;
    add_header Referrer-Policy           "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy        "camera=(), microphone=(), geolocation=()" always;
    add_header Content-Security-Policy   $csp_header always;
    add_header Cache-Control             "no-store, max-age=0" always;
    proxy_hide_header Server;
    add_header Server "Hermes" always;
    if ($block_direct_ip) { return 444; }

    access_log  /var/log/nginx/a2a-access.log;
    error_log   /var/log/nginx/a2a-error.log;
    limit_conn conn_limit 10;

    location ~ /\.(git|env|svn|hg|idea|vscode|DS_Store|htpasswd) {
        deny all; return 404;
    }

    location / {
        limit_req zone=general burst=40 nodelay;
        limit_req zone=auth burst=10 nodelay;
        proxy_pass http://a2a_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Then reload:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 4. Test through nginx

```bash
# Health check (direct)
curl -s http://127.0.0.1:8906/health
# Expected: {"status":"ok","service":"a2a-server","agent":"joseph"}

# Through nginx
curl -s http://127.0.0.1:13006/health
# Expected: {"status":"ok",...}

# Agent Card
curl -s http://127.0.0.1:8906/a2a/agent-card
# Expected: Agent Card JSON
```

### 5. Test task submission

```bash
# Submit a task:
curl -s -X POST http://127.0.0.1:8906/a2a/task \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tasks/send","params":{"task":{"state":"submitted","messages":[{"role":"user","parts":[{"type":"text","text":"Hello A2A world from Joseph"}]}]}}}'
# Expected: task ID returned

# Poll the task:
curl -s http://127.0.0.1:8906/a2a/task/<TASK_ID>
# Expected: current state
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
