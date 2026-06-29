---
language: nginx
tags: [nginx, proxy, web, networking]
title: Nginx Reverse Proxy
description: Location blocks, proxy_pass, proxy_set_header, and upstream definition for proxying requests to backend services
source: pattern
---

```nginx
# Upstream backend definition — load balances across multiple app servers
upstream backend_cluster {
    server app1.internal:3000 weight=3;
    server app2.internal:3000 weight=2;
    server app3.internal:3000 backup;
}

# Main server block
server {
    listen 80;
    server_name api.example.com;

    # Strip the /api/ prefix and proxy to the backend
    location /api/ {
        proxy_pass http://backend_cluster/;

        # Forward essential headers to the backend
        proxy_set_header Host                  $host;
        proxy_set_header X-Real-IP             $remote_addr;
        proxy_set_header X-Forwarded-For       $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto     $scheme;

        # Increase buffer sizes for large requests
        proxy_buffer_size          4k;
        proxy_buffers              8 4k;
        proxy_busy_buffers_size    8k;

        # Timeouts
        proxy_connect_timeout      30s;
        proxy_send_timeout         60s;
        proxy_read_timeout         60s;
    }

    # Proxy WebSocket connections (no upgrade header rewriting needed)
    location /ws/ {
        proxy_pass http://backend_cluster;
        proxy_http_version 1.1;
        proxy_set_header Upgrade          $http_upgrade;
        proxy_set_header Connection       "upgrade";
        proxy_set_header Host             $host;
        proxy_set_header X-Real-IP        $remote_addr;

        proxy_read_timeout 86400s;  # Long timeout for persistent WS connections
    }

    # Pass through non-API routes as-is
    location / {
        proxy_pass http://backend_cluster;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```