---
language: shell
tags: [ssh, networking, tunnel, security]
title: Advanced SSH Config Patterns
description: Host aliases, Match exec, ControlMaster multiplexing, ProxyCommand via netcat/ncat, LocalCommand
source: pattern
---

# Advanced `~/.ssh/config` Patterns

The SSH client config file (`~/.ssh/config`) supports powerful patterns for
managing complex infrastructure. This snippet covers the most useful advanced
features.

## Host Aliases and Wildcards

```ssh_config
# ~/.ssh/config

# Wildcard for a domain pattern
Host *.internal.example.com
    User admin
    IdentityFile ~/.ssh/internal_ed25519
    ProxyJump bastion.example.com
    StrictHostKeyChecking accept-new

# Multiple aliases for the same host
Host prod prod-01 prod-primary
    HostName prod-01.example.com
    User root
    Port 2222
    IdentityFile ~/.ssh/prod_deploy_key

# Pattern negation — skip certain hosts
Host *.example.com !backup*.example.com
    User deploy
    Compression yes
```

## `Match` Keyword

`Match` enables conditional configuration based on the target host, user, local
user, or command output.

### Match on Host Pattern

```ssh_config
# Apply different configs based on the destination
Match Host "db-*"
    User dba
    IdentityFile ~/.ssh/dba_key
    ForwardAgent no

Match Host "web-*" Exec "hostname | grep -q prod"
    User prod-deploy
    IdentityFile ~/.ssh/prod_deploy_key
```

### Match on Local User

```ssh_config
# Terry gets a different key and jump host
Match LocalUser terry
    IdentityFile ~/.ssh/terry_key
    ProxyJump terry-bastion.example.com

Match LocalUser !terry
    ProxyJump shared-bastion.example.com
```

### Match with `Exec` (Dynamic Conditions)

Run a command — if it exits 0, the config block applies. Powerful for environment
detection.

```ssh_config
# Use different jump host based on network
Match Exec "ping -c1 -W1 10.0.0.1 >/dev/null 2>&1"
    ProxyJump office-bastion.example.com
    User internal

Match Exec "! ping -c1 -W1 10.0.0.1 >/dev/null 2>&1"
    ProxyJump external-bastion.example.com
    User external

# Conditional identity based on working directory
Match Exec "pwd | grep -q /srv/production"
    IdentityFile ~/.ssh/prod_key

Match Exec "pwd | grep -q /srv/staging"
    IdentityFile ~/.ssh/staging_key

# Time-based access (office hours vs after-hours)
Match Exec "[ $(date +%H) -ge 9 ] && [ $(date +%H) -lt 18 ]"
    User office-hours
Match Exec "[ $(date +%H) -lt 9 ] || [ $(date +%H) -ge 18 ]"
    User after-hours
    ForwardAgent no
```

### Match on Original Host

```ssh_config
# Apply based on the hostname originally typed
Match OriginalHost "myapp-dev"
    HostName dev.myapp.internal
    User devops

Match OriginalHost "myapp-prod"
    HostName prod-03.myapp.internal
    User sre
```

## ControlMaster Multiplexing

Reuse a single TCP connection for multiple SSH sessions — drastically reduces
login latency.

```ssh_config
# Global multiplexing settings
Host *
    ControlMaster auto
    ControlPath ~/.ssh/controlmasters/%r@%h:%p
    ControlPersist 4h

# Create the control directory
# mkdir -p ~/.ssh/controlmasters
```

### Manual Control

```shell
# Force a new master connection
ssh -M -S ~/.ssh/controlmasters/myconn user@host

# Subsequent connections reuse the master
ssh -S ~/.ssh/controlmasters/myconn user@host

# Check control socket status
ssh -O check user@host

# Gracefully stop master connection
ssh -O stop user@host

# Cancel all pending forwarded connections
ssh -O exit user@host
```

### Per-Host Multiplexing Control

```ssh_config
Host bastion
    HostName bastion.example.com
    ControlMaster auto
    ControlPath ~/.ssh/cm/%r@%h:%p
    ControlPersist 8h

# Disable multiplexing for port-forwarding sessions
Host tunnel-bastion
    HostName bastion.example.com
    User tunnel
    ControlMaster no
    ControlPath none
```

## ProxyCommand — Advanced Proxying

`ProxyCommand` runs an arbitrary command to connect to the SSH server. More
flexible than `ProxyJump`.

### Via netcat / ncat

```ssh_config
# Direct TCP connection via netcat
Host old-bastion
    HostName target.internal
    User admin
    ProxyCommand ssh bastion.example.com nc %h %p 2>/dev/null

# Using ncat with timeout
Host slow-bastion
    HostName target.internal
    User admin
    ProxyCommand ssh bastion.example.com ncat --wait 30 %h %p
```

### Via HTTP CONNECT Proxy

```ssh_config
# SSH through an HTTP proxy (corporations, hotels)
Host external
    HostName github.com
    User git
    Port 443
    ProxyCommand nc -X connect -x proxy.corp.com:3128 %h %p

# Using corkscrew (dedicated HTTP CONNECT tool)
Host github.com
    User git
    Port 443
    ProxyCommand corkscrew proxy.corp.com 3128 %h %p ~/.ssh/proxy-auth
```

### Via SOCKS5 Proxy

```ssh_config
Host *.example.com
    ProxyCommand nc -X 5 -x localhost:1080 %h %p

# Using connect-proxy
Host *.internal
    ProxyCommand connect-proxy -S localhost:1080 %h %p
```

### Via an Intermediate Host with netcat mode

```ssh_config
Host target
    HostName 10.0.0.50
    User deploy
    # Jump via bastion using netcat (no SSH forwarding needed on bastion)
    ProxyCommand ssh -W %h:%p bastion.example.com

# -W is a modern alternative to the old 'nc' trick
# Requires PermitOpen any on bastion
```

### Tor Routing

```ssh_config
Host *.onion
    ProxyCommand nc -x localhost:9050 %h %p
    StrictHostKeyChecking accept-new

# Access hidden services
Host juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion
    HostName juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion
    User admin
    Port 22
```

## LocalCommand

Run a local command after a successful SSH connection is established.

```ssh_config
# Notify on connection
Host *.production
    LocalCommand echo "Connected to %n at $(date)" >> ~/.ssh/connection.log
    PermitLocalCommand yes

# Open VS Code remote workspace on connect
Host dev-server
    HostName dev.internal
    User dev
    LocalCommand code --remote "ssh-remote+dev-server" /workspace/
    PermitLocalCommand yes

# Update terminal title
Host *
    PermitLocalCommand yes
    LocalCommand echo -ne "\033]0;%n@%h\007"
```

### LocalCommand with `Match`

```ssh_config
# Only run LocalCommand for interactive sessions
Match Exec "test -n \"$SSH_TTY\""
    PermitLocalCommand yes
    LocalCommand tmux set -g status-left "SSH: %n@%h "
```

## Canonical Hostnames

Automatically expand short names to fully qualified domain names.

```ssh_config
CanonicalDomains internal.example.com example.com
CanonicalizeHostname yes

# Now you can just type:
#   ssh web-01        ->  web-01.internal.example.com
#   ssh myserver      ->  myserver.example.com
```

## Security Hardening

```ssh_config
# Global security defaults
Host *
    # Cipher restrictions
    Ciphers chacha20-poly1305@openssh.com,aes256-gcm@openssh.com
    MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com
    KexAlgorithms curve25519-sha256@libssh.org,diffie-hellman-group16-sha512

    # Key types
    HostKeyAlgorithms ssh-ed25519-cert-v01@openssh.com,ssh-ed25519

    # No risky features
    ForwardAgent no
    ForwardX11 no
    PermitLocalCommand yes   # only if you need LocalCommand

    # Rekey for long-lived connections
    RekeyLimit 1G 3600
```

## Complete Complex Config Example

```ssh_config
# ~/.ssh/config — enterprise multi-environment setup

# --- Global defaults ---
Host *
    ServerAliveInterval 15
    ServerAliveCountMax 3
    StrictHostKeyChecking accept-new
    UserKnownHostsFile ~/.ssh/known_hosts
    AddKeysToAgent yes
    UseKeychain yes                     # macOS only

# --- Bastion hosts ---
Host bastion-prod
    HostName bastion.prod.example.com
    User jump
    IdentityFile ~/.ssh/bastion_prod_ed25519
    ControlMaster auto
    ControlPath ~/.ssh/cm/%r@%h:%p
    ControlPersist 4h

Host bastion-staging
    HostName bastion.staging.example.com
    User jump
    IdentityFile ~/.ssh/bastion_staging_ed25519

# --- Production targets ---
Host prod-web-*
    User webadmin
    IdentityFile ~/.ssh/prod_web_ed25519
    ProxyJump bastion-prod
    ForwardAgent no

Host prod-db-*
    User dba
    IdentityFile ~/.ssh/prod_db_ed25519
    ProxyJump bastion-prod
    LocalCommand echo "Connected to DB: %n" | logger -t ssh-connect
    PermitLocalCommand yes

# --- Staging targets ---
Host staging-*
    User admin
    IdentityFile ~/.ssh/staging_ed25519
    ProxyJump bastion-staging
    StrictHostKeyChecking no

# --- Developer environment ---
Host dev-*
    HostName %h.dev.internal
    User developer
    ForwardAgent yes
    LocalCommand osascript -e "display notification \"SSH connected to %n\"" 2>/dev/null
    PermitLocalCommand yes

# --- Network-dependent routing ---
Match host "*.internal" Exec "! ping -c1 -W1 10.0.0.1 >/dev/null 2>&1"
    ProxyJump external-bastion.example.com
Match host "*.internal" Exec "ping -c1 -W1 10.0.0.1 >/dev/null 2>&1"
    ProxyJump bastion-prod

# --- On-prem vs cloud detection ---
Match Exec "dig +short %h | grep -q 10\\."
    ProxyJump onprem-bastion
Match Exec "! dig +short %h | grep -q 10\\."
    ProxyJump cloud-bastion
```

## Debugging SSH Config

```shell
# Show effective config for a host
ssh -G target-host

# Show which config file lines match
ssh -G -v target-host 2>&1 | grep "^debug.*config"

# Dry run — print config without connecting
ssh -G target-host | grep -E "^(hostname|user|port|identityfile|proxy)"

# Dump full resolved config
ssh -G target-host | sort
```