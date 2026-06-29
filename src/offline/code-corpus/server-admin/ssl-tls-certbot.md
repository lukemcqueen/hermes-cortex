---
language: shell
tags: [ssl, tls, certbot, letsencrypt, nginx, certificates]
title: SSL/TLS with Certbot and Let's Encrypt
description: Certificate generation, auto-renewal, and nginx integration for free Let's Encrypt SSL/TLS certificates
source: pattern
---

```bash
# ── 1. Install certbot and nginx plugin ──
apt update && apt install -y certbot python3-certbot-nginx
# On RHEL/Fedora: dnf install certbot python3-certbot-nginx

# ── 2. Obtain certificate (standalone mode) ──
# Stop any service on port 80 first, then run:
certbot certonly --standalone -d example.com -d www.example.com \
  --non-interactive --agree-tos -m admin@example.com

# ── 3. Obtain certificate (nginx plugin — preferred) ──
# Requires a working nginx server block for the domain
certbot --nginx -d example.com -d www.example.com \
  --non-interactive --agree-tos -m admin@example.com

# ── 4. Verify certificate files ──
ls -la /etc/letsencrypt/live/example.com/
# Expected:
#   cert.pem       -> ../../archive/example.com/cert1.pem       (server cert only)
#   chain.pem      -> ../../archive/example.com/chain1.pem      (intermediates)
#   fullchain.pem  -> ../../archive/example.com/fullchain1.pem  (cert + chain)
#   privkey.pem    -> ../../archive/example.com/privkey1.pem    (private key)

# ── 5. nginx server block with SSL ──
cat > /etc/nginx/sites-available/example.com << 'EOF'
server {
    listen 443 ssl http2;
    server_name example.com www.example.com;

    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 10m;

    # HSTS (uncomment after confirming SSL works)
    # add_header Strict-Transport-Security "max-age=63072000; includeSubDomains" always;

    root /var/www/example.com;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
    }
}

# Redirect HTTP -> HTTPS
server {
    listen 80;
    server_name example.com www.example.com;
    return 301 https://$server_name$request_uri;
}
EOF

ln -s /etc/nginx/sites-available/example.com /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# ── 6. Auto-renewal (certbot timer) ──
# certbot installs a systemd timer by default; verify it:
systemctl list-timers | grep certbot
# Or check the cron job:
grep certbot /etc/crontab /etc/cron.d/* 2>/dev/null

# Manual renewal test (dry-run):
certbot renew --dry-run

# ── 7. Post-renewal hook (reload nginx after renewal) ──
cat > /etc/letsencrypt/renewal-hooks/post/nginx-reload.sh << 'EOF'
#!/bin/bash
systemctl reload nginx || nginx -s reload
EOF
chmod +x /etc/letsencrypt/renewal-hooks/post/nginx-reload.sh

# Test renewal hook
certbot renew --dry-run --post-hook "/etc/letsencrypt/renewal-hooks/post/nginx-reload.sh"

# ── 8. Verify SSL configuration ──
# Online:    https://www.ssllabs.com/ssltest/
# CLI:       openssl s_client -connect example.com:443 -tls1_3
# Expiry:    echo | openssl s_client -servername example.com \
#            -connect example.com:443 2>/dev/null | openssl x509 -noout -dates
```