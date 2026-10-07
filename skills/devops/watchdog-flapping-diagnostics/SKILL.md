---
name: watchdog-flapping-diagnostics
description: "Watchdog flapping: nginx throttle of fleet probes; debounce."
version: 1.0.0
category: devops
author: Hermes Cortex
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [watchdog, health, flapping, nginx, failover, diagnostics]
---

# Health / Watchdog Flapping Diagnostics

## When to Use

A health or failover watchdog (e.g. `cortex-bus-failover-watchdog.py` workers, a
fleet-health probe, a push-metrics health check) flips between "unreachable" and
"reachable again" on a repeated, fixed cadence. Examples that fire this skill:
- An alert+recovery pair delivered back-to-back, recurring every :00/:30 of the hour
  or every 5-min tick.
- "Primary bus unreachable" followed minutes later by "routing restored", on a loop.

## First Principle — it is almost never the network

A real outage does NOT self-heal within one watchdog tick. So a periodic
alert-then-recover pattern is NEVER "flaky network" — the probe is seeing a
SERVING-LAYER failure (nginx throttle) that flips between two probes. Investigate
the nginx health endpoint, not the route or the backend service.

## Step 1 — read the serving health-access.log, not the backend

The probe hits the service through nginx. The intermittent status codes are in the
health access log:

```bash
tail -2000 <health-access.log> | awk '{print $9}' | sort | uniq -c | sort -rn
```

Interpret:
- **499** = client closed the connection before nginx replied — the probe's client
  timeout (urllib default 8s) fired while nginx queued the request. With a fast
  backend, 499s are the signature of nginx throttling, not a slow service.
- **503** = nginx rate-limit returned (`limit_req ... nodelay` returns 503 when the
  burst is exceeded; `limit_conn` queues/closes excess).
- Overlay the 499/503 timestamps on the watchdog tick cadence — they line up to the
  second (`10:00:09` nginx 499 ↔ `10:00:12` worker alert).

Confirm it is the fleet's OWN probes being throttled (not an attacker):
```bash
tail -2000 <health-access.log> | grep -E ' (499|503) '          # then group by:
  | awk '{print $NF}'          # User-Agent: Python-urllib/*, hermes-fleet-watchdog, hermes-health-report
  | awk '{print $1}'           # remote addr: the NAT gateway IP dominates
```

Then prove the backend is healthy in parallel: `curl` the upstream directly
(~0.2s = fine). A fast backend + 499s = nginx is the throttle.

## Step 2 — understand the mechanism (why it throttles)

nginx rate/conn limits are keyed per client IP. Fleet agents reach the host through a
NAT gateway, so MANY agents collapse into ONE source IP (the router/gateway LAN
address, or one external ISP IP). When their watchdogs probe in the same
synchronized tick, the aggregate exceeds the health block's `limit_conn
conn_limit N` + `limit_req ... burst=N` → 503/499. The watchdog treats any
non-200/401/403 as **down**, so one throttled probe = false "unreachable".

## Step 3 — fix at the source

- **PREFERRED — allowlist the fleet so it bypasses the limits entirely**, via the
  empty-key trick, instead of relaxing limits for everyone: nginx applies NO rate
  or conn limit when the limit_zone key variable is empty. Key the zones off a
  `geo` map that yields `""` for trusted fleet IPs and `$binary_remote_addr` for
  everyone else. The fleet gets unlimited probes; the public keeps the tight burst
  / conn ceiling as a real DDoS defence. Add a worker IP to the map when it joins
  off-LAN:
  ```nginx
  geo $limit_bypass {
      default          $binary_remote_addr;
      192.168.0.0/16   "";     # LAN fleet (router NAT aggregate)
      <wan-worker-ip>  "";     # external WAN worker
      127.0.0.0/8      "";     # localhost
  }
  limit_req_zone  $limit_bypass zone=general:10m rate=20r/s;
  limit_conn_zone $limit_bypass zone=conn_limit:10m;
  ```
  Only the zone key changes — no server-block edits. Validate it before shipping:
  parse-check with `nginx -t -c <minimal-http-conf> -p <writable-prefix> \`
  `-g 'pid <prefix>/nginx.pid; ...'` (override the root pid/access_paths via -g or
  the parse fails on permissions, not config), and run that throwaway nginx to
  confirm an allowlisted IP returns 200 instead of 503 under a burst. Raising
  burst/conn for everyone is the fallback when allowlisting isn't feasible, but it
  weakens the public ceiling.
- **The live /etc/nginx is commonly root-owned and stale** — a fix in the repo
  template will NOT reach production without a privileged apply. On a host where
  the agent lacks sudo for /etc/nginx, write the EXACT operator command
  (`sudo cp <repo>/ops/install/deploy/nginx/<conf> /etc/nginx/<conf> && sudo
  nginx -t && sudo systemctl reload nginx`) into the report and flag that the
  change will not take effect until that runs. Shipping the fix and declaring it
  done while /etc/nginx still throttles is exactly how this class recurs.
- **Compare /etc/nginx against the repo nginx template FIRST**
  (`ops/install/deploy/nginx/` for a cortex install). A drifted/stale deploy can
  carry tighter limits than the source, and a routine `cortex-update --force` will
  NOT refresh it unless the nginx deploy step actually runs. Diff deployed vs repo
  before assuming the running limits are intentional.
- This is a crown-jewel security config: edit the repo template, deploy through the
  real nginx deploy path, run `nginx -t`, reload — never hand-edit /etc/nginx.

## Design rule — debounce alert and recovery

A health/failover watchdog's ALERT must require N consecutive failures and its
RECOVERY M consecutive successes. A path that alerts on the 1st failure and
recovers on the 1st success turns any single transient blip — throttle, timeout, or
retry — into an alert+recovery pair (the flapping noise). Mirror the orchestrator
pattern (activate only after 3 consecutive failures + elapsed time; recover only
after 3 consecutive successes) on every worker/degraded path. A debounce makes the
system robust to ANY future transient probe failure, so you fix the class, not just
today's throttle.

## Pitfalls

- Don't call it network flakiness because the probe source varies — NAT collapses
  many agents to one IP, so "different IPs" still share one nginx rate bucket.
- Don't run `curl http://127.0.0.1:<port>/health` on a TLS-only nginx listener and
  read the `400` as a service fault — plain HTTP to an `ssl` listener returns 400
  (and a closed port returns 000/connection refused). Probe over `https` (or the
  backend directly) for a truthful status.
- Throttling that only ever hits your OWN monitoring UAs (Python-urllib, the fleet
  watchdog) is the tell — an attacker would show many unknown/bot UAs.
