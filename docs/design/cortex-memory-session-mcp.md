# Design — cortex memory & session as MCP servers (S2c)

> **Status:** proposed. Answers Luke's question: *"we need Pi to have session
> stage and mycortex memory. can hermes-cortex provide this as a service or mcp
> server?"* — **Yes**, as two standalone MCP servers under `mcp-servers/`.
> Pi's reading of "session stage": **checkpoint/restore _plus_ searchable
> session history.**

## Goal

Any agent harness — Pi, Claude Code, Codex, steadfaste-tui, a future one — gets
two capabilities that today exist only inside a Hermes process:

1. **Durable memory** — facts, profiles, semantic search over the past.
2. **Session continuity** — where a session is (done / pending / blockers /
   decisions) and a searchable record of what previous sessions did.

## Why MCP, not a bespoke service

- **The harnesses already speak it.** Pi has an MCP client; so do Claude Code
  and Codex. Zero bespoke integration per harness, and no "integration drifts
  per agent" maintenance burden.
- **The pattern is in-repo.** `mcp-servers/` already ships five servers
  (`loop-gov`, `task`, `bus`, `executor`, `sandbox`) — lifecycle, transport,
  registration and doctor treatment are solved.
- **ADR-0005's principle** — *"ONE standard shim, generated per agent, never
  hand-written bespoke per agent."* A new harness inherits both capabilities by
  pointing at the same two servers.
- A bespoke HTTP service would need a client library per harness and would
  re-solve auth, discovery and versioning that MCP already defines.

## Current state (the gap)

| Capability | Today | Reachable by Pi? |
|---|---|---|
| `mem_profile` / `mem_search` / `mem_context` / `mem_reasoning` / `mem_conclude` | `plugins/mycortex-mem/__init__.py` — registered via `ctx.register_memory_provider(...)` | ❌ Hermes plugin-system call; exists only in a Hermes process |
| Session state | Hermes session storage + the `session-manager` skill | ❌ no standalone surface |
| loop-gov / task / bus / executor / sandbox | `mcp-servers/*.py` | ✅ |

This is the **S2c** slice already recorded in
`docs/design/component-hermes-separation.md`: *"Plugin/MCP layer: … mycortex-mem
/ command … run as standalone MCP servers … remove their in-process Hermes
plugin coupling."*

## Surface A — `mcp-servers/cortex-mem-mcp.py`

**No new data model.** Wrap the existing mycortex-mem store; expose the same five
tools the plugin exposes, so a Hermes-side migration later becomes a
delete-the-plugin change rather than a rewrite.

| Tool | Behaviour |
|---|---|
| `mem_profile` | read / write the peer card (cheapest orient-first call) |
| `mem_search` | hybrid search over past messages (raw excerpts, no LLM) |
| `mem_context` | full standing snapshot for the session (no LLM) |
| `mem_reasoning` | LLM-synthesised answer — most expensive; use sparingly |
| `mem_conclude` | write / list / delete durable facts |

Design rule carried over from the plugin: **`mem_profile` is the orientation
call, `mem_reasoning` is the expensive one** — the tool descriptions must say so,
because a harness with no other guidance will reach for the expensive one first.

## Surface B — `mcp-servers/cortex-session-mcp.py`

Checkpoint/restore **and** search, per Luke's answer.

| Tool | Behaviour |
|---|---|
| `session_checkpoint` | persist a compact snapshot: `done`, `pending`, `blockers`, `decisions`, free-form notes |
| `session_restore` | return a snapshot by id, or the latest for a repo/agent — enough for a *fresh* session to resume exactly |
| `session_list` | recent sessions (repo, agent, started/ended, status) |
| `session_search` | semantic + keyword search across history — "did we already try X?" |
| `session_note` | append a durable progress line mid-session (visible to the user) |
| `session_close` | final snapshot + mark ended (resume later without re-deriving) |

`session_restore` must return **facts, not a transcript** — the checkpoint's job
is to make resumption cheap, so it caps (done / pending / blockers / decisions)
rather than echoing conversation.

## Stores

| Surface | Store | Notes |
|---|---|---|
| Memory | the **existing** mycortex-mem Postgres schema | reuse as-is; no migration |
| Session | a **new** `sessions` schema in the same cortex Postgres (`session`, `session_checkpoint`, `session_event`) | same host/credentials path mycortex-mem already uses; no new infrastructure |
| Session search | reuse the **existing embeddings** infra (`schema/v004__embeddings.sql`) | one embedding path, not a second one |

Rationale for Postgres over a local file: the value of session history is
cross-harness (Pi's session should be searchable from Hermes and vice versa), and
mycortex-mem already establishes the connection path, roles and RLS pattern.

Host without the shared Postgres → the server reports "memory unavailable"
cleanly and the harness continues; memory is an enhancement, never a hard
dependency (fail-open, matching `bus_send`'s outbox behaviour).

## Consumption (how Pi gets it)

1. Each harness declares the two servers in its own MCP config — for Pi that is
   its MCP server list, resolved from the same repo path the other five use.
2. The ADR-0005 shim (`agent-shim.py`) remains the single generated client, so a
   new harness gets the wiring from the same generator rather than hand-editing.
3. Registration never requires the Hermes gateway: the servers read `.env` +
   Postgres directly, exactly like `task-mcp.py` / `loop-gov-mcp.py`.

## Slices

| Slice | What | Depends on |
|---|---|---|
| **S2c-a** | `cortex-mem-mcp.py` — wrap the five existing tools | nothing (store exists) — **smallest, immediate Pi win** |
| **S2c-b** | `sessions` schema + `session_checkpoint` / `_restore` / `_list` / `_close` | S2c-a (shares the server skeleton + Postgres path) |
| **S2c-c** | `session_search` on the existing embeddings | S2c-b |
| **S2c-d** | wiring + a doctor check ("this host's harnesses can reach memory/session") | S2c-a…c |

S2c-a is independently shippable and delivers the memory half on its own.

## Non-goals

- **Not** a new memory model — the store is mycortex-mem's.
- **Not** a Hermes plugin removal yet: the plugin keeps working while the MCP
  server is added. The plugin becomes deletable *after* a harness proves parity
  (same sequencing as Scope-1's additive shims).
- **Not** a vector DB or a second embeddings pipeline — reuse `v004`.
- **Not** an LLM-in-the-loop session summary: checkpoints are structured facts,
  so restore is cheap and deterministic.

## Risks

- **Two writers, one store.** The memory plugin and the MCP server write the same
  schema. Mitigate exactly as the cron bridge did: one owner per concern —
  additive first, and the plugin is retired once the MCP path is proven, never
  both live indefinitely.
- **Prompt-cache/`cost`** — `mem_reasoning` is an LLM call. It must stay explicit
  and rare (tool description says so), or a harness will burn tokens orienting.
- **Secret handling** — the servers read the canonical `~/hermes-cortex/.env`
  like every other MCP server; no new credential surface.

## Verification

- Parity: the same query through the plugin and through the MCP server returns
  the same result (golden known-answer, not a smoke test).
- A real non-Hermes harness (Pi) completing: `mem_profile` → `session_checkpoint`
  → new session → `session_restore` + `session_search` — end-to-end, on the
  deployed path.
