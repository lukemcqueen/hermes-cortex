---
language: nginx
tags: [nginx, static, http-server, files, web]
title: Nginx Static File Server
description: Serving static assets with root, index, try_files, directory listing, charset, logging, and security hardening
source: pattern
---

```nginx
server {
    listen 80;
    server_name static.example.com;

    # ── Document root ──────────────────────────────────────────────────
    root /var/www/static;
    index index.html index.htm;

    # ── Character set ──────────────────────────────────────────────────
    charset utf-8;

    # ── Logging ────────────────────────────────────────────────────────
    access_log /var/log/nginx/static-access.log combined buffer=32k flush=5s;
    error_log  /var/log/nginx/static-error.log  warn;

    # ── Server tokens off ──────────────────────────────────────────────
    server_tokens off;

    # ── Default: try_files ─────────────────────────────────────────────
    # Serves the actual file; if not found, tries the file + trailing slash
    # (to trigger index), then falls back to a 404.
    location / {
        try_files $uri $uri/ /404.html;
    }

    # ── Custom error pages ─────────────────────────────────────────────
    error_page 404 /404.html;
    error_page 500 502 503 504 /50x.html;

    location = /404.html {
        internal;    # Only accessible via error_page redirect
    }

    location = /50x.html {
        internal;
    }

    # ── Explicit file type handling with expires ───────────────────────
    location ~* \.(css|js)$ {
        expires 1M;                    # Cache for 1 month
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    location ~* \.(jpg|jpeg|png|gif|ico|webp|avif|svg)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    location ~* \.(woff|woff2|ttf|otf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # ── Directory listing (opt-in, disabled by default) ────────────────
    location /files/ {
        alias /var/www/static/files/;
        autoindex on;                  # Shows file list when no index file
        autoindex_exact_size off;      # Human-friendly sizes (KB/MB/GB)
        autoindex_localtime on;        # Use server local time

        # Basic auth to protect directory listing
        auth_basic           "Restricted Files";
        auth_basic_user_file /etc/nginx/.htpasswd;

        # Limit to read-only methods
        limit_except GET {
            deny all;
        }
    }

    # ── Deny access to hidden files ────────────────────────────────────
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }

    # ── Security headers for static content ────────────────────────────
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options       "DENY"    always;
    add_header Referrer-Policy       "strict-origin-when-cross-origin" always;
}
```