# ISWC Agent 401 — Stale API Key in Docker Image

**Date:** 2026-07-29
**Symptom:** ISWC Agent (Tomcat) returns 401 on `updateAgentRun`. Cannot process CISML transactions.

## Root Cause

The `.env` file had `ISWC_API_KEY_DEV=615b6586...` (new key), and
`app_tomcat.generated/` configs reflected it — but the Docker image was built
before the `.env` was updated. The running container had the old key
`9000cede...` baked in.

## Detection

```bash
# Location 1: Running container (old key found)
docker exec client-tomcat-1 grep api.key \
  /usr/local/soa_work_dir/iswc-agent-5.5.7/config/agent.properties
# → 9000cede3d5446d08529abf43a13c159

# Location 2: Generated config (new key)
grep api.key app_tomcat.generated/env_files/stage/iswc-agent/agent.properties
# → 615b6586308a4f928afdb1efb8acc012

# Location 3: .env source
grep ISWC_API_KEY_DEV .env
# → 615b6586308a4f928afdb1efb8acc012
```

(1) ≠ (2) → image built from stale generated files.

## Verification

```bash
# Old key → 401, new key → 4xx (gateway accepts)
curl -s -o /dev/null -w "HTTP %{http_code}" \
  -H "Ocp-Apim-Subscription-Key: $NEW_KEY" \
  "https://cisaciswcuat.azure-api.net/iswc/searchByIswc?iswc=T-000000000-0"
```

## Fix

```bash
cd /path/to/app/client-alpha
source .env
./run generate-configs
./run build tomcat
docker compose -f docker-compose.client.yml -p client up -d --remove-orphans tomcat
```

## Config Pipeline

| Step | Tool | Path |
|------|------|------|
| Template | `app_tomcat/env_files/stage/iswc-agent/agent.properties` | `${ISWC_API_KEY_DEV}` |
| Generation | `./run generate-configs` | envsubst |
| Generated | `app_tomcat.generated/env_files/stage/iswc-agent/agent.properties` | resolved value |
| Build | Dockerfile line 191 | COPY into image |
| Runtime | `/usr/local/soa_work_dir/iswc-agent-5.5.7/config/agent.properties` | in container |

## Cron Pipeline

Host cron `* * * * *` runs `client-run-client-xml-loader.sh` which chains inside the
container: XML Loader → Indexer → Checksum → Cleanup → ISWC Agent.
Lockfile at `temp/lockfile` prevents concurrent runs.
