---
name: nginx-web-app-deployment
description: "Deploy a custom web app (Flask, Python, Node) behind nginx — upstream config, SSL, basic auth, rate limiting, launchd/systemd service, and multi-layer testing pattern."
version: 1.0.0
author: Hermes Cortex
platforms: [macos, linux]
---

# Nginx Web App Deployment

Deploy a custom web app behind a Hermes-style nginx stack with SSL, basic auth, rate limiting, and auto-restart.

## Step 1 — Choose Port

Recommended port convention for Hermes-style setups:

| Service | Port | Purpose |
|---------|------|---------|
| App 1 | 13001 | First service |
| App 2 | 13002 | Second service |
| App 3 | 13003 | Third service |
| _(next)_ | 13004+ | — |

Internal (app) ports are typically in the 5000-9000 range. External (nginx) ports are 13001+.

## Step 2 — Write the App

Standard Flask app pattern:

```python
app.run(host="127.0.0.1", port=5001)
```

Keep it listening on 127.0.0.1 only — nginx handles external access.

## Step 3 — Create the Service

### macOS (launchd)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.hermes.APPNAME</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/venv/bin/gunicorn</string>
        <string>-w</string><string>2</string>
        <string>-b</string><string>127.0.0.1:INTERNAL_PORT</string>
        <string>app:app</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/app</string>
    <key>KeepAlive</key>
    <true/>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/path/to/logs/app.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/logs/app.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/path/to/venv/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.hermes.APPNAME.plist
```

### Linux (systemd user service)

```ini
[Unit]
Description=APPNAME
After=network.target

[Service]
WorkingDirectory=/opt/APPNAME
ExecStart=/opt/APPNAME/venv/bin/gunicorn -w 2 -b 127.0.0.1:INTERNAL_PORT app:app
Restart=always
Environment=PATH=/opt/APPNAME/venv/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now APPNAME
```

## Step 4 — nginx Config

Add to your nginx sites config:

```nginx
upstream APPNAME_backend {
    server 127.0.0.1:INTERNAL_PORT;
}

server {
    listen EXTERNAL_PORT ssl;
    server_name YOUR_DOMAIN localhost;

    ssl_certificate     /path/to/ssl/YOUR_DOMAIN/fullchain.pem;
    ssl_certificate_key /path/to/ssl/YOUR_DOMAIN/privkey.pem;

    access_log  /var/log/nginx/APPNAME-access.log;
    error_log   /var/log/nginx/APPNAME-error.log;

    auth_basic "APPNAME";
    auth_basic_user_file /path/to/.htpasswd;

    limit_conn conn_limit 10;

    location / {
        limit_req zone=general burst=40 nodelay;
        limit_req zone=auth burst=10 nodelay;

        proxy_pass http://APPNAME_backend;
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

### CRITICAL — Single Listener Rule

⚠️ **NEVER add a second `listen` directive on the same port.** Each server block must have exactly ONE `listen` line:

```nginx
# ✅ CORRECT — single SSL listener
listen 13003 ssl;

# ❌ WRONG — this creates a plain HTTP listener that intercepts TLS handshakes → 400 error
listen 13003 ssl;
listen 127.0.0.1:13003;
```

The plain listener catches TLS connections first, reads the encrypted handshake as HTTP, and returns a 400 Bad Request. The `listen PORT ssl;` directive already binds all interfaces.

## Step 5 — Verify Config & Reload

```bash
nginx -t && nginx -s reload
```

## Step 6 — Multi-Layer Testing (MANDATORY)

Test EVERY layer before declaring the deployment done:

```bash
# Layer 1: Internal (app directly)
curl -s -o /dev/null -w "Layer 1: %{http_code}\n" http://127.0.0.1:INTERNAL_PORT/

# Layer 2: nginx proxy
curl -s -o /dev/null -w "Layer 2: %{http_code}\n" http://127.0.0.1:EXTERNAL_PORT/
```

### Write an automated test suite

Create `test_api.py` that covers:

1. ✅ App is reachable (internal port)
2. ✅ nginx proxy returns 401 (basic auth challenge)
3. ✅ No active sessions initially
4. ✅ Start a session → returns 200, active=true
5. ✅ Multi-user isolation
6. ✅ Second start auto-stops first session
7. ✅ Stop → returns duration, active=false
8. ✅ Today endpoint returns structured data
9. ✅ Week endpoint returns expected shape
10. ✅ Error handling (invalid input → 400, stop with no active → 400)

**Key rule:** Test the endpoint the same way the user will access it. Testing only the internal port is not sufficient.

```bash
# Run the test suite
venv/bin/python test_api.py
```

## PITFALLS

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Dual listener on same port | 400 Bad Request, nginx log shows garbled bytes | Remove plain listener, keep only `listen PORT ssl;` |
| Server name mismatch | SSL cert warnings in browser | Use `YOUR_DOMAIN localhost` in server_name directive |
| nginx not reloaded after config change | Old config still serving | Always run `nginx -t && nginx -s reload` |
| Gunicorn binding to 0.0.0.0 | App accessible without auth | Bind gunicorn to `127.0.0.1` only |
| launchd PATH missing | Gunicorn not found | Set `EnvironmentVariables:PATH` in plist |
| No automated test suite | Regression goes unnoticed | Write test_api.py before declaring done |
