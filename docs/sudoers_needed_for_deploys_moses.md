# nginx — called by crons
moses ALL=(root) NOPASSWD: /usr/sbin/nginx -t
moses ALL=(root) NOPASSWD: /usr/sbin/nginx -s reload
moses ALL=(root) NOPASSWD: /usr/bin/systemctl reload nginx
moses ALL=(root) NOPASSWD: /usr/bin/systemctl start nginx
moses ALL=(root) NOPASSWD: /usr/bin/systemctl stop nginx
moses ALL=(root) NOPASSWD: /usr/bin/systemctl restart nginx

# blocked IP deploy — tight single path
moses ALL=(root) NOPASSWD: /bin/cp /tmp/blocked_ips.conf.new /etc/nginx/blocked_ips.conf

# htpasswd deploy
moses ALL=(root) NOPASSWD: /usr/bin/cp /tmp/hermes-htpasswd /etc/nginx/.hermes-htpasswd

# apt cleanup — called by system-alert-watchdog
moses ALL=(root) NOPASSWD: /usr/bin/apt autoremove --purge -y
moses ALL=(root) NOPASSWD: /usr/bin/apt clean

# swap-refresh — called by daily swap-refresh cron
moses ALL=(root) NOPASSWD: /sbin/swapoff, /sbin/swapon

# fail2ban — read-only monitoring
moses ALL=(root) NOPASSWD: /usr/bin/fail2ban-client status

# certbot — automated renewal
moses ALL=(root) NOPASSWD: /usr/bin/certbot renew --non-interactive
moses ALL=(root) NOPASSWD: /usr/bin/certbot certificates

# troubeshooting - read-only
moses ALL=(root) NOPASSWD: /bin/journalctl -u vsftpd *
moses ALL=(root) NOPASSWD: /bin/cat /var/log/vsftpd.log
moses ALL=(root) NOPASSWD: /bin/cat /etc/vsftpd.conf