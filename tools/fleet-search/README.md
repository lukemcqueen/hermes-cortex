# fleet-search

One search capability for every fleet agent — hermes-cortex (Python) and steadfaste (Rust).
Design of record: `docs/design/agent-search.md`.

```bash
cargo build --release          # 5.9 MB binary; needs a warm crate cache or network once
./target/release/fleet-search doctor
./target/release/fleet-search search "searxng limiter" --json
./target/release/fleet-search fetch https://docs.searxng.org/       # prints text, caches it
./target/release/fleet-search local "limiter"                       # offline, no provider
./target/release/fleet-search mcp                                   # MCP over stdio
```

Three operations, and nothing else:

| Tool | What it does | Needs a provider |
|---|---|---|
| `web_search` | find pages | yes — `SEARXNG_URL` |
| `web_fetch` | a URL as text, stored locally | no |
| `web_search_local` | search what was already fetched | **no** |

**Exit codes:** `0` ran · `1` ran and failed · `3` could not verify (nothing was searched — do not
infer an empty result from it).

**Environment:** `SEARXNG_URL` (optional, e.g. `http://127.0.0.1:8888`) ·
`XDG_CACHE_HOME` (optional; defaults to `~/.cache`).

Rules this tool keeps, and why:

- **No daemon.** Starts, does one thing, exits. Nothing resident, no port, nothing to secure.
- **A failure is never an empty list.** "Found nothing" and "could not look" are different, and
  only one is worth retrying.
- **stdout is the result.** In MCP mode it carries JSON-RPC and nothing else; diagnostics go to
  stderr, always.
- **Bound parameters, escaped patterns.** Page text came off the web: it is hostile input to the
  cache, and a query containing `%` matches that character, not the whole corpus.
- **Bundled SQLite.** Chosen after measuring: this host has no `sqlite3` CLI, and a cache that
  silently vanishes is worse than no cache.
