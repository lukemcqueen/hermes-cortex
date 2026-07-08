# nginx — called by crons
esther ALL=(root) NOPASSWD: /usr/sbin/nginx -t
esther ALL=(root) NOPASSWD: /usr/sbin/nginx -s reload
esther ALL=(root) NOPASSWD: /usr/bin/systemctl reload nginx
esther ALL=(root) NOPASSWD: /usr/bin/systemctl start nginx
esther ALL=(root) NOPASSWD: /usr/bin/systemctl stop nginx
esther ALL=(root) NOPASSWD: /usr/bin/systemctl restart nginx

# blocked IP deploy — tight single path
esther ALL=(root) NOPASSWD: /bin/cp /tmp/blocked_ips.conf.new /etc/nginx/blocked_ips.conf

# htpasswd deploy
esther ALL=(root) NOPASSWD: /usr/bin/cp /tmp/hermes-htpasswd /etc/nginx/.hermes-htpasswd

# apt cleanup — called by system-alert-watchdog
esther ALL=(root) NOPASSWD: /usr/bin/apt autoremove --purge -y
esther ALL=(root) NOPASSWD: /usr/bin/apt clean

# fail2ban — read-only monitoring
esther ALL=(root) NOPASSWD: /usr/bin/fail2ban-client status

# certbot — automated renewal
esther ALL=(root) NOPASSWD: /usr/bin/certbot renew --non-interactive
esther ALL=(root) NOPASSWD: /usr/bin/certbot certificates

# troubeshooting - read-only
esther ALL=(root) NOPASSWD: /bin/journalctl -u vsftpd *
esther ALL=(root) NOPASSWD: /bin/cat /var/log/vsftpd.log
esther ALL=(root) NOPASSWD: /bin/cat /etc/vsftpd.conf