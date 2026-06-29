---
language: shell
tags: [networking, diagnostics, troubleshooting, tcpdump, ss]
title: Network Diagnostics
description: Ping, traceroute, ss, netstat, lsof, tcpdump for debugging connectivity.
source: pattern
---

```bash
# ── ICMP / Connectivity ──
ping -c 4 8.8.8.8               # basic reachability
ping -c 4 example.com           # DNS resolution + reachability
traceroute example.com          # path to destination (UDP by default)
traceroute -I example.com       # ICMP traceroute
mtr example.com                 # continuous traceroute (combines ping + trace)

# ── Socket / Port inspection ──
ss -tln                         # all listening TCP ports
ss -tuln                        # all listening TCP + UDP
ss -tup                         # active connections with process
ss -tlnp                        # listening + process (requires root)

netstat -tuln                   # legacy socket listing
netstat -rn                     # routing table

lsof -i :80                     # what's listening on port 80
lsof -iTCP -sTCP:LISTEN        # all listening TCP sockets
lsof -i @1.2.3.4               # connections to/from specific IP

# ── Packet capture (requires root) ──
tcpdump -i eth0                 # all traffic on interface
tcpdump -i eth0 port 80        # HTTP traffic only
tcpdump -i eth0 host 1.2.3.4  # traffic to/from host
tcpdump -i eth0 -w capture.pcap # write to file
tcpdump -r capture.pcap         # read from file
tcpdump -X                      # hex + ASCII output
```
