#!/usr/bin/env bash
# install-fail2ban.sh — install + configure fail2ban on this host.
#
# Based on the proven fleet config: nftables ban backend (Linux),
# pf backend (macOS), jails for sshd + nginx-http-auth + nginx-badbots.
# Cross-platform: pacman (Arch) / brew (macOS). Idempotent.
# Run:  sudo bash install-fail2ban.sh
set -euo pipefail

OS="$(uname -s)"
JAIL_DIR="/etc/fail2ban/jail.d"
[[ "$OS" == "Darwin" ]] && JAIL_DIR="$(brew --prefix 2>/dev/null || echo /usr/local)/etc/fail2ban/jail.d"

say() { printf '\033[1;34m== %s ==\033[0m\n' "$*"; }
ok()  { printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }

need_root() {
  if [[ "$OS" == "Darwin" ]]; then
    return 0  # brew runs as user; sudo only where needed
  fi
  if [[ $EUID -ne 0 ]]; then
    echo "Run as root:  sudo bash $0"
    exit 1
  fi
}

say "Installing fail2ban"
if command -v fail2ban-server >/dev/null 2>&1; then
  ok "already installed"
else
  if [[ "$OS" == "Darwin" ]]; then
    brew install fail2ban
  else
    pacman -S --needed --noconfirm fail2ban
  fi
  ok "installed"
fi

say "Writing jail configs"
mkdir -p "$JAIL_DIR"

BANACTION="nftables"
if [[ "$OS" == "Darwin" ]]; then
  BANACTION="pf"
fi

# Arch's fail2ban package does NOT ship nginx filter files (Debian/Ubuntu
# do). Without these, the nginx jails fail to load ("Found no accessible
# config files for 'filter.d/nginx-badbots'") and the service exits 255.
# Ship the standard filters explicitly — works on every distro.
FILTER_DIR="/etc/fail2ban/filter.d"
[[ "$OS" == "Darwin" ]] && FILTER_DIR="$(brew --prefix 2>/dev/null || echo /usr/local)/etc/fail2ban/filter.d"
mkdir -p "$FILTER_DIR"

if [[ ! -f "$FILTER_DIR/nginx-http-auth.conf" ]]; then
  cat > "$FILTER_DIR/nginx-http-auth.conf" <<'EOF'
[Definition]

failregex = ^ \[error\] \d+#\d+: \*\d+ user "(?P<user>[^"]+)":? (?:password mismatch|was not found in "[^"]*"|user not found), client: <HOST>, server: \S*, request: "\S+ \S+ HTTP/\d+\.\d+", host: "\S+(?::\d+)?"(?:, referrer: "\S+")?\s*$

ignoreregex =

[Init]

# default port if not specified in jail.conf
port = http,https
EOF
  ok "filter nginx-http-auth.conf written"
else
  ok "filter nginx-http-auth.conf present"
fi

if [[ ! -f "$FILTER_DIR/nginx-badbots.conf" ]]; then
  cat > "$FILTER_DIR/nginx-badbots.conf" <<'EOF'
[Definition]

failregex = ^<HOST> -.*"(GET|POST|HEAD|PUT|DELETE|OPTIONS).*"(?:[12345]\d\d) .*"(?:Mozilla.*(?:BOT|bot|spider|crawl|curl|wget|scrapy|python-requests|Go-http-client)|curl|wget|Scrapy|python-requests|Go-http-client).*"$
            ^<HOST> -.*"(GET|POST|HEAD|PUT|DELETE|OPTIONS).*"(?:[12345]\d\d) .*"(?:${_badbotscustom})"$

ignoreregex =

[Init]

# List of bad bots to ban
_badbotscustom = 12345|Badbot|Baiduspider|Curl|Go-http-client|libwww-perl|Lwp-trivial|MJ12bot|python-requests|Scrapy|Wget|YandexBot

# default port if not specified in jail.conf
port = http,https
EOF
  ok "filter nginx-badbots.conf written"
else
  ok "filter nginx-badbots.conf present"
fi

cat > "$JAIL_DIR/defaults-local.conf" <<EOF
[DEFAULT]
banaction = ${BANACTION}
backend = systemd

[sshd]
enabled = true
EOF
ok "defaults-local.conf (sshd jail, ${BANACTION})"

cat > "$JAIL_DIR/nginx-auth.local" <<'EOF'
[nginx-http-auth]
enabled  = true
port     = http,https
filter   = nginx-http-auth
logpath  = /var/log/nginx/*error.log
maxretry = 5
bantime  = 3600
EOF
ok "nginx-auth.local"

cat > "$JAIL_DIR/nginx-badbots.local" <<'EOF'
[nginx-badbots]
enabled  = true
port     = http,https
filter   = nginx-badbots
logpath  = /var/log/nginx/access.log
maxretry = 1
bantime  = 86400
findtime = 86400
EOF
ok "nginx-badbots.local"

say "Enabling + starting fail2ban"
if [[ "$OS" == "Darwin" ]]; then
  brew services start fail2ban
else
  systemctl enable --now fail2ban
  systemctl restart fail2ban
fi
sleep 2

say "Status"
fail2ban-client status || true
echo ""
for jail in sshd nginx-http-auth nginx-badbots; do
  echo "--- $jail ---"
  fail2ban-client status "$jail" 2>&1 | grep -E 'Status|Currently banned|Total banned' || true
done

echo ""
echo "✅ Done. Verify the ban set:"
if [[ "$OS" == "Darwin" ]]; then
  echo "   sudo pfctl -s Anchors | grep f2b"
else
  echo "   sudo nft list set inet f2b-table addr-set f2b-sshd"
fi
