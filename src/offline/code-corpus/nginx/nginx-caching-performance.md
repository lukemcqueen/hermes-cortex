---
language: nginx
tags: [nginx, caching, performance, gzip, rate-limiting, web]
title: Nginx Caching & Performance
description: Proxy caching, gzip compression, expires headers, client_max_body_size, and rate limiting for performance tuning
source: pattern
---

```nginx
# ── Cache zone definition ──────────────────────────────────────────────
# Path on disk, max 1 GB, keys expire after 1 day of inactivity
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=mycache:10m
                 max_size=1g inactive=24h use_temp_path=off;

# ── Rate-limiting zones ────────────────────────────────────────────────
# Zone 'api_limit': 10 MB shared memory, 10 requests/sec per IP
limit_req_zone  $binary_remote_addr zone=api_limit:10m rate=10r/s;

# Zone 'login_limit': 5 MB, 1 request/sec per IP (stricter for auth)
limit_req_zone  $binary_remote_addr zone=login_limit:5m  rate=1r/s;

# Zone 'conn_limit': limit concurrent connections per IP
limit_conn_zone $binary_remote_addr zone=conn_limit:10m;

# ── Gzip compression ───────────────────────────────────────────────────
gzip              on;
gzip_vary         on;
gzip_proxied      any;
gzip_comp_level   5;               # 1-9, 5 offers good ratio/speed trade-off
gzip_min_length   256;             # Don't compress tiny responses
gzip_types
    text/plain
    text/css
    text/xml
    text/javascript
    application/json
    application/javascript
    application/xml
    application/rss+xml
    application/atom+xml
    image/svg+xml
    font/woff
    font/woff2;

# ── Server block ───────────────────────────────────────────────────────
server {
    listen 80;
    server_name example.com;

    client_max_body_size 10m;      # Max upload size (default 1m)

    # ── Static files with far-future expires ───────────────────────────
    location /static/ {
        root   /var/www/html;
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;            # No need to log static asset hits
    }

    # ── API proxy with caching ─────────────────────────────────────────
    location /api/ {
        proxy_pass http://backend:3000;

        # Use cache zone; cache 200/301/302 for 5 minutes
        proxy_cache         mycache;
        proxy_cache_key     $scheme$proxy_host$request_uri;
        proxy_cache_valid   200 301 302 5m;
        proxy_cache_valid   404              1m;
        proxy_cache_use_stale error timeout updating http_500 http_502 http_503;

        # Bypass cache for authenticated requests
        proxy_cache_bypass  $http_authorization;
        proxy_no_cache      $http_authorization;

        # Standard headers
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Pass cache status header for debugging
        add_header X-Cache-Status $upstream_cache_status;
    }

    # ── Rate-limited auth/login endpoint ───────────────────────────────
    location /auth/login {
        proxy_pass http://backend:3000;

        # Burst of 5, then queue excess with nodelay
        limit_req zone=login_limit burst=5 nodelay;

        # Limit concurrent connections
        limit_conn conn_limit 5;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    }

    # ── General proxy with rate limiting ───────────────────────────────
    location / {
        proxy_pass http://backend:3000;

        # Burst of 20 requests then delay
        limit_req zone=api_limit burst=20 nodelay;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```