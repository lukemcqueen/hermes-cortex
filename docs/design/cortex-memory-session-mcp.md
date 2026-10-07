# Design — cortex context: memory + session over one shared tool surface (S2c)

> **Status:** proposed v2. Answers Luke: *"we need Pi to have session stage and
> mycortex memory. can hermes-cortex provide this as a service or mcp server?"*,
> then *"session and mycortex memory are related too — consider how best to
> incorporate memory too/mix/match/etc"*, and *"split the concerns design and
> implement both"*.
>
> **v1 of this doc proposed two servers. That was wrong.** Memory and session
> are not two adjacent capabilities — they are two *views of one store*, and the
> design below exploits that.

## The relationship (why one surface)

Look at what the memory store already is (`mycortex_mem`):

| Table | What it holds |
|---|---|
| `peers` | who the agent talks to |
| `sessions` | a conversation — `started_at` / `ended_at` / `message_count` |
| `messages` | the per-session, per-peer history (user/assistant, 5k cap) |
| `conclusions` | durable facts distilled from that history |
| `profiles` | the curated peer card |

**Sessions are already the substrate memory is built from.** `messages` *is*
session history; `conclusions` and `profiles` are what memory distilled out of
it. Two servers over this would mean two connections, two identity resolutions,
and two slowly-diverging opinions about what a session is.

Therefore: **one MCP server, two tool families, one store, one identity model.**

```
cortex-context-mcp.py
├── mem_*      memory family   — what do I know?
└── session_*  session family  — where am I?
        └── both over mycortex_mem (+ one new checkpoint table)
```

## Current state (the gap)

| Capability | Today | Reachable by Pi? |
|---|---|---|
| `mem_profile` / `mem_search` / `mem_context` / `mem_conclude` | `plugins/mycortex-mem/__init__.py`, via `ctx.register_memory_provider(...)` | ❌ Hermes plugin-system call |
| `mem_reasoning` | same plugin, via `agent.auxiliary_client.call_llm` | ❌ Hermes internal |
| Session state | Hermes session storage + the `session-manager` skill | ❌ no standalone surface |
| loop-gov / task / bus / executor / sandbox | `mcp-servers/*.py` | ✅ |

This is the **S2c** slice already recorded in
`docs/design/component-hermes-separation.md`.

## Why a shared tool surface (and why the access layer is per-harness)

> **Update (2026-10-02).** The correction below was right when written:
> Pi <= 0.87 had no MCP client. **Pi >= 0.99 / 1.0 does** — it reads `mcpServers`
> from `~/.pi/agent/mcp.json` (user scope) and `.pi/mcp.json` (trusted projects
> only), the same shape as Claude Code, and names tools `mcp__<server>__<tool>`.
> Pi therefore takes the **MCP layer for the tool surface** *and* the extension,
> which MCP cannot replace: the extension owns WHEN a checkpoint is written
> (`turn_end`), because a killed session can never call a tool. Governance is
> registered by `ops/scripts/install/install-pi-mcp.sh` (one run: `pi mcp list
> --json` reports the 4 governance servers `connected`; transcript committed
> under `tests/artifacts/`, independent reproduction pending); the extension and the
> curated skill set by `install-pi-integration.sh`.
>
> Original correction (retained for the record): an earlier revision of this doc
> claimed *"the harnesses already speak MCP — Pi, Claude Code, Codex"*, which was
> false for Pi at the time — its surface was `pi.on("turn_end" |
> "before_agent_start" | "session_before_compact", …)` plus
> `pi.registerTool({…})`, in TypeScript. MCP was chosen then on an unverified
> premise. **The lesson stands: verify the harness's actual surface before
> choosing a layer** — and re-verify it, because surfaces change.

What survives the correction is the part that was actually load-bearing: **the
tool surface must be shared, but the access layer is per-harness.**

- **The store is the shared artifact** — one implementation in
  `ops/services/mycortex-mem/context_tools.py`, so Pi's history is searchable
  from Hermes and vice versa, and no harness has its own opinion about what a
  session is.
- **The layer is chosen to fit the harness** — MCP for MCP-native harnesses,
  a CLI (+ extension) for Pi. Same "one shim per agent, never bespoke per agent"
  rule as `docs/adr/0005`, just applied correctly.
- **The pattern is in-repo** — `mcp-servers/` ships five servers; lifecycle,
  registration and doctor treatment are solved.

The corrected shape:

```
        ops/services/mycortex-mem/context_tools.py     ← ONE implementation
              │                          │
   cortex-context-mcp.py          cortex-context.py  ← access layers
   (Hermes/Claude/Codex)          (Pi + anything shelling out)
```
- **ADR-0005's principle** — *"ONE standard shim, generated per agent, never
  hand-written bespoke per agent."*

## Split 1 — the one that matters: the TRIGGER, not the surface

The split Luke asked for is **not** memory-vs-session. It's:

| Concern | Owner | Why |
|---|---|---|
| **Store + search** | **the shared tool surface** (MCP + CLI, cross-harness) | Pi's history must be searchable from Hermes and vice versa |
| **When a checkpoint is written** | **the harness** (hook / on-stop) | MCP is tool-call shaped and has no lifecycle. The agent that most needs a checkpoint is the one that just got killed — it can never write one. |

This removes the biggest weakness of an MCP-hosted session: **auto-capture is a
harness responsibility, never the model's memory.**

## The mix/match — where the two families reinforce each other

This is what makes one server better than two:

1. **`mem_context` becomes true orientation.** Today it returns card + facts +
   recent activity. It also returns **the current session's checkpoint** — so one
   cheap call orients an agent on *both* axes ("what do I know" and "where am
   I"). A cold start gets memory and position in a single request.
2. **Checkpoint content is memory candidate material.** `decisions` and
   `blockers` are exactly what `mem_conclude` exists for; `session_close` can
   promote them rather than losing them in a session blob.
3. **`session_search` is one query surface, not a second index.** It searches
   checkpoints *and* the message history the memory family already searches —
   same store, same ranking code, no second embeddings pipeline.
4. **Identity is shared.** A session is keyed to a peer; a card is keyed to the
   participants. One resolution path, so a restore cannot land on another peer.

## Tool surface

### Memory family (`mem_*`) — mirrors the existing plugin exactly

| Tool | Behaviour |
|---|---|
| `mem_profile` | read / write the peer card — cheapest call, no LLM |
| `mem_search` | search over past messages — raw excerpts, no LLM |
| `mem_context` | orientation snapshot **(now includes the session checkpoint)** |
| `mem_conclude` | write / list / delete durable facts |

Design rule carried over from the plugin: **`mem_profile` is the orientation
call, `mem_reasoning` is the expensive one** — the descriptions must say so, or a
harness with no other guidance reaches for the costly one first.

### Session family (`session_*`)

| Tool | Behaviour |
|---|---|
| `session_checkpoint` | persist `done` / `pending` / `blockers` / `decisions` / notes |
| `session_restore` | snapshot by id, or latest for `harness:repo:branch` — **facts, never a transcript** |
| `session_list` | recent sessions (harness, repo, agent, status) |
| `session_search` | checkpoint + message history search ("did we already try X?") |
| `session_note` | append a durable progress line mid-session |
| `session_close` | final snapshot + end; optionally promote decisions to memory |

**Session identity is explicit and derivable** — `harness:repo:branch`, never
"latest". A caller that cannot name its session cannot silently resume someone
else's.

## Disadvantages of MCP for sessions (and the mitigations)

Honest list, since Luke asked:

| Disadvantage | Mitigation in this design |
|---|---|
| **No lifecycle hook — best-effort only** | the harness owns writes (`session-autocheckpoint.py` on turn-end/stop); the model is never the only trigger |
| **Stateless server: no "current session"** | explicit, derivable session id passed by the harness |
| **No locking — concurrent writers** | one owner per record; checkpoint writes are append-only, the session row is upserted by its derived key |
| **A summary, never a true context resume** | accepted and stated: `session_restore` returns structured facts and says so |
| **Tool-schema cost on every call** | one server, families kept tight; session tools are called at boundaries, not per turn |
| **Start-of-session dependency** | fail-open: an unreachable store reports "memory unavailable" and the harness continues |

Inherent to *any* external store (not MCP-specific): the context window stays in
the harness; only what the agent writes is recoverable.

## Stores

| Surface | Store | Notes |
|---|---|---|
| Memory | the **existing** `mycortex_mem` schema | reuse as-is; no migration |
| Session checkpoints | a new **`mycortex_mem`-adjacent** table (`v002__sessions.sql`) | same DB, roles and psql seam — no new infrastructure |
| Search | the same store + the existing messages table | one ranking path, no second index |

Host without the shared Postgres → "memory unavailable", harness continues.
Memory is an enhancement, never a hard dependency (fail-open).

## Deferred (explicitly, not silently)

- **`mem_reasoning`** — needs a provider resolved without Hermes's
  `auxiliary_client`. v1 exposes the no-LLM tools plus session;
  exposed-but-broken would be worse than absent.
- **Embedding-backed search** — v1 uses keyword matching over the same store; the
  embedding upgrade is a later slice and reuses one path, not a new one.

## Slices

| Slice | What | Depends on |
|---|---|---|
| **S2c-a** | `store.py` (shared psql seam + SQL) + `v002__sessions.sql` | — |
| **S2c-b** | `cortex-context-mcp.py`: memory (no-LLM) + session families | S2c-a |
| **S2c-c** | `session-autocheckpoint.py` harness trigger + Pi consumption docs | S2c-b |
| **S2c-d** | doctor check + `cortex-update` registration | S2c-b |
| **S2c-e** | `mem_reasoning` (provider resolution) + embedding search | decided separately |

## Consumption — how Pi (or any harness) gets it

Two independent pieces, per the split:

**1. The store + search — declare the MCP server once:**
```bash
hermes mcp add cortex-context \
    --command ~/.hermes-cortex/venv/bin/python3 \
    --args ~/hermes-cortex/mcp-servers/cortex-context-mcp.py
```
Same wiring as `tasks` / `loop-governance`. No Hermes gateway required — the
server reads `.env` + Postgres directly.

**2. The trigger — the harness calls this at a boundary, not the model:**
```bash
python3 ~/hermes-cortex/ops/scripts/session-autocheckpoint.py \
    --done "<x>" --pending "<y>" --decision "<z>" [--close]
```
Wire it to the harness's stop/turn-end hook (Pi: its stop hook; Claude Code:
a `Stop` hook). It is fail-open — a memory outage never breaks the harness — and
it suppresses an *identical consecutive* checkpoint, so firing it every turn
cannot shred session history.

**Set the session identity once per session** (all optional; falls back to git):
```bash
export CORTEX_SESSION_HARNESS=pi CORTEX_SESSION_REPO=<repo> CORTEX_SESSION_BRANCH=main
```
Then tools need no session argument, and a checkpoint written by the harness and
one read by the MCP server agree on the session.

## Verified

- 22 hermetic tests (`tests/test_cortex_context_mcp.py`), including a **real MCP
  handshake** over stdio (tools/list through the SDK, not a shape check).
- **Real end-to-end**: the harness trigger wrote a checkpoint → the MCP server's
  own handler read it back with structured facts → a repeat was suppressed →
  `mem_context` returned memory *and* the session in one call →
  `session_close(promote_decisions=True)` landed the decision as a durable
  memory fact (`source: session`).



## Non-goals

- No new memory model — `mycortex_mem` is the store.
- No plugin removal yet: additive first; retire the plugin once the MCP path is
  proven (the cron-bridge one-owner lesson).
- Not a transcript archive: checkpoints are structured and capped.
- No LLM-in-the-loop checkpoint summaries: restore must be cheap and deterministic.

## Risks

- **Two writers, one store** — the plugin and the MCP server share a schema.
  Additive first, then retire the plugin; never both live indefinitely.
- **Secret handling** — reads the canonical `~/hermes-cortex/.env` like every
  other MCP server; no new credential surface.

## Verification

- **Hermetic unit tests** with an injected fake store (no live DB).
- **Parity** — the same `mem_profile` / `mem_search` query through the plugin and
  the MCP server returns identical results (golden known-answer).
- **Real end-to-end on the deployed path with Pi** — `mem_profile` →
  `session_checkpoint` → *new* session → `session_restore` + `session_search`.
