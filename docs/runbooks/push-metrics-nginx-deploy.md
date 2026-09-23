# Runbook — deploy the push-metrics reverse proxy (port xx005)

**Status: needs root (not runnable by an agent without passwordless sudo).**
Owner: the fleet operator. Prepared from live evidence 2026-09-23 by moses (audit cycles #2778/#2779).

## Symptom

`agent-push-metrics` fails every run — HTTP 000 / connection refused to the orchestrator's
`:13005` (primary) and the peer's `:14003` (fallback). The cron has failed 1000+
consecutive runs since 2026-08-30, and the paused ISSUES tasks on orchestrator hosts all
trace back to it.

## Root cause (verified)

The push-metrics reverse proxy is defined **only** in the opt-in extras template
`ops/install/deploy/nginx/orch-hermes-services.conf` (App 5, `xx005` →
`127.0.0.1:8428`, i.e. VictoriaMetrics). That file is deployed to `conf.d/` **only when
the host's environment opts in**:

```
hermes-services-apply.py:  hermes_services = os.environ.get("HERMES_SERVICES", "dashboard,langfuse,health")
                           needs_extra = any(svc in hermes_services for svc in ["grafana","bus","metrics","extra","all"])
```

Evidence on the orchestrator host:

* `/etc/nginx/conf.d/` **does not exist** — the extras file was never deployed.
* `/etc/nginx/sites-available/hermes-services.conf` serves xx001 / xx002 / xx004 / xx007 —
  **no xx005**.
* The repo's extras template does define xx005 (`listen 13005 ssl;` → `metrics_backend`).

So the config exists in the repo; the host simply never enabled it. A container/VM
restart does **not** fix this (that proposal was correctly refused — the VM is healthy).

## Do this (per host, as root)

```bash
# 1. What is actually served right now?
grep -rE "listen 1[34]00[0-9]" /etc/nginx/sites-available/ /etc/nginx/conf.d/ 2>/dev/null

# 2. Check the opt-in gate for THIS host.
#    Orchestrators must include bus + metrics (+ grafana) or 'all'.
echo "$HERMES_SERVICES"        # empty ⇒ extras are DISABLED on this host

# 3. Apply the nginx config with extras enabled (run from the deployed cortex home).
sudo env HERMES_SERVICES=bus,metrics,grafana \
  python3 ~/.hermes-cortex/scripts/hermes-services-apply.py

# 4. Validate BEFORE reloading — never reload a config that fails the check.
sudo nginx -t && sudo systemctl reload nginx

# 5. Verify the port is really served (from another host, not loopback).
curl -sk -o /dev/null -w '%{http_code}\n' https://<orchestrator-host>:13005/   # primary
curl -sk -o /dev/null -w '%{http_code}\n' https://<peer-orchestrator-host>:14005/  # fallback host
```

401 is a **pass** (the block requires basic auth). `000` / connection refused is a fail.

## Caveats — read before running

1. **Do not enable extras blindly on a host whose core conf already defines the bus.**
   `sites-available/hermes-services.conf` on the orchestrator currently contains an
   `agent_bus_backend` (xx004) block that the *current* repo template no longer has. If
   extras are enabled, the extras file adds its own `xx004` block → two blocks on one
   port → `nginx -t` fails. Check step 1 first; if xx004 appears in both, remove the
   duplicate block from the core conf in the same edit.
2. **Removing extras takes the bus down.** `hermes-services-apply.py` now prints a loud
   drift warning (2026-09-23) when it disables extras while the core conf no longer
   defines bus/grafana/metrics. If you see that warning, stop and reconcile.
3. **The `:14003` fallback in the push script looks wrong.** 14003 is the peer
   orchestrator's *grafana* port (xx003); the metrics proxy there is **14005** (xx005).
   Fix the fallback URL after the port is live, or the client keeps failing even though
   the proxy works.
4. VictoriaMetrics itself listens on `127.0.0.1:8428` — the proxy is the only thing
   missing. `curl -s http://127.0.0.1:8428/-/healthy` on the host confirms the backend.

## Repo-side status

* Config present: `ops/install/deploy/nginx/orch-hermes-services.conf` (App 5 / xx005).
* Deploy gate hardened: `ops/install/deploy/nginx/hermes-services-apply.py` warns on the
  silent-removal path (2026-09-23).
* Nothing else in the repo needs to change for this port to exist — the remaining work is
  the root deploy above.
