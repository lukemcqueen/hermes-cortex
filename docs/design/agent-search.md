# Agent search — one capability, two agent systems

> **Status:** IMPLEMENTED (surfaces + cache + provider contract), WIRING PENDING.
> **Audience:** whoever wires it into an agent system (cortex or steadfaste).
> **Implementation:** `tools/fleet-search/` (Rust, 21 tests, `cargo test`).

## The requirement

Give both agent systems a way to search: hermes-cortex (Python) and steadfaste (Rust). The stated
constraint was resource-shaped — SearXNG was the candidate and is heavier than a single coding
agent needs — with a preference for a minimal MCP tool, SQLite for caching, and SearXNG as an
*optional external provider rather than a permanent dependency*.

The requirement's table, kept here because it is the yardstick this design is measured against:

| Setup | RAM | CPU |
|---|---|---|
| Minimal SearXNG, 1 worker | 100–250 MB | 1 vCPU |
| SearXNG + Valkey | 150–350 MB | 1 vCPU |
| Custom Go search wrapper | 10–30 MB | 1 vCPU |

## What was measured first (not assumed)

| Fact | Measured on esther, 2026-10-13 |
|---|---|
| `go` | **absent** — `go: command not found` |
| `rustc` / `cargo` | **1.98.1**, workspace builds offline from a warm crate cache |
| steadfaste | **is Rust** (`core/Cargo.lock`, `crates/steadfaste-*`, `steadfaste-gateway`) |
| `sqlite3` CLI | **absent** |
| Python `sqlite3` module | present, SQLite 3.53.1 |
| crates.io | reachable |

Two of these decided the shape. **Go would be a third language** in a fleet that already has Python
(cortex) and Rust (steadfaste) — and it is not even installed, so the "lowest RAM" row would cost a
toolchain on every host. And **the `sqlite3` CLI is absent**, which is why the cache is not a
subprocess: a local cache that silently reports itself unavailable is indistinguishable from
"nothing found", the worst failure mode this tool has.

## The decision

**One static Rust binary, three operations, two surfaces, no service.**

- **Rust, not Go** — same resource class, zero new toolchains, and it is the language of the system
  this capability is ultimately for.
- **No daemon** — it starts, does one thing, exits. Nothing resident, nothing to restart, no port,
  no health check, no listener to secure.
- **Bundled SQLite** (`rusqlite` + `bundled`) — the cache works on a host with no `sqlite3` and no
  Python. Cost: one C compile at build time and a slightly larger binary, paid once on the build
  host instead of per query.
- **SearXNG optional** — `SEARXNG_URL` enables `web_search`. Unset, `web_search` says so and exits
  **3**; it never scrapes free search pages (fragile, rate-limited, and impossible to tell apart
  from "no results").

### The measured envelope

| Metric | Measured |
|---|---|
| Binary | **5.9 MB** (`target/release/fleet-search`) |
| Idle RSS, MCP server waiting on stdin | **5.2 MB** (VSZ 8.6 MB) |
| Peak in the no-provider path | no network, no allocation worth reporting |

That is **below** the 10–30 MB Go estimate and two orders of magnitude under the SearXNG row. The
design point stands on measurement rather than on the estimate it was proposed from.

### SearXNG, measured the same way (2026-10-13)

The question "can SearXNG be squeezed to ~50 MB so it can be the starting point?" was answered by
running it, not by reading a sizing table. `searxng/searxng:latest`, one worker, loopback only,
`limiter`/`public_instance`/`image_proxy` off, no Valkey:

| Configuration | Steady RSS | Results for a real query |
|---|---|---|
| Default engine set, one worker | **~124 MiB** | **20**, with `brave` + `duckduckgo` unresponsive |
| Pruned to 3 engines (`keep_only`) | **~92 MiB** | **0** — the engines that could answer were blocked; **not agent-usable** |
| Default set + `UWSGI_WORKERS=4` | ~124 MiB, still one python process | 20 — the variable is **inert** here |

Measured in STEADY STATE: after the instance has served queries, and again 20 s later. Earlier
figures of 99 MB / 82 MB were taken ~25 s after start, before it had served anything, and a cap
chosen from them would be undersized. A 64 MB cap is OOM-killed outright.

**50 MB is not reachable.** The floor is ~92 MiB and that configuration returns nothing; the
smallest configuration that actually **works** is **~124 MiB** — about half the "minimal SearXNG"
figure the sizing table this design started from suggested.

Two findings that matter more than the numbers:

- **The current image runs Granian, not uWSGI**, so `UWSGI_WORKERS=1` — the variable most guides
  (and the maintainers' own memory thread) recommend — has no effect here. The worker count is
  still the driver (that thread reports 600 MB → 150 MB at `workers=1`), but the lever moved.
- **Memory and usefulness trade in the same direction.** Pruning engines is the only way under
  100 MB, and the engines pruned are the coverage lost. On this host `brave` and `duckduckgo` are
  already unresponsive from a datacenter IP, so a small engine set is a search engine that finds
  nothing. SearXNG earns ~99 MB by failing over across ~70 engines; pruning removes exactly that.

A ready-to-use config, with these numbers beside it, is in
`tools/fleet-search/docker/searxng/` (`settings.yml` + `compose.yaml` + README).

Also learned by running it: SearXNG's JSON reports **`unresponsive_engines`**. With results it is
informational; with ZERO results it separates *"nothing matched"* from *"the engines that could
answer were blocked"* — and only one of those is worth retrying. The provider **surfaces it**
(`unresponsive` is a first-class field in the JSON, and the CLI names the engines on stderr), which
was verified against a live instance: `results: 2 | unresponsive: ['brave', 'duckduckgo', 'wikidata']`.

## The three operations

| Operation | Needs a provider | Behaviour when it cannot work |
|---|---|---|
| `web_search` | yes (`SEARXNG_URL`) | exit **3** + names the variable; never an empty list |
| `web_fetch` | no | stores what it read in the cache; a failed store is reported, not hidden |
| `web_search_local` | **no** | searches what was already fetched; offline by construction |

**Exit codes are part of the contract**, because an agent branches on them:

- `0` — the operation ran; the result is on stdout
- `1` — it ran and FAILED (unreachable provider, HTTP error, unusable response)
- `3` — COULD NOT VERIFY: nothing was searched and nothing should be inferred

Collapsing 1 and 3 is how an agent concludes a host is broken when it merely lacks a variable.

## Surfaces (one dispatch, two front doors)

`ops.rs` holds the three operations and the table describing them. The CLI and the MCP server both
call **that** code, and `tools/list` is generated from **that** table — so no surface can describe an
operation differently from another. This is the fleet's interop rule applied to a capability rather
than to a coding agent: one implementation, adapters with no semantics.

1. **CLI** — for crons, shell, and any language:
   `fleet-search search "query" --json` · `fetch <url>` · `local "query"` · `doctor`.
   `fetch` prints text on stdout and metadata on stderr, so it pipes and redirects like a UNIX tool.
2. **MCP over stdio** — `fleet-search mcp`. No port, no daemon: the client starts the process and
   speaks JSON-RPC on its stdin/stdout. stdout carries JSON-RPC and nothing else.

## Wiring into each system (the part that is NOT done)

**hermes-cortex (Python).** Two adapters, both thin:
- register the binary in `mcp_servers` so cortex agents get `web_search` / `web_fetch` /
  `web_search_local` as ordinary MCP tools;
- call the CLI from crons where a process per run is the natural shape.
- The deploy must build and place the binary (`cargo build --release`), which needs a warm crate
  cache or network once. `Cargo.lock` is committed so builds are reproducible.

**steadfaste (Rust).** It already has the right slots — per its own component/interface map,
**C7 Worker runtime** ("loop, tools, adapters") is where a tool belongs and **C9 Core Interface
server** is the northbound surface. The adapter there is: run this binary as an MCP server, or link
the same code as a crate. Nothing in steadfaste's policy layer changes, and no semantics move into
the adapter — a transport/adapter that invents behavior is the bug the gateway contract forbids.

## Honest limits (as of this commit)

- **Live SearXNG round trip: DONE** (2026-10-13). `web_search` was run against a real
  `searxng/searxng:latest` instance on this host and returned real results; the same run showed the
  provider surfacing `unresponsive` (`['brave', 'duckduckgo', 'wikidata']`). The instance was then
  removed — nothing is wired to a running provider yet.
- **Wiring is pending** in both systems (above). An unwired tool is a library, not a capability.
- **`web_search_local` corpus is only what `web_fetch` has stored.** It is not an index of the
  fleet's repositories (mycortex owns that) and must not be described as one.
