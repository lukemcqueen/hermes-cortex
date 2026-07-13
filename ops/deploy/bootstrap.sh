#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
#  Hermes Cortex — Linux Server Bootstrap
#  https://github.com/fleet-operator/hermes-cortex
#
#  Single-command bootstrap for a bare Ubuntu 24.04 LTS server.
#  Installs the full Hermes Cortex stack from scratch — system packages,
#  Docker, Ollama, models, Hermes Agent, gbrain, Langfuse, nginx,
#  fail2ban, UFW, cron jobs, and security hardening.
#
#  Usage:
#    curl -fsSL https://raw.githubusercontent.com/fleet-operator/hermes-cortex/main/ops/deploy/bootstrap.sh | bash
#
#  Or from a local clone:
#    bash ops/deploy/bootstrap.sh
#
#  What it does (12 phases):
#    1. Pre-flight checks        — OS, arch, sudo, connectivity
#    2. System dependencies      — apt packages, python3, nginx, fail2ban
#    3. Interactive secrets       — prompts for API keys, domain, passwords
#    4. Docker engine             — CE + compose plugin
#    5. Ollama + models           — LLM server + embedding/coder models
#    6. Hermes CLI                — Hermes Agent binary
#    7. hermes-cortex repo        — clone, .env, run install.sh
#    8. nginx + Let's Encrypt SSL — reverse proxy with auto HTTPS
#    9. fail2ban                  — nginx/SSH jail config
#   10. UFW + security hardening  — firewall, sysctl, permissions
#   11. Final verification        — cortex-doctor, health check
#   12. Summary                   — URLs, ports, next steps
#
#  Idempotent — safe to re-run. Skips already-completed phases.
#
#  Target: Ubuntu 24.04 LTS (amd64 or arm64)
#  Estimated time: 8–15 minutes (mostly model downloads)
# ═══════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── Terminal colors ─────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
ok()    { printf "  ${GREEN}✓${RESET} %s\n" "$*"; }
info()  { printf "  ${CYAN}→${RESET} %s\n" "$*"; }
warn()  { printf "  ${YELLOW}⚠${RESET} %s\n" "$*"; }
fail()  { printf "  ${RED}✗${RESET} %s\n" "$*"; exit 1; }
header(){ printf "\n${BOLD}━ %s ━${RESET}\n" "$*"; }

# ── Globals ─────────────────────────────────────────────────────────
HERMES_HOME="${HOME:?}/.hermes"
CORTEX_REPO="${HOME:?}/hermes-cortex"
CORTEX_DEPLOY="${HOME:?}/.hermes-cortex"
LANGFUSE_DIR="${HOME:?}/langfuse"

# Secrets (populated by interactive prompts)
AGENT_NAME=""
AGENT_DOMAIN=""
LE_EMAIL=""
OPENROUTER_KEY=""
DEEPSEEK_KEY=""
INBOX_PASSWORD=""
LANGFUSE_PK=""
LANGFUSE_SK=""

# SSL (set by interactive prompts)
SSL_METHOD="1"
SSL_SOURCE_HOST=""
SSL_SOURCE_DOMAIN=""

# ── Step tracking ──────────────────────────────────────────────────
STEP_TOTAL=11
STEP_CURRENT=0
next_step() { STEP_CURRENT=$((STEP_CURRENT + 1)); printf "\n${BOLD}[%d/%d]${RESET} " "$STEP_CURRENT" "$STEP_TOTAL"; header "$*"; }

# ═══════════════════════════════════════════════════════════════════════
#  PHASE 1: PRE-FLIGHT CHECKS
# ═══════════════════════════════════════════════════════════════════════
next_step "Pre-flight checks"

# Must be run as root or with sudo
if [[ $EUID -ne 0 ]]; then
    if command -v sudo &>/dev/null; then
        warn "Not running as root — re-executing with sudo..."
        exec sudo bash "$0" "$@"
    else
        fail "Must run as root (or have sudo). Try: sudo bash $0"
    fi
fi

# Use the original user's home if running via sudo
if [[ -n "${SUDO_USER:-}" ]]; then
    REAL_USER="$SUDO_USER"
    REAL_HOME="$(eval echo ~$SUDO_USER)"
else
    REAL_USER="${USER:-root}"
    REAL_HOME="$HOME"
fi

# OS check
OS_ID=""
OS_VERSION=""
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    OS_ID="$ID"
    OS_VERSION="$VERSION_ID"
fi
if [[ "$OS_ID" != "ubuntu" ]]; then
    fail "This bootstrap targets Ubuntu 24.04 (detected: $OS_ID $OS_VERSION). Edit the script to adapt to your distro."
fi
ok "OS: $OS_ID $OS_VERSION ($(uname -m))"

# Architecture
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64|amd64) ARCH="amd64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    *) warn "Untested architecture: $ARCH — continuing anyway" ;;
esac

# Internet connectivity
if ! curl -sf --max-time 5 https://github.com >/dev/null 2>&1; then
    fail "No internet connectivity. Check DNS and firewall."
fi
ok "Internet reachable"

# ── Ensure TTY for interactive prompts ──
if [[ ! -t 0 ]]; then
    warn "Running non-interactively (no TTY) — secrets will need manual config after bootstrap"
    NONINTERACTIVE=true
else
    NONINTERACTIVE=false
fi

# ═══════════════════════════════════════════════════════════════════════
#  PHASE 2: SYSTEM DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════
next_step "System dependencies"

export DEBIAN_FRONTEND=noninteractive

# Update package lists
info "Updating package lists..."
apt-get update -qq || warn "apt update had issues — continuing"

# Core packages — always needed
info "Installing core packages..."
apt-get install -y -qq \
    curl wget git jq unzip \
    python3 python3-pip python3-venv \
    ca-certificates gnupg lsb-release \
    htop iotop net-tools dnsutils \
    zsh tmux \
    >/dev/null 2>&1 || warn "Some core packages failed — check apt"

# Server packages
header "Web server + security"
apt-get install -y -qq \
    nginx nginx-extras \
    fail2ban \
    ufw \
    certbot python3-certbot-nginx \
    >/dev/null 2>&1 || warn "Some server packages failed"

ok "System packages installed"

# ═══════════════════════════════════════════════════════════════════════
#  PHASE 3: INTERACTIVE SECRETS
# ═══════════════════════════════════════════════════════════════════════
next_step "Interactive secrets collection"

if $NONINTERACTIVE; then
    info "Non-interactive mode — will create template .env for manual edit"
    AGENT_NAME="${AGENT_NAME:-agent}"
    AGENT_DOMAIN="${AGENT_DOMAIN:-localhost}"
else
    echo ""
    echo "  ${BOLD}Enter values or press Enter to accept defaults in [brackets]${RESET}"
    echo "  ${YELLOW}API keys can be left blank and filled in later.${RESET}"
    echo ""

    read -rp "  Agent name                          [agent]: " input
    AGENT_NAME="${input:-agent}"

    read -rp "  Public domain (e.g. agent.example.com): " input
    AGENT_DOMAIN="${input:-}"
    if [[ -z "$AGENT_DOMAIN" ]]; then
        warn "No domain set — SSL will be skipped. Health endpoint will be HTTP-only."
        AGENT_DOMAIN="localhost"
    fi

    read -rp "  Let's Encrypt email (for SSL expiry notices): " input
    LE_EMAIL="${input:-}"

    echo ""
    info "SSL certificates"
    echo "    1) Let's Encrypt (auto-provision — needs public DNS + port 80)"
    echo "    2) Copy from another server (e.g. Moses/Joseph already has the cert)"
    read -rp "  SSL method [1/2]: " input
    SSL_METHOD="${input:-1}"
    if [[ "$SSL_METHOD" == "2" ]]; then
        read -rp "  Source server (user@host, e.g. root@joseph): " SSL_SOURCE_HOST
        read -rp "  Domain on the certificate:                  " SSL_SOURCE_DOMAIN
        AGENT_DOMAIN="${SSL_SOURCE_DOMAIN:-$AGENT_DOMAIN}"
    fi

    echo ""
    info "API keys (can be left blank — edit ~/hermes-cortex/.env later)"
    read -rp "  OpenRouter API key (sk-or-...):     " input
    OPENROUTER_KEY="${input:-}"
    read -rp "  DeepSeek API key (sk-...):          " input
    DEEPSEEK_KEY="${input:-}"
    read -rp "  Agent inbox password (auto-gen if blank): " input
    INBOX_PASSWORD="${input:-$(openssl rand -base64 18)}"

    echo ""
    info "Langfuse credentials (can be left blank)"
    read -rp "  Langfuse public key (pk-lf-...):    " input
    LANGFUSE_PK="${input:-}"
    read -rp "  Langfuse secret key (sk-lf-...):    " input
    LANGFUSE_SK="${input:-}"

    echo ""
    info "GitHub access (for agents to push changes to the repo)"
    read -rp "  GitHub fine-grained PAT (ghp_...):    " input
    GITHUB_TOKEN="${input:-}"

    # Generate htpasswd entry for inbox
    HTPASSWD_HASH=""
    if command -v openssl &>/dev/null && [[ -n "$INBOX_PASSWORD" ]]; then
        HTPASSWD_HASH=$(openssl passwd -apr1 "$INBOX_PASSWORD" 2>/dev/null || true)
    fi
fi

ok "Secrets collected"

# ═══════════════════════════════════════════════════════════════════════
#  PHASE 4: DOCKER ENGINE
# ═══════════════════════════════════════════════════════════════════════
next_step "Docker Engine"

if command -v docker &>/dev/null; then
    info "Docker already installed ($(docker --version 2>/dev/null || true))"
else
    info "Adding Docker GPG key and repository..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin >/dev/null
    ok "Docker installed ($(docker --version 2>/dev/null || true))"
fi

# Add user to docker group
if groups "$REAL_USER" 2>/dev/null | grep -qv docker; then
    usermod -aG docker "$REAL_USER"
    info "User '$REAL_USER' added to docker group (log out/in to take effect)"
fi

# Start and enable
systemctl enable docker 2>/dev/null || true
systemctl start docker 2>/dev/null || true
ok "Docker service active"

# ═══════════════════════════════════════════════════════════════════════
#  PHASE 5: OLLAMA + MODELS
# ═══════════════════════════════════════════════════════════════════════
next_step "Ollama + models"

if command -v ollama &>/dev/null; then
    info "Ollama already installed"
else
    info "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | bash
    ok "Ollama installed"
fi

# Configure Ollama systemd service
cat > /etc/systemd/system/ollama.service << 'UNIT'
[Unit]
Description=Ollama LLM Server
After=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=REAL_USER
ExecStart=/usr/local/bin/ollama serve
Environment=OLLAMA_HOST=127.0.0.1
Environment=OLLAMA_NUM_THREADS=2
Environment=OLLAMA_KEEP_ALIVE=0
Restart=always
RestartSec=30
NoNewPrivileges=yes
ProtectHome=read-only
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
UNIT
sed -i "s/REAL_USER/$REAL_USER/g" /etc/systemd/system/ollama.service
systemctl daemon-reload
systemctl enable ollama
systemctl start ollama
ok "Ollama service configured"

# Wait for Ollama to be ready
info "Waiting for Ollama to respond..."
for i in $(seq 1 15); do
    if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        ok "Ollama ready"
        break
    fi
    sleep 2
done

# Pull models (in parallel — background)
info "Pulling models (background — will finish after bootstrap)..."
sudo -u "$REAL_USER" OLLAMA_HOST=127.0.0.1 ollama pull nomic-embed-text:v1.5 &
PID_EMBED=$!
sudo -u "$REAL_USER" OLLAMA_HOST=127.0.0.1 ollama pull qwen2.5-coder:3b &
PID_CODER=$!
ok "Model pulls started (PIDs: $PID_EMBED, $PID_CODER)"

# ═══════════════════════════════════════════════════════════════════════
#  PHASE 6: HERMES CLI
# ═══════════════════════════════════════════════════════════════════════
next_step "Hermes Agent CLI"

if command -v hermes &>/dev/null; then
    info "Hermes already installed ($(hermes --version 2>/dev/null || true))"
else
    info "Installing Hermes Agent..."
    curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
    # Add to PATH for current user
    if ! grep -q '.local/bin' "/home/$REAL_USER/.bashrc" 2>/dev/null; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "/home/$REAL_USER/.bashrc"
    fi
    ok "Hermes installed"
fi

# ═══════════════════════════════════════════════════════════════════════
#  PHASE 7: CLONE REPO + RUN INSTALLER
# ═══════════════════════════════════════════════════════════════════════
next_step "Clone hermes-cortex + run installer"

if [[ -d "$CORTEX_REPO" ]]; then
    info "hermes-cortex already cloned — pulling latest..."
    cd "$CORTEX_REPO" && git pull --ff-only origin main 2>/dev/null || true
else
    info "Cloning hermes-cortex..."
    sudo -u "$REAL_USER" git clone --depth 1 \
        https://github.com/fleet-operator/hermes-cortex.git "$CORTEX_REPO"
    ok "Repo cloned"
fi

# Create .env from template
if [[ ! -f "$CORTEX_REPO/.env" ]]; then
    info "Creating .env from template..."
    cp "$CORTEX_REPO/.env.example" "$CORTEX_REPO/.env"
    chown "$REAL_USER:$REAL_USER" "$CORTEX_REPO/.env"
    chmod 600 "$CORTEX_REPO/.env"

    # Write collected secrets
    declare -A SECRETS
    SECRETS[AGENT_NAME]="$AGENT_NAME"
    SECRETS[CORTEX_HEALTH_URL]="https://${AGENT_DOMAIN}:13007/health"
    SECRETS[CORTEX_INBOX_URL]="https://${AGENT_DOMAIN}:13004"
    SECRETS[CORTEX_INBOX_AUTH]="${AGENT_NAME}:${INBOX_PASSWORD}"
    SECRETS[OPENROUTER_API_KEY]="$OPENROUTER_KEY"
    SECRETS[DEEPSEEK_API_KEY]="$DEEPSEEK_KEY"
    SECRETS[HERMES_LANGFUSE_PUBLIC_KEY]="$LANGFUSE_PK"
    SECRETS[HERMES_LANGFUSE_SECRET_KEY]="$LANGFUSE_SK"
    SECRETS[CORTEX_SSL_CERT_PATH]="/etc/letsencrypt/live/${AGENT_DOMAIN}/fullchain.pem"
    SECRETS[CORTEX_SSL_CERT_KEY_PATH]="/etc/letsencrypt/live/${AGENT_DOMAIN}/privkey.pem"
    SECRETS[AGENT_DOMAIN]="$AGENT_DOMAIN"

    for key in "${!SECRETS[@]}"; do
        val="${SECRETS[$key]}"
        if [[ -n "$val" ]]; then
            # Uncomment + set the value
            sed -i "s/^#\? *${key}=.*/${key}=\"${val//\//\\/}\"/" "$CORTEX_REPO/.env" 2>/dev/null || true
        fi
    done
    ok ".env configured with secrets"
else
    info ".env already exists — skipping"
fi

# Create Langfuse .env
if [[ ! -f "$LANGFUSE_DIR/.env" ]]; then
    mkdir -p "$LANGFUSE_DIR"
    if [[ -f "$CORTEX_REPO/ops/install/deploy/.env.example" ]]; then
        cp "$CORTEX_REPO/ops/install/deploy/.env.example" "$LANGFUSE_DIR/.env"
        chown "$REAL_USER:$REAL_USER" "$LANGFUSE_DIR/.env"
        chmod 600 "$LANGFUSE_DIR/.env"
    fi
fi

# Configure git credentials so agents can push changes
if [[ -n "$GITHUB_TOKEN" ]]; then
    sudo -u "$REAL_USER" git config --global credential.helper store
    cat > "$REAL_HOME/.git-credentials" << CRED
https://git:${GITHUB_TOKEN}@github.com
CRED
    chmod 600 "$REAL_HOME/.git-credentials"
    chown "$REAL_USER:$REAL_USER" "$REAL_HOME/.git-credentials"
    ok "Git credentials configured (HTTPS + credential.helper=store)"
else
    info "No GitHub token provided — git push will fail until credentials are set up."
    info "  Run: git config --global credential.helper store"
    info "  Then: echo 'https://git:ghp_YOUR_TOKEN@github.com' > ~/.git-credentials && chmod 600 ~/.git-credentials"
fi

# Run the install.sh as the real user
info "Running hermes-cortex installer..."
cd "$CORTEX_REPO"
sudo -u "$REAL_USER" HOME="$REAL_HOME" \
    CORTEX_PROFILE="${CORTEX_PROFILE:-server}" \
    bash ops/install/install.sh 2>&1 | \
    while IFS= read -r line; do printf "    %s\n" "$line"; done
ok "hermes-cortex install complete"

# ═══════════════════════════════════════════════════════════════════════
#  PHASE 8: NGINX + LET'S ENCRYPT SSL
# ═══════════════════════════════════════════════════════════════════════
next_step "nginx + SSL"

# Create nginx config from repo template if it exists
if [[ -f "$CORTEX_REPO/ops/deploy/ansible/templates/hermes-nginx.conf.j2" ]]; then
    info "Generating nginx config from Ansible template..."
    # Simple variable substitution for the Jinja2 template
    sed "s/{{ agent_domain }}/$AGENT_DOMAIN/g" \
        "$CORTEX_REPO/ops/deploy/ansible/templates/hermes-nginx.conf.j2" \
        > /etc/nginx/sites-available/hermes-cortex.conf

    # Remove default site, enable Hermes
    rm -f /etc/nginx/sites-enabled/default
    ln -sf /etc/nginx/sites-available/hermes-cortex.conf /etc/nginx/sites-enabled/

    if nginx -t 2>&1; then
        systemctl reload nginx || systemctl start nginx
        ok "nginx configured and running"
    else
        warn "nginx config has errors — review /etc/nginx/sites-available/hermes-cortex.conf"
    fi
else
    # Use the install.sh's nginx setup
    info "Using install.sh nginx setup..."
    cd "$CORTEX_REPO"
    bash ops/scripts/install/install-nginx.sh 2>/dev/null || \
        warn "nginx install script had issues — manual config may be needed"
fi

# htpasswd for inbox
if [[ -n "$HTPASSWD_HASH" ]] && [[ ! -f /etc/nginx/.hermes-htpasswd ]]; then
    echo "${AGENT_NAME}:${HTPASSWD_HASH}" > /etc/nginx/.hermes-htpasswd
    chmod 600 /etc/nginx/.hermes-htpasswd
    ok "htpasswd created for inbox API"
fi

# ── SSL: Let's Encrypt or Copy from another server ──
if [[ "$SSL_METHOD" == "2" ]] && [[ -n "${SSL_SOURCE_HOST:-}" ]]; then
    info "Copying SSL certificate from $SSL_SOURCE_HOST..."
    mkdir -p /etc/letsencrypt/live/"$AGENT_DOMAIN"
    # Copy fullchain + privkey via SSH (assumes SSH key on source host)
    scp -o StrictHostKeyChecking=accept-new \
        "$SSL_SOURCE_HOST:/etc/letsencrypt/live/$AGENT_DOMAIN/fullchain.pem" \
        "/etc/letsencrypt/live/$AGENT_DOMAIN/fullchain.pem" 2>/dev/null || \
        warn "scp failed — you'll need to copy certs manually from $SSL_SOURCE_HOST"
    scp -o StrictHostKeyChecking=accept-new \
        "$SSL_SOURCE_HOST:/etc/letsencrypt/live/$AGENT_DOMAIN/privkey.pem" \
        "/etc/letsencrypt/live/$AGENT_DOMAIN/privkey.pem" 2>/dev/null || \
        warn "scp failed for privkey"
    # Copy chain.pem and options-ssl-nginx.conf if available
    scp -o StrictHostKeyChecking=accept-new \
        "$SSL_SOURCE_HOST:/etc/letsencrypt/live/$AGENT_DOMAIN/chain.pem" \
        "/etc/letsencrypt/live/$AGENT_DOMAIN/chain.pem" 2>/dev/null || true
    scp -o StrictHostKeyChecking=accept-new \
        "$SSL_SOURCE_HOST:/etc/letsencrypt/options-ssl-nginx.conf" \
        "/etc/letsencrypt/options-ssl-nginx.conf" 2>/dev/null || true
    scp -o StrictHostKeyChecking=accept-new \
        "$SSL_SOURCE_HOST:/etc/letsencrypt/ssl-dhparams.pem" \
        "/etc/letsencrypt/ssl-dhparams.pem" 2>/dev/null || true
    chmod 755 /etc/letsencrypt/live/"$AGENT_DOMAIN"
    chmod 644 /etc/letsencrypt/live/"$AGENT_DOMAIN"/*.pem 2>/dev/null || true
    chmod 600 /etc/letsencrypt/live/"$AGENT_DOMAIN"/privkey.pem 2>/dev/null || true
    systemctl reload nginx 2>/dev/null || true
    ok "SSL certificates copied from $SSL_SOURCE_HOST"
elif [[ "$AGENT_DOMAIN" != "localhost" ]] && [[ -n "$LE_EMAIL" ]]; then
    info "Requesting Let's Encrypt certificate for $AGENT_DOMAIN..."
    certbot --nginx -d "$AGENT_DOMAIN" --non-interactive --agree-tos \
        --email "$LE_EMAIL" --redirect 2>&1 || \
        warn "Let's Encrypt failed — check DNS and try: sudo certbot --nginx -d $AGENT_DOMAIN"
    ok "SSL certificate obtained"
elif [[ "$AGENT_DOMAIN" != "localhost" ]]; then
    warn "No email provided — skipping SSL. Run later: sudo certbot --nginx -d $AGENT_DOMAIN"
else
    info "No domain — skipping SSL (localhost only)"
fi

# ═══════════════════════════════════════════════════════════════════════
#  PHASE 9: FAIL2BAN
# ═══════════════════════════════════════════════════════════════════════
next_step "Fail2ban (nginx + SSH)"

# Basic nginx jail
if [[ ! -f /etc/fail2ban/jail.d/hermes-cortex.local ]]; then
    cat > /etc/fail2ban/jail.d/hermes-cortex.local << 'JAIL'
[nginx-http-auth]
enabled  = true
port     = http,https
filter   = nginx-http-auth
logpath  = /var/log/nginx/error.log
maxretry = 5
bantime  = 3600

[nginx-botsearch]
enabled  = true
port     = http,https
filter   = nginx-botsearch
logpath  = /var/log/nginx/access.log
maxretry = 10
findtime = 60
bantime  = 86400

[sshd]
enabled  = true
port     = ssh
filter   = sshd
logpath  = /var/log/auth.log
maxretry = 3
bantime  = 86400
JAIL
    ok "fail2ban jails configured (nginx-http-auth, nginx-botsearch, sshd)"
fi

systemctl enable fail2ban 2>/dev/null || true
systemctl restart fail2ban 2>/dev/null || true
ok "fail2ban active"

# ═══════════════════════════════════════════════════════════════════════
#  PHASE 10: UFW + SECURITY HARDENING
# ═══════════════════════════════════════════════════════════════════════
next_step "UFW + security hardening"

# UFW — default deny, allow specific
ufw --force reset 2>/dev/null || true
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow http
ufw allow https
ufw allow in on docker0 to any port 11434 proto tcp from 127.0.0.1 2>/dev/null || true
ufw --force enable
ok "UFW enabled (SSH, HTTP, HTTPS allowed)"

# sysctl tuning
cat > /etc/sysctl.d/99-hermes-cortex.conf << 'SYSCTL'
# Hermes Cortex — kernel tuning
net.ipv4.tcp_keepalive_time = 60
net.ipv4.tcp_keepalive_intvl = 10
net.ipv4.tcp_keepalive_probes = 6
vm.swappiness = 10
vm.max_map_count = 262144
SYSCTL
sysctl --system >/dev/null 2>&1 || true
ok "sysctl tuned"

# File permissions
chmod 600 "$CORTEX_REPO/.env" 2>/dev/null || true
chmod 600 "$LANGFUSE_DIR/.env" 2>/dev/null || true
chmod 600 /etc/nginx/.hermes-htpasswd 2>/dev/null || true
ok "Sensitive file permissions hardened (chmod 600)"

# Journald rate limiting for verbose services
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/99-hermes-cortex.conf << 'JOURNAL'
[Journal]
RateLimitIntervalSec=30s
RateLimitBurst=20000
JOURNAL
systemctl restart systemd-journald 2>/dev/null || true
ok "Journald rate limit increased"

# ═══════════════════════════════════════════════════════════════════════
#  PHASE 11: FINAL VERIFICATION
# ═══════════════════════════════════════════════════════════════════════
next_step "Final verification"

# Wait a moment for services to settle
sleep 3

# Run doctor
info "Running cortex-doctor.py..."
cd "$CORTEX_REPO"
sudo -u "$REAL_USER" HOME="$REAL_HOME" \
    python3 ops/scripts/manage/cortex-doctor.py --quiet 2>&1 | \
    while IFS= read -r line; do printf "    %s\n" "$line"; done

# Check key endpoints
echo ""
info "Key health checks..."
for check in \
    "Ollama:      curl -s http://127.0.0.1:11434/api/tags | head -c 100" \
    "Health:      curl -s http://127.0.0.1:13007/health | head -c 200" \
    "nginx:       curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:80" \
    "Langfuse:    curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000"; do

    label="${check%%:*}"
    cmd="${check#*: }"
    result="$(eval "$cmd" 2>/dev/null || echo '❌')"
    if [[ -n "$result" && "$result" != "❌" && "$result" != "000" ]]; then
        printf "    ✅ %s %s\n" "$label" "$result"
    else
        printf "    ❌ %s unreachable\n" "$label"
    fi
done

# ═══════════════════════════════════════════════════════════════════════
#  PHASE 12: SUMMARY
# ═══════════════════════════════════════════════════════════════════════
next_step "Bootstrap complete!"

echo ""
echo "  ${BOLD}Hermes Cortex is installed and running on $AGENT_DOMAIN${RESET}"
echo ""
echo "  ┌─────────────────────┬──────────────────────────────────────────┐"
echo "  │ Service             │ URL                                      │"
echo "  ├─────────────────────┼──────────────────────────────────────────┤"
printf "  │ Hermes Agent        │ your terminal / dashboard               │\n"
printf "  │ Cortex Dashboard   │ https://%s:13001                  │\n" "$AGENT_DOMAIN"
printf "  │ Langfuse           │ https://%s:13002                  │\n" "$AGENT_DOMAIN"
printf "  │ Agent Inbox API    │ https://%s:13004                  │\n" "$AGENT_DOMAIN"
printf "  │ Health Endpoint    │ https://%s:13007/health            │\n" "$AGENT_DOMAIN"
printf "  │ Ollama             │ http://127.0.0.1:11434                 │\n"
echo "  └─────────────────────┴──────────────────────────────────────────┘"
echo ""
echo "  ${BOLD}Credentials${RESET}"
printf "  Agent inbox auth:     %s / %s\n" "$AGENT_NAME" "${INBOX_PASSWORD:-<set in .env>}"
echo ""
echo "  ${BOLD}Key files${RESET}"
echo "  Config:              ~/hermes-cortex/.env"
echo "  State:               ~/.hermes-cortex/"
echo "  Hermes home:         ~/.hermes/"
echo "  Langfuse config:     ~/langfuse/.env"
echo "  nginx config:        /etc/nginx/sites-available/hermes-cortex.conf"
echo "  fail2ban jails:      /etc/fail2ban/jail.d/hermes-cortex.local"
echo ""
echo "  ${BOLD}Next steps${RESET}"
echo "  1. Edit ~/hermes-cortex/.env to fill in any missing API keys"
echo "  2. If models are still downloading: ollama ps"
echo "  3. Verify: python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py"
echo "  4. Create agent cron jobs: cd ~/hermes-cortex && bash ops/scripts/install/install-crons.sh"
echo "  5. For orchestrator: set IS_ORCHESTRATOR=true in .env"
echo ""
echo "  ${BOLD}Recovery (if something goes wrong)${RESET}"
echo "  The script is idempotent — just re-run it. Or for a full reset:"
echo "    # Reset Docker:      docker compose -f ~/langfuse/docker-compose.yml down"
echo "    # Reset nginx:       rm /etc/nginx/sites-enabled/hermes-cortex.conf"
echo "    # Re-run doctor:     python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --fix"
echo ""

# ═══════════════════════════════════════════════════════════════════════
#  WAIT FOR MODELS (non-blocking)
# ═══════════════════════════════════════════════════════════════════════
info "Waiting for model pulls to finish (up to 5 min)..."
wait $PID_EMBED 2>/dev/null || true
wait $PID_CODER 2>/dev/null || true
ok "Model pulls complete"

# Final service check
systemctl is-active --quiet ollama && ok "Ollama: active" || warn "Ollama: inactive"
systemctl is-active --quiet nginx && ok "nginx: active" || warn "nginx: inactive"
systemctl is-active --quiet fail2ban && ok "fail2ban: active" || warn "fail2ban: inactive"
ufw status | grep -q active && ok "UFW: active" || warn "UFW: inactive"

echo ""
printf "  ${GREEN}${BOLD}✅ Bootstrap complete in ${SECONDS}s${RESET}\n"
echo ""
