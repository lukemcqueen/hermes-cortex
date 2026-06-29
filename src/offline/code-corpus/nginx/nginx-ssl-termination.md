---
language: nginx
tags: [nginx, ssl, tls, https, security, web]
title: Nginx SSL Termination
description: HTTPS server block with SSL certificates, secure protocols, ciphers, HSTS, and HTTP→HTTPS redirect
source: pattern
---

```nginx
# Redirect all HTTP traffic to HTTPS
server {
    listen 80;
    server_name example.com www.example.com;
    return 301 https://$host$request_uri;
}

# HTTPS server block
server {
    listen 443 ssl http2;
    server_name example.com www.example.com;

    # Certificate paths (Let's Encrypt / certbot convention)
    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    # TLS protocol versions — disable obsolete SSLv3, TLSv1, TLSv1.1
    ssl_protocols TLSv1.2 TLSv1.3;

    # Strong cipher suites (modern, PFS-enabled)
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;

    # Prefer server cipher order over client
    ssl_prefer_server_ciphers on;

    # Optimise TLS session caching
    ssl_session_cache    shared:SSL:10m;
    ssl_session_timeout  1h;
    ssl_session_tickets  off;

    # Diffie-Hellman parameters (generate: openssl dhparam -out /etc/nginx/dhparam.pem 2048)
    ssl_dhparam /etc/nginx/dhparam.pem;

    # OCSP Stapling — improves TLS handshake performance
    ssl_stapling       on;
    ssl_stapling_verify on;
    resolver           1.1.1.1 8.8.8.8 valid=300s;
    resolver_timeout   5s;

    # HTTP Strict Transport Security (HSTS) — tell browsers to always use HTTPS
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

    # Application root
    location / {
        proxy_pass http://backend:3000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```