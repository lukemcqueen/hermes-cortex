---
language: nginx
tags: [nginx, load-balancing, upstream, high-availability, networking]
title: Nginx Load Balancing
description: Upstream blocks with least_conn, ip_hash, round-robin, active health checks, and passive failure detection
source: pattern
---

```nginx
# ── Upstream: least_conn ────────────────────────────────────────────────
# Distributes requests to the server with fewest active connections.
# Best for long-lived or variable-latency requests (e.g., WebSockets, APIs).
upstream backend_least_conn {
    least_conn;

    server app1.internal:3000 weight=3;   # Receives ~3x traffic
    server app2.internal:3000 weight=2;
    server app3.internal:3000 weight=1;

    # Mark server as down manually (no traffic sent)
    server app4.internal:3000 down;

    # Mark as backup (only used when all primary servers are unavailable)
    server backup.internal:3000 backup;
}

# ── Upstream: ip_hash ──────────────────────────────────────────────────
# Ensures a client IP always hits the same backend (session stickiness).
# Useful for stateful apps without a shared session store.
upstream backend_ip_hash {
    ip_hash;

    server app1.internal:3000;
    server app2.internal:3000;
    server app3.internal:3000;

    # A fallback if hashing fails — requests not covered by ip_hash go here
    server backup.internal:3000 backup;
}

# ── Upstream: round-robin (default) with passive health checks ────────
# Nginx's default load-balancing method. Traffic is distributed in turn.
# Passive health checks: nginx marks a server as failed after max_fails
# within fail_timeout, then stops sending traffic for fail_timeout seconds.
upstream backend_round_robin {
    server app1.internal:3000 max_fails=3 fail_timeout=30s;
    server app2.internal:3000 max_fails=3 fail_timeout=30s;
    server app3.internal:3000 max_fails=3 fail_timeout=30s;

    # Keep idle keepalive connections to upstreams (HTTP/1.1 only)
    keepalive 32;
}

# ── Active health checks (requires nginx plus or OpenResty) ────────────
# For nginx-plus use health_check directive in the location block;
# for open-source nginx, passive checks (max_fails) are the standard approach.
# Below is the equivalent passive + optional synthetic check pattern.

server {
    listen 80;
    server_name app.example.com;

    location / {
        proxy_pass http://backend_least_conn;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # HTTP/1.1 keepalive to upstreams
        proxy_http_version 1.1;
        proxy_set_header Connection "";

        # Timeouts for fail-fast detection
        proxy_connect_timeout 5s;
        proxy_read_timeout    10s;
        proxy_send_timeout    10s;
    }

    # Optional: dedicated health-check endpoint
    location /health {
        proxy_pass http://backend_least_conn/health;
        proxy_connect_timeout 3s;
        proxy_read_timeout    5s;

        # Only allow internal health checks
        allow 10.0.0.0/8;
        allow 172.16.0.0/12;
        deny  all;
    }
}
```