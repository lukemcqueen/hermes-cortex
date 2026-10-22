# Docker Container Crash-Loop: JS Heap OOM

## Case Study: langfuse-web (3.206.0 → 3.218.0)

### Failure Signal

- Cron `langfuse-health-watchdog` reports `last_status=error`:
  ```
  🌐 Web:
  Langfuse web check failed: Remote end closed connection without response
  ```
- Container status cycles: `Up N seconds (health: starting)` → restart → repeat
- `docker inspect` shows `RestartCount: 8118`, `ExitCode: 0`, `OOMKilled: false`

### Root Cause

JavaScript heap runs out of memory under container cgroup limit:

```
FATAL ERROR: Ineffective mark-compacts near heap limit Allocation failed - JavaScript heap out of memory

--- Last few GCs ---
[7:0x71c97e0ae000]    40265 ms: Scavenge 749.6 (769.2) -> 748.5 (790.2) MB
[7:0x71c97e0ae000]    41565 ms: Mark-Compact (reduce) 754.1 (790.2) -> 733.0 (751.7) MB
```

The Langfuse Next.js server needs ~750MB+ heap. With `--max-old-space-size=512` and container `mem_limit: 1g`, the old-space fills within ~40s, Node crashes, Docker restarts (unhelpfully with `restart: unless-stopped`).

### Fix Applied

| Setting | Before | After |
|---|---|---|
| Image tag | `langfuse/langfuse:3.206.0` | `langfuse/langfuse:3` (3.218.0) |
| Custom command override | `/bin/sh -c 'exec node ./web/server.js --keepAliveTimeout 110000'` | Removed (uses image default CMD) |
| `mem_limit` / `memswap_limit` | 1g / 1g | 2g / 2g |
| `NODE_OPTIONS --max-old-space-size` | 512 (image default, compose override wasn't applying to old image) | 1536 |
| `NODE_OPTIONS --max-semi-space-size` | 64 | 128 |

### Watchdog Script Fix

The health check function used `urllib.request.urlopen()` which had a connectivity issue with `localhost` in the Hermes venv (times out when `curl` works). Rewrote to use `subprocess.run(["curl", ...])` with the health endpoint `http://127.0.0.1:3000/api/public/health`.

### Verification

```bash
python3 ~/.hermes/scripts/langfuse-health-watchdog.py    # exit 0 = silent (healthy)
curl -s http://127.0.0.1:3000/api/public/health          # {"status":"OK","version":"3.218.0"}
docker inspect langfuse-langfuse-web-1 --format '{{.State.Health.Status}} {{.RestartCount}}'
# healthy 0
```

### Key Lessons

1. **Never trust exit code 0 on a crash-looping container** — the process exits cleanly, Docker restarts it. The real signal is `RestartCount` climbing and logs showing GC pressure.
2. **`docker logs` is the first place to check** for `FATAL ERROR`, `FATAL`, or GC trace lines.
3. **Check that docker-compose env overrides actually apply** — old image had hard-coded `NODE_OPTIONS` in Dockerfile that overrode the compose value. Upgrading the image resolved the env override.
4. **Custom `command:` overrides should be minimal** — the default CMD from the image is usually correct. Only override when you know why the default doesn't work.
5. **urllib vs curl**: In the Hermes venv, `urllib.request.urlopen("http://localhost:...")` can time out while `curl` and `urllib.request.urlopen("http://127.0.0.1:...")` work. When a watchdog script using urllib fails but curl succeeds, switch the script to `subprocess.run(["curl", ...])`.
