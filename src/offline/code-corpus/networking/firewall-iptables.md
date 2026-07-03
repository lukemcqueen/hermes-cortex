---
language: shell
tags: [networking, firewall, iptables, nftables, security]
title: Firewall with iptables/nftables
description: Packet filtering, NAT, port forwarding, and rule management with iptables and nftables.
source: pattern
---

```bash
# ── iptables basics ──
iptables -L -n -v              # list all rules with counters
iptables -S                    # list rules as commands (restorable)

# ── Default policies ──
iptables -P INPUT DROP         # drop all inbound by default
iptables -P FORWARD DROP       # drop all forwarding
iptables -P OUTPUT ACCEPT      # allow all outbound

# ── Common rules ──
iptables -A INPUT -i lo -j ACCEPT                    # loopback
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT  # established
iptables -A INPUT -p tcp --dport 22 -j ACCEPT        # SSH
iptables -A INPUT -p tcp --dport 80 -j ACCEPT        # HTTP
iptables -A INPUT -p tcp --dport 443 -j ACCEPT       # HTTPS

# ── NAT / Port forwarding ──
iptables -t nat -A PREROUTING -p tcp --dport 80 \
  -j DNAT --to-destination 10.0.0.5:8080              # forward 80 → internal

# ── Save / restore ──
iptables-save > /etc/iptables/rules.v4               # persist rules
iptables-restore < /etc/iptables/rules.v4            # restore rules

# ── nftables (modern replacement) ──
nft list ruleset                  # show all rules
nft add rule inet filter input tcp dport 22 accept   # allow SSH
nft add table inet filter                              # create table
nft add chain inet filter input { type filter hook input priority 0 \; }
nft add rule inet filter input ct state established,related accept
nft add rule inet filter input iif lo accept
```
