---
name: wan-reachability-probing
description: Test port reachability from internet via external probes.
version: 0.1.0
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
---

# WAN Reachability Probing

Verify whether a port/service is actually reachable from the internet when your test host sits inside the same LAN as the target — or when a peer reports you unreachable but local checks look fine.

## When to Use

- "Can't reach the router admin / service from outside the LAN"
- A peer agent reports you unreachable, but the local process and nginx look healthy
- After changing port forwards, DDNS records, or router remote-access settings
- Any "is this port open from the internet?" question where your test vantage is behind the same NAT as the target

## The Hairpin NAT Trap (read first)

Curling your own public IP or DDNS from inside the LAN is **inconclusive**: most routers don't support NAT hairpin, so even a perfectly OPEN port returns HTTP 000/timeout from inside. A 000 from a hairpin test is NOT evidence of a closed port. Verified 2026-08-30: `curl https://<PUBLIC_IP>:8443/` from inside → 000, while external nodes reported 443/14007/11022 OPEN at the same moment.

## Procedure

### 1. LAN liveness (fast sanity)
Ping the target, then curl the LAN endpoint. `401`/`200` means the service is up locally; a LAN-side `000` IS meaningful (service/router down).

### 2. DDNS / public-IP currency
`dig +short <ddns-domain> A` must equal `curl -s https://api.ipify.org`. A stale A record is a top "can't connect" cause even when everything else is healthy.

### 3. External probe — check-host.net free API (no key, scriptable)
yougetsignal-style web port checkers are Cloudflare-blocked (301). Use:

```bash
req=$(curl -s -H "Accept: application/json" "https://check-host.net/check-tcp?host=<PUBLIC_IP>:<PORT>&max_nodes=3" | python3 -c "import sys,json;print(json.load(sys.stdin)['request_id'])")
sleep 6   # nodes report asynchronously
curl -s -H "Accept: application/json" "https://check-host.net/check-result/$req"
```

Result shape per node:
- `[{"address": ..., "time": 0.3}]` = **OPEN**
- `[{"error": "Connection timed out"}]` = **CLOSED**

Poll multiple nodes; majority rules.

### 4. Interpret the matrix

| Probe pattern | Meaning |
|---|---|
| ALL probed ports CLOSED | WAN-level problem: ISP block, router firewall, or remote admin disabled |
| Some OPEN, some CLOSED | CLOSED ones are target-side (unforwarded, service down, host firewall); the router WAN path works |
| One port CLOSED, siblings OPEN | That specific host/service, not the router (2026-08-30: WAN:10022 peer-SSH down while 11022 SSH open) |
| Forwards OPEN but router-admin ports (8443/8080/444/81) CLOSED | FreshTomato remote admin disabled — enable *Administration → Access → Remote Access*, then reach at `https://<ddns>:8443` |

## Pitfalls

- Never conclude "not externally accessible" from a hairpin 000 — get an external node's result first.
- check-host.net nodes answer asynchronously: `sleep ~6` before polling the result.
- Empty result (no `request_id`) = API rate-limited or transient — retry once.
- Probe the suspect port AND a known-good sibling port in the same pass; the contrast splits "router problem" vs "target problem" in one round.

## Verification

A probe pass is verified when ≥1 external node returns a structured result (OPEN or timed-out) — an empty/no-result JSON proves nothing.

## Related

- `health-external-verification` (user-owned): health-endpoint-specific external testing — overlaps with this skill; curator should consolidate.
- `fresh-tomato-router` (user-owned): router nvram, port-forward rules, remote-admin enable — its Verification section has the same hairpin trap.

Worked example: `references/wan-reachability-probe-example.md`.
