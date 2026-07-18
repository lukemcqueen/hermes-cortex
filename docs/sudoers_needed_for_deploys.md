# nginx — called by crons
luke ALL=(root) NOPASSWD: /usr/sbin/nginx -t
luke ALL=(root) NOPASSWD: /usr/sbin/nginx -s reload
luke ALL=(root) NOPASSWD: /usr/bin/systemctl reload nginx
luke ALL=(root) NOPASSWD: /usr/bin/systemctl start nginx
luke ALL=(root) NOPASSWD: /usr/bin/systemctl stop nginx
luke ALL=(root) NOPASSWD: /usr/bin/systemctl restart nginx

# blocked IP deploy — tight single path
luke ALL=(root) NOPASSWD: /bin/cp /tmp/blocked_ips.conf.new /etc/nginx/blocked_ips.conf

# htpasswd deploy
luke ALL=(root) NOPASSWD: /usr/bin/cp /tmp/hermes-htpasswd /etc/nginx/.hermes-htpasswd

# apt cleanup — called by system-alert-watchdog
luke ALL=(root) NOPASSWD: /usr/bin/apt autoremove --purge -y
luke ALL=(root) NOPASSWD: /usr/bin/apt clean

# swap-refresh — called by daily swap-refresh cron
luke ALL=(root) NOPASSWD: /sbin/swapoff, /sbin/swapon

# fail2ban — read-only monitoring
luke ALL=(root) NOPASSWD: /usr/bin/fail2ban-client status

# certbot — automated renewal
luke ALL=(root) NOPASSWD: /usr/bin/certbot renew --non-interactive
luke ALL=(root) NOPASSWD: /usr/bin/certbot certificates

# troubeshooting - read-only
luke ALL=(root) NOPASSWD: /bin/journalctl -u vsftpd *
luke ALL=(root) NOPASSWD: /bin/cat /var/log/vsftpd.log
luke ALL=(root) NOPASSWD: /bin/cat /etc/vsftpd.conf