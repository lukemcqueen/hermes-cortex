# Health Endpoint Throttle → False "Moses Unreachable" (2026-10-04)

## Symptom

Every worker agent's `cortex-bus-failover-watchdog` recurringly emitted a
`⚠️ Moses (primary bus) unreachable — traffic now routes via Esther :14004`
followed ~5 min later by `✅ Moses (primary bus) reachable again`. Observed at
the top of `:00` and `:30` each hour (e.g. 10:00 / 11:00). Not a real outage.

## Root cause

Moses' nginx **health server (port :13007) rate-limits the fleet's own health
probes** at their synchronized 5-min / 30-min watchdog tick boundaries.

The deployed health server block applied tight per-client-IP limits:

```nginx
limit_conn conn_limit 10;                       # max 10 concurrent conns/IP
limit_req  zone=general burst=10 nodelay;       # rate-limit burst 10
```

All fleet agents reach Moses through one *aggregated* source per path: the
router NAT IP (a private `192.168.1.x` gateway) for LAN hosts and one external
public client IP for the WAN workers. When every agent's watchdog fires at the same `:00`/`:30`
boundary, their combined probes exceed `conn_limit 10` / `burst 10`, so nginx
returns **503** (rate-limited) or **499** (client's 8 s `urlopen` timeout fired
while its connection queued behind `conn_limit`). The watchdog treats any
non-200/401/403 as "down", reports "Moses unreachable", then "reachable" on the
next tick — the flapping pair.

## Evidence (`/var/log/nginx/health-access.log`)

- `503`/`499` rows fire at exactly `:00:xx` and `:30:xx` every hour
  (e.g. `10:00:09`, `10:00:10` → alert at `10:00:12`; `11:00:10` → alert at
  `11:00:11`).
- The throttled clients are **only fleet-monitoring user agents**:
  `Python-urllib/3.x` (the watchdog), `hermes-fleet-watchdog/1.0`,
  `hermes-health-report/1.0`.
- ~84× `499` + 18× `503` in the last 24 h out of ~1500 hits (~6 % of probes).
- The health backend (`127.0.0.1:8905`) answers in ~0.2 s — the delay is purely
  nginx throttling, **not** the health-vector service.

## Fix

### 1. Allowlist the fleet's IPs to bypass the DDoS limits (canonical fix)

nginx applies **no limit when a limit zone's key variable is empty**. Key the
rate/conn zones off a `geo` allowlist so the fleet's probes bypass the tight
limits entirely, while everyone else keeps the public DDoS ceiling.

Live config `/etc/nginx/hermes-zone-defs.conf` — add the `geo` map and re-key
the three zones:

```nginx
geo $limit_bypass {
    default          $binary_remote_addr;
    192.168.1.0/24   "";     # LAN fleet (router NAT aggregate)
    115.21.71.146    "";     # external WAN worker
    127.0.0.0/8      "";     # localhost
}
limit_req_zone  $limit_bypass zone=general:10m rate=20r/s;
limit_req_zone  $limit_bypass zone=auth:10m   rate=5r/s;
limit_conn_zone $limit_bypass zone=conn_limit:10m;
```

An allowlisted IP gets an **empty** zone key → nginx applies no limit. The
health server block keeps its tight `conn_limit 10` / `burst 10` as the real
public ceiling: the fleet bypasses it, a DDoS attacker does not. Add a new
worker/agent IP to the `geo` map when it joins off-LAN.

Then apply:

```bash
sudo cp ~/hermes-cortex/ops/install/deploy/nginx/hermes-zone-defs.conf /etc/nginx/hermes-zone-defs.conf
sudo nginx -t && sudo systemctl reload nginx
```

> The earlier approach — *raising* the health block's limits (e.g. burst/conn
> 200) — is **superseded**. It weakens the DDoS ceiling for the public and is
> unnecessary: the allowlist gives the fleet unlimited access without relaxing
> anything for everyone else.

### 2. Source-of-truth (repo)

- `ops/install/deploy/nginx/hermes-zone-defs.conf` carries the
  `geo $limit_bypass` allowlist — this is the actual fix.
- `ops/install/deploy/nginx/hermes-services.conf` health block keeps its tight
  limits — do **not** relax it.
- Live `/etc/nginx` had drifted tighter than the templates and was never
  re-deployed by `cortex-update` (that step needs root), which is why the
  earlier doc-only round didn't take.

### 3. Watchdog debounce (complementary noise suppression)

Commit `84794f85`: the worker `cortex-bus-failover-watchdog.py` now alarms only
after **2 consecutive** failed probes and recovers only after **3 consecutive**
successes, so a single transient blip no longer spams the channel. This stops
the alert noise; step 1 stops the actual throttling.

## Verification

After `nginx -s reload`, confirm health probes return 200 continuously and no
`503`/`499` burst remains at the `:00`/`:30` boundary:

```bash
tail -500 /var/log/nginx/health-access.log | awk '{print $9}' | sort | uniq -c
# expect: only 200 (no 499/503)
```

## Related

- `docs/runbooks/push-metrics-nginx-deploy.md` — the sibling `:13005`
  metrics-sink (same "bundled but never deployed on the host" class of issue;
  `metrics-sink.conf` is not loaded on this host either).