# SearXNG — the measured minimum, and what it costs

Settings for a **private, single-agent** instance. Every number below was measured on esther
(2026-10-13, `searxng/searxng:latest`) — not taken from a sizing table.

## Measured

| Configuration | Memory cap that works | Measured RSS | Results for a real query |
|---|---|---|---|
| Default engine set, one worker | 128 MB (**96 MB DIES**) | **~99 MB** | **20** — but `brave` and `duckduckgo` unresponsive |
| Pruned to 3 engines (`keep_only`) | 96 MB | **82.3 MB** | **0** ❌ — 2 of the 3 were blocked |
| 64 MB cap | — | — | container exits: `Unexpected exit from worker-1` |

**50 MB is not reachable.** The floor is ~82 MB, and the one configuration that fits under 100 MB
returns nothing at all on this host.

Two things worth knowing before choosing sizes:

1. **The current image runs Granian, not uWSGI.** `searxng/searxng:latest` starts Granian, so
   `UWSGI_WORKERS=1` (the env var most guides recommend) is **ignored**. The worker count is still
   the memory driver — the maintainers' own thread reports 600 MB → 150 MB going from `workers=%k`
   to `workers=1` — but on this image the lever moved.
2. **Memory and usefulness move together.** Pruning engines is the only lever that gets under
   100 MB, and the engines you prune are the coverage you lose. Here `brave` and `duckduckgo` are
   already unresponsive from this IP, so a small engine set is a search engine that finds nothing.
   **~99 MB is the smallest configuration that actually returns results** — SearXNG earns its
   footprint by failing over across ~70 engines, and pruning removes exactly that.

## The config these numbers describe

`settings.yml` (all of it is necessary; the defaults for `limiter`/`public_instance`/`image_proxy`
are already `false`, and `valkey: url: false` is what keeps Valkey out of the deployment):

```yaml
use_default_settings: true          # keep the full engine set (see above)
server:
  secret_key: "<generate: openssl rand -hex 32>"
  limiter: false                    # private instance
  public_instance: false
  image_proxy: false
search:
  formats: [html, json]             # json is what an agent calls
valkey:
  url: false                        # no Valkey service needed
```

`compose.yaml` — cap it at 128 MB, bind to loopback only:

```yaml
services:
  searxng:
    image: searxng/searxng:latest
    ports: ["127.0.0.1:8888:8080"]
    mem_limit: 128m
    restart: unless-stopped
    volumes: ["./settings.yml:/etc/searxng/settings.yml:ro"]
    environment:
      GRANIAN_WORKERS: "1"          # NOT UWSGI_WORKERS: this image runs Granian
```

Then point any agent at it:

```bash
export SEARXNG_URL=http://127.0.0.1:8888
fleet-search search "your query" --json
```

## What an agent should be told

SearXNG's JSON includes **`unresponsive_engines`**. With results it is informational; with ZERO
results it is the difference between *"nothing matched"* and *"the engines that could answer were
blocked"* — and only one of those is worth retrying. Measured here: `brave`, `duckduckgo`, and
sometimes `wikidata` are unresponsive from a datacenter IP.
