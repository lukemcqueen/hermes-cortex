---
language: nginx
tags: [nginx, security, headers, cors, csp, web]
title: Nginx Security Headers
description: Hardening response headers — Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, CORS, Referrer-Policy, Permissions-Policy
source: pattern
---

```nginx
server {
    listen 80;
    server_name example.com;

    # ── Content Security Policy ─────────────────────────────────────────
    # Restrict resources to same-origin + trusted CDNs. Adjust as needed.
    add_header Content-Security-Policy "
        default-src 'self';
        script-src  'self' https://cdnjs.cloudflare.com 'unsafe-inline';
        style-src   'self' https://cdnjs.cloudflare.com 'unsafe-inline';
        img-src     'self' data: https://images.example.com;
        font-src    'self' https://fonts.gstatic.com;
        connect-src 'self' https://api.example.com;
        frame-ancestors 'none';
        base-uri    'self';
        form-action 'self';
    " always;

    # ── Clickjacking protection ─────────────────────────────────────────
    add_header X-Frame-Options "DENY" always;

    # ── Prevent MIME-type sniffing ──────────────────────────────────────
    add_header X-Content-Type-Options "nosniff" always;

    # ── Cross-Origin Resource Sharing (CORS) ────────────────────────────
    # Apply only to API locations that need cross-origin access.
    # Using a map to conditionally send CORS headers is preferred.

    # ── Referrer policy ─────────────────────────────────────────────────
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # ── Permissions policy (was Feature-Policy) ─────────────────────────
    # Disable unnecessary browser features
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=()" always;

    # ── Cache-busting for sensitive responses ───────────────────────────
    add_header Cache-Control "no-store, no-cache, must-revalidate" always;

    # ── Remove server version banner ────────────────────────────────────
    server_tokens off;

    location /api/ {
        proxy_pass http://backend:3000;

        # Conditional CORS for API endpoints
        add_header Access-Control-Allow-Origin  "https://app.example.com" always;
        add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Authorization, Content-Type, Accept" always;
        add_header Access-Control-Allow-Credentials "true" always;
        add_header Access-Control-Max-Age       "86400" always;

        # Handle preflight (OPTIONS) requests
        if ($request_method = OPTIONS) {
            add_header Content-Length 0;
            add_header Content-Type text/plain;
            return 204;
        }

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        root   /var/www/html;
        index  index.html;
    }
}
```