# SearXNG — the measured minimum

Settings for a **private, single-agent** instance. Every number here was measured on esther
(2026-10-13, `searxng/searxng:latest`) by `measure.sh` beside this file — re-run it and you get the
same table. **The design rationale lives in `docs/design/agent-search.md`; this file is the config
and the numbers.**

## Measured

Steady state (measured after the instance served queries AND again 20 s later — a container that
only survives startup is not a working provider):

| Configuration | Steady RSS | Usable as a search provider? |
|---|---|---|
| Full engine set, one worker | **~124 MiB** | **yes** — 20 results; `brave` + `duckduckgo` unresponsive |
| Pruned to 3 engines (`keep_only`) | **~92 MiB** | **NO** — 0 results |
| Full set + `UWSGI_WORKERS=4` | ~124 MiB, still **one** python process | n/a — **the variable is inert** on this image |

**50 MB is not reachable.** The floor is ~92 MiB, and the configuration that fits there returns
nothing. The smallest configuration that actually **works** is **~124 MiB**.

Earlier numbers in this file said 99 MB / 82 MB; those were taken ~25 s after start, before the
instance had served anything. The steady-state figures above are the ones to size against.

Two things a sizing table will not tell you:

- **The image runs Granian, not uWSGI.** `UWSGI_WORKERS=1` — what most guides recommend — does
  nothing here. One worker is still the difference between ~100 MB and ~600 MB, but the lever is
  `GRANIAN_WORKERS`.
- **Pruning engines buys memory with coverage**, and here it buys *nothing usable*: `brave` and
  `duckduckgo` are unresponsive from a datacenter IP, so a small engine set is a search engine that
  finds nothing. SearXNG earns its ~99 MB by failing over across ~70 engines.

## The config these numbers describe

`settings.yml` (see the file for the annotated version):

```yaml
use_default_settings: true          # keep the full engine set on purpose
server:
  secret_key: "<openssl rand -hex 32>"
  limiter: false                    # private instance — and this is what keeps Valkey out
  public_instance: false
  image_proxy: false
search:
  formats: [html, json]
valkey:
  url: false                        # no Valkey service
```

The `limiter: false` line is load-bearing: with it **on**, SearXNG logs
`ERROR:searx.limiter: The limiter requires Valkey` — verified by running it. Off, this deployment
needs no Valkey at all.

`compose.yaml` caps the container at 128 MB and binds it to loopback only (no authentication, so it
must not be reachable off-host).

Then:

```bash
export SEARXNG_URL=http://127.0.0.1:8888
fleet-search search "your query" --json
```

## For whoever wires it up

SearXNG's JSON reports **`unresponsive_engines`**. With results it is informational; with zero
results it separates *"nothing matched"* from *"the engines that could answer were blocked"* — only
one of which is worth retrying from an agent's point of view.
