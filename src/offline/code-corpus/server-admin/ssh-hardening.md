---
language: shell
tags: [ssh, security, hardening, authentication]
title: SSH Hardening
description: Comprehensive SSH server hardening — key-based auth, disable root login, change port, AllowUsers whitelist, and fail2ban integration
source: pattern
---

```bash
# ── 1. Generate strong Ed25519 key pair (on client machine) ──
ssh-keygen -t ed25519 -a 100 -C "your-email@example.com"
# Copy public key to server
ssh-copy-id -i ~/.ssh/id_ed25519.pub user@server-ip

# ── 2. Harden /etc/ssh/sshd_config ──
# Disable password auth, root login, and weak ciphers; whitelist users
cat >> /etc/ssh/sshd_config << 'EOF'

# --- Hardening directives ---
Port 2222                          # Change from default 22
PermitRootLogin no                 # Never allow root SSH
PubkeyAuthentication yes           # Force key-based auth
PasswordAuthentication no          # Disable password login
ChallengeResponseAuthentication no
AuthenticationMethods publickey    # Only publickey (no keyboard-interactive)
AllowUsers alice bob               # Whitelist — only these users may SSH
MaxAuthTries 3                     # Limit auth retries
MaxSessions 4                      # Limit concurrent sessions
LoginGraceTime 30                  # 30 seconds to authenticate
ClientAliveInterval 300            # 5 min keepalive
ClientAliveCountMax 0              # Disconnect at interval expiry
AcceptEnv LANG LC_*                # Keep locale forwarding
X11Forwarding no                   # Disable X11 unless needed
AllowTcpForwarding yes             # Keep if you tunnel; otherwise 'no'
# Cipher and MAC hardening (OpenSSH 8.9+)
KexAlgorithms curve25519-sha256,diffie-hellman-group16-sha512,diffie-hellman-group18-sha512
Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com
MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com
EOF

# Restart SSH to apply
systemctl restart sshd
# Or: sudo sshd -t  # test config first, then restart

# ── 3. fail2ban SSH jail ──
cat > /etc/fail2ban/jail.d/ssh-local.conf << 'EOF'
[sshd]
enabled   = true
port      = 2222
filter    = sshd
logpath   = /var/log/auth.log
maxretry  = 3
bantime   = 3600
findtime  = 600
EOF

systemctl restart fail2ban

# ── 4. Verify the config ──
sshd -T | grep -E '(port|permitrootlogin|pubkeyauthentication|passwordauthentication|allowusers)'
fail2ban-client status sshd
```