# Runbook — push-metrics sink (port xx005)

**Repo-side fixed 2026-09-23; the host-side deploy still needs root.**
Owner: the fleet operator. Evidence from audit cycles #2778/#2779/#2793/#2794.

## Symptom

`agent-push-metrics` failed on remote hosts for weeks — HTTP 000 / connection refused to
the orchestrator's `:13005` (primary) and a peer's `:14003` (fallback). 1000+ consecutive
failures since 2026-08-30, an escalation loop (sensor → P1 ISSUE → task reopen →
governance cycle), and a cron the failure-watchdog kept pausing, all for a condition no
agent could fix without root.

## Root cause (verified, two layers)

**1. Half-wired feature.** The push **client** is universal — cron `agent-push-metrics`,
scope universal, `every 5m`, on every host. The push **sink** (the xx005 reverse proxy in
front of VictoriaMetrics) lived inside `orch-hermes-services.conf`, an opt-in bundle that
defaults to off:

```
hermes-services-apply.py:  os.environ.get("HERMES_SERVICES", "dashboard,langfuse,health")
                           needs_extra = any(svc in HERMES_SERVICES for svc in
                                             ["grafana","bus","metrics","extra","all"])
```

So 288 attempts/host/day were aimed at a port almost no host served. On the orchestrator:
`/etc/nginx/conf.d/` did not exist and the core conf served only xx001/xx002/xx004/xx007.

**2. A second, independent bug in the client.** `push_metrics()` iterated
`"${VICTORIA_URL}" "${VICTORIA_METRICS_FALLBACK_URL}"` under `set -u`, so any host
without `VICTORIA_METRICS_FALLBACK_URL` in its env **aborted with "unbound variable"**
(exit 1) before it ever sent anything. That alone produced one cron error per tick on
hosts that had no fallback configured.

## What changed in the repo (2026-09-23)

* The xx005 block moved out of the extras bundle into its own template
  `ops/install/deploy/nginx/metrics-sink.conf` — one owner for the port, no duplicate
  `listen` when extras are toggled.
* Deploy gate (`metrics_sink_decision()` in `hermes-services-apply.py`, mirrored in
  `install-nginx-full.sh`):
  * `HERMES_SERVICES` unset → deploy **iff** a local VictoriaMetrics answers
    (`CORTEX_VM_HEALTH_URL`, default `http://127.0.0.1:8428/-/healthy`). The default now
    works on hosts that have a sink and never creates a dead listener on hosts that don't.
  * `HERMES_SERVICES` set with `metrics`/`extra`/`all` → deploy (explicit).
  * `HERMES_SERVICES` set without them → do not deploy (explicit wins; if a live xx005
    block is being removed, the operator gets the drift warning).
* The client's failure accounting is bounded: first failure of an outage alerts (exit 1,
  self-diagnosing, names this runbook); later ticks inside the cooldown exit 0 with a
  suppressed line; the cooldown (6h) re-alerts; recovery clears the state. State:
  `~/.hermes-cortex/state/push-metrics.state`. A `000` alert therefore no longer means
  288 error-ticks a day, and the cron-failure watchdog never sees 3 consecutive errors.
* Unwritable state file fails closed: it alerts every run rather than silently suppressing.

## How an outage is detected now (both halves)

Push cannot report its own absence, so the alarm lives at the **sink**, not in each
agent's cron. The doctor now carries a sink-side check:

```
Metrics arrival age — 2 agent(s) pushed within 30m; arrived: Esther, Moses;
  no node_uptime_seconds sample for: moses; 4 known agent(s) not seen at this sink
  (Gisu, Joseph, Kustos, Titus) — expected if they push elsewhere or have no
  VICTORIA_METRICS_URL
```

* `check_metrics_arrival()` asks VictoriaMetrics `/api/v1/label/agent/values` and then
  `time() - timestamp(<metric>{agent="<name>"})` per agent. Read-only; no writes.
* It derives the query target from **this host's own** `VICTORIA_METRICS_URL` and
  `VICTORIA_METRICS_FALLBACK_URL` (in push order, local backend last), because the sink
  that actually receives may be a peer. A 401 is not "unreachable": the sink blocks sit
  behind htpasswd, and the credential travels as a Basic-auth header, never in output.
* Levels: agents stale past the threshold → **WARN**; sink reachable but holding no agent
  series → **INFO** with the runbook pointer (silence must never read as health); sink
  unreachable → **INFO** naming what was tried.
* Knobs: `CORTEX_VM_QUERY_URL` (pin one sink), `CORTEX_METRICS_STALE_MINUTES`
  (default 30 — six missed 5m ticks), `CORTEX_VM_FRESHNESS_METRIC`
  (default `node_uptime_seconds`).

What it showed on the first live run (2026-09-24): moses's **primary** sink
(this host's own public xx005) is refused, the fleet's live sink is a **peer's** metrics
port, and four of six registered agents have never been seen at it — their pushes are
failing outright, most likely because their fallback points at a grafana port. Fix the
primary here and the picture becomes readable in one line.

## Do this (per sink host, as root)

```bash
# 1. What is served right now?
grep -rE "listen 1[34]00[0-9]" /etc/nginx/sites-available/ /etc/nginx/conf.d/ 2>/dev/null

# 2. Confirm the backend is alive (the proxy is the only missing piece).
curl -s http://127.0.0.1:8428/-/healthy        # expect "OK"

# 3. Apply. HERMES_SERVICES is no longer required for metrics — the gate
#    auto-detects the backend. Set it only to be explicit.
sudo python3 ~/.hermes-cortex/scripts/hermes-services-apply.py
#    …or explicitly:  sudo env HERMES_SERVICES=all python3 ~/.hermes-cortex/scripts/hermes-services-apply.py

# 4. Validate BEFORE reloading — never reload a config that fails the check.
sudo nginx -t && sudo systemctl reload nginx

# 5. Verify the port is served from ANOTHER host (loopback proves nothing).
curl -sk -o /dev/null -w '%{http_code}\n' https://<sink-host>:13005/
```

`401` is a **pass** (the block requires basic auth). `000` / refused is a fail.
Then confirm the sink actually ingests: `curl -s 'http://127.0.0.1:8428/api/v1/label/agent/values'`
should list the agents that have pushed since.

## Caveats — read before running

1. **Do not enable `grafana`/`bus` extras blindly.** A host whose core conf still contains
   its own xx004 block gets a second xx004 block from the extras file → `nginx -t` fails.
   Metrics is unaffected by this now — it is no longer in that bundle.
2. **The `:14003` fallback looks wrong.** 14003 is a peer orchestrator's *grafana* port
   (xx003); its metrics proxy is **14005** (xx005) after the port-prefix translation.
   Fix that host's `VICTORIA_METRICS_FALLBACK_URL` or drop it — a wrong fallback makes a
   working primary look broken.
3. **A host with no sink at all is not broken.** Either deploy one, or unset
   `VICTORIA_METRICS_URL` in `~/.hermes-cortex/.env`: the client then exits 0 with
   "metrics push disabled (this is optional)" and records nothing.
4. `401`/`403` from the sink in the client alert is an **auth** problem (htpasswd), not a
   dead sink — the alert text says so.

## Repo-side status

* Template: `ops/install/deploy/nginx/metrics-sink.conf` (xx005 → local VictoriaMetrics).
* Gates: `metrics_sink_decision()` (python deployer) + the mirrored block in
  `install-nginx-full.sh`.
* Client: `ops/scripts/manage/agent-push-metrics.sh` (bounded alerting).
* Tests: `tests/test_runtime/test_metrics_sink_gate.py`,
  `tests/test_runtime/test_push_metrics_bounded_alerts.py`.
* Remaining work: the root deploy above, on each host that should own a sink.
