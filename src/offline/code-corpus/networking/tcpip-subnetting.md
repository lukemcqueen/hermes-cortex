---
language: shell
tags: [networking, tcpip, subnet, cidr]
title: TCP/IP & Subnetting
description: Subnet masks, CIDR notation, private address ranges, and subnet calculations.
source: pattern
---

```bash
# ── Private IP Ranges ──
# Class A:   10.0.0.0/8      (10.0.0.0 – 10.255.255.255)
# Class B:   172.16.0.0/12   (172.16.0.0 – 172.31.255.255)
# Class C:   192.168.0.0/16  (192.168.0.0 – 192.168.255.255)

# ── Common CIDR Prefixes ──
# /24 = 256 hosts (254 usable)    netmask 255.255.255.0
# /16 = 65536 hosts               netmask 255.255.0.0
# /8  = 16.7M hosts               netmask 255.0.0.0
# /32 = single host

# ── Calculate subnet via ipcalc ──
ipcalc 192.168.1.0/24            # show network, broadcast, hosts
ipcalc 10.0.0.0/8                # large private range

# ── Loopback ──
# 127.0.0.0/8 — localhost (127.0.0.1 is the standard)

# ── Port ranges ──
# 0–1023:     Well-known / system ports (requires root)
# 1024–49151: Registered ports
# 49152–65535: Dynamic / ephemeral (client-side)
```
