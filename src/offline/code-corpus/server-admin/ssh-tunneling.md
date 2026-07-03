---
language: shell
tags: [ssh, networking, tunnel, security]
title: SSH Tunneling
description: SSH port forwarding, dynamic tunnels, jump hosts, reverse tunnels, ProxyJump, autossh for persistence
source: pattern
---

# SSH Tunneling

SSH tunnels create encrypted pathways through networks. Essential for accessing
services on remote networks, bypassing firewalls, and securing traffic.

## Local Port Forwarding (`-L`)

Forward a local port to a remote host:port through the SSH server.

```shell
# Forward localhost:8080 -> internal-web:80 via bastion
ssh -L 8080:internal-web:80 bastion.example.com

# Multiple forwards
ssh -L 8080:web:80 -L 5432:db:5432 bastion.example.com

# Bind to all interfaces (not just localhost)
ssh -L 0.0.0.0:8080:internal-web:80 bastion.example.com

# Bind address is optional
ssh -L 0.0.0.0:9090:localhost:9090 user@remote-host
```

**Use case**: Access an internal web dashboard or database through a jump box.

## Remote Port Forwarding (`-R`)

Forward a remote port back to a local service. The SSH server listens on
`remote_port` and forwards connections to `local_host:local_port`.

```shell
# Expose local dev server on remote host
ssh -R 9000:localhost:3000 user@public-server.example.com

# Gateway ports — allow remote server's other clients to connect
ssh -R 0.0.0.0:9000:localhost:3000 user@public-server.example.com

# Remote forwarding with restricted source
ssh -R [10.0.0.1]:9000:localhost:3000 user@public-server.example.com
```

**Use case**: Expose a local webhook receiver to the internet, or let a colleague
access your local dev server.

## Dynamic Port Forwarding (`-D` — SOCKS Proxy)

Create a SOCKS5 proxy that tunnels all traffic through the SSH server.

```shell
# Start SOCKS5 proxy on localhost:1080
ssh -D 1080 user@gateway.example.com

# With compression for slow links
ssh -C -D 1080 user@gateway.example.com

# Quiet mode, keep in foreground
ssh -N -D 1080 user@gateway.example.com
```

Configure your browser or app to use `localhost:1080` as SOCKS5 proxy. For curl:

```shell
# Route curl through the SOCKS tunnel
curl --socks5 localhost:1080 https://checkip.amazonaws.com
```

**Use case**: Browse the web from a different IP, or route traffic through a
corporate gateway to access internal sites.

## Jump Hosts (`-J`)

Chain through one or more intermediate hosts.

```shell
# Single jump host
ssh -J bastion.example.com internal-server.local

# Multiple hops
ssh -J jump1.example.com,jump2.example.com target.internal

# Jump host with different user
ssh -J user1@bastion.example.com:2222 user2@target.internal

# Nested jumps (each hop requires auth)
ssh -J bastion.example.com -J internal-bastion.local web.internal
```

**Use case**: Reach a server that sits behind multiple layers of network
segmentation.

## ProxyJump Config (`~/.ssh/config`)

Configure jump hosts permanently in SSH config.

```ssh_config
# ~/.ssh/config

# Simple jump
Host internal-web
    HostName 10.0.1.50
    User deploy
    ProxyJump bastion.example.com

# Multi-hop jump
Host db-primary
    HostName db.internal.example.com
    User dba
    ProxyJump bastion.example.com,internal-bastion.local

# Custom port on jump host
Host staging
    HostName 10.0.2.100
    User admin
    ProxyJump [bastion.example.com]:2222

# ProxyJump with identity file on jump
Host production
    HostName prod-01.example.com
    User root
    ProxyJump bastion
    IdentityFile ~/.ssh/prod_key

Host bastion
    HostName bastion.example.com
    User jumphost
    IdentityFile ~/.ssh/bastion_key
    Port 22
```

## Reverse Tunnel with autossh (Persistent)

autossh restarts tunnels automatically on connection drop.

```shell
# Install autossh
brew install autossh          # macOS
apt install autossh           # Debian/Ubuntu

# Basic persistent reverse tunnel
autossh -M 0 -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" \
  -R 9000:localhost:3000 -N user@public-server.example.com

# With monitoring port (-M is deprecated, use -o ServerAliveInterval instead)
autossh -M 0 \
  -o "ServerAliveInterval 10" \
  -o "ServerAliveCountMax 2" \
  -o "ExitOnForwardFailure yes" \
  -R 8080:localhost:8080 \
  -N tunnel-user@public.example.com
```

### systemd Service for autossh

```ini
# /etc/systemd/system/webhook-tunnel.service
[Unit]
Description=Persistent SSH reverse tunnel for webhook
After=network.target

[Service]
Type=simple
User=tunnel
ExecStart=/usr/bin/autossh -M 0 \
  -o "ServerAliveInterval 30" \
  -o "ServerAliveCountMax 3" \
  -o "ExitOnForwardFailure yes" \
  -o "StrictHostKeyChecking accept-new" \
  -i /home/tunnel/.ssh/tunnel_key \
  -R 8080:localhost:8080 \
  -N tunnel-user@public.example.com
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```shell
sudo systemctl daemon-reload
sudo systemctl enable --now webhook-tunnel.service
sudo systemctl status webhook-tunnel.service
```

### Launchd for macOS (autossh as service)

```xml
<!-- ~/Library/LaunchAgents/com.user.webhook-tunnel.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.webhook-tunnel</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/autossh</string>
        <string>-M</string>
        <string>0</string>
        <string>-o</string>
        <string>ServerAliveInterval=30</string>
        <string>-N</string>
        <string>-R</string>
        <string>9000:localhost:3000</string>
        <string>tunnel-user@public.example.com</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
```

```shell
launchctl load ~/Library/LaunchAgents/com.user.webhook-tunnel.plist
launchctl start com.user.webhook-tunnel
```

## SSH Config for Tunneling

```ssh_config
# ~/.ssh/config — tunnel-oriented config

# Keep connections alive
Host *
    ServerAliveInterval 30
    ServerAliveCountMax 3
    ExitOnForwardFailure yes
    TCPKeepAlive yes

# SOCKS proxy tunnel
Host socks-proxy
    HostName gateway.example.com
    User proxy-user
    DynamicForward 1080
    Compression yes
    CompressionLevel 6
    # Keep the tunnel open without a shell
    RequestTTY no
    SessionType none

# Reverse tunnel alias
Host tunnel-reverse
    HostName public.example.com
    User tunnel
    IdentityFile ~/.ssh/tunnel_ed25519
    RemoteForward 9000 localhost:3000
    RemoteForward 9090 localhost:9090
    SessionType none
    ExitOnForwardFailure yes
```

## Security Considerations

```shell
# Limit forwarded ports per user in /etc/ssh/sshd_config
Match User tunnel
    PermitListen 0.0.0.0:9000
    PermitOpen 10.0.0.50:3000 10.0.0.50:5432
    AllowTcpForwarding remote

# Disable TCP forwarding for non-tunnel users
Match User !tunnel
    AllowTcpForwarding no

# Restrict tunnels to specific source IPs
PermitListen 10.0.0.0/8

# Disable agent forwarding in production (forwarding in general)
ForwardAgent no
AllowAgentForwarding no

# Use ed25519 keys for tunnel services
ssh-keygen -t ed25519 -a 100 -f ~/.ssh/tunnel_ed25519 -C "tunnel@$(hostname)"
```

## Quick Reference

| Command | Purpose | Common Flag |
|---------|---------|-------------|
| `ssh -L` | Local port forward | Listens on client |
| `ssh -R` | Remote port forward | Listens on server |
| `ssh -D` | SOCKS5 dynamic forward | `-D 1080` |
| `ssh -J` | Jump host | Chain with commas |
| `ssh -N` | No remote command | For tunnels only |
| `ssh -C` | Compression | Slow links |
| `ssh -f` | Background after auth | Combined with `-N` |
| `ssh -v` | Verbose | Debug tunnel setup |

Test connectivity before investing in automation:

```shell
ssh -v -N -L 8080:target:80 bastion.example.com
# Check for "Entering interactive session" and "local forwarding listening"
```