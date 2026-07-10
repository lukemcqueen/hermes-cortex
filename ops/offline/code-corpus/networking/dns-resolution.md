---
language: shell
tags: [networking, dns, resolution, bind, lookup]
title: DNS Resolution & Troubleshooting
description: DNS lookup tools, record types, resolution order, and debugging.
source: pattern
---

```bash
# ── DNS Record Types ──
# A:     IPv4 address
# AAAA:  IPv6 address
# CNAME: Canonical name (alias)
# MX:    Mail exchanger
# TXT:   Arbitrary text (SPF, DKIM, verification)
# NS:    Nameserver
# SOA:   Start of Authority

# ── Query tools ──
dig example.com A               # query A record
dig example.com MX              # mail servers
dig example.com ANY             # all records
dig +short example.com          # compact output

nslookup example.com            # legacy tool, still useful
nslookup example.com 8.8.8.8   # query specific DNS server

host example.com                # simple forward lookup
host 1.2.3.4                    # reverse DNS lookup

# ── Resolution order ──
# 1. /etc/hosts                  (static overrides)
# 2. /etc/resolv.conf            (DNS servers, search domains)
# 3. nscd / systemd-resolved     (caching daemon)

# ── Trace the full path ──
dig +trace example.com          # follow root → TLD → authoritative
```
