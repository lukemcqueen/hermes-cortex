# Decision — Codeharness Architecture Party (Fable, Nous)

> Synthesis of the 7-role party: Elicit, Architect, Domain (batch 1) + Security,
> SRE, Product, QA (batch 2). Source docs in this directory. This is the ADR —
> what to build, what to fix before freeze, what to defer.

## Party scores

| Role | Score | Read |
|------|-------|------|
| Security | **4/10** (11 showstoppers) | controls mounted inside the boundary they must enforce |
| SRE | **5/10** (7 showstoppers) | right substrate, unspecified survival mechanics |
| Product | **6/10** (5 showstoppers) | set-and-forget yes, value-fast no — over-built horizontal, under-built vertical |
| QA | **7/10** (6 showstoppers) | excellent bones, two conflicting worker contracts |

Weighted (Arch 20% / Sec 20% / SRE 15% / Domain 15% / Product 15% / QA 15%),
with Architect+Domain scoring their own design ~7: **~5.9/10 — the shape is
right, do not freeze yet.**

## Verdict (unanimous across all four critics)

**The architecture's shape is correct** — frozen `core/`, coding agent as an
unprivileged `worker` plugin, journal-as-truth, permission-gated gateway,
provider-agnostic ABI. **But it must NOT be frozen in this state.** There is a
short list of fixes that are *cheap now and ruinously expensive after ABI v1
freezes* — because the journal format, the worker contract, the permission
vocabulary, and the audit-trail format are all 3-year commitments. The critics
all point at the same few holes.

## Pre-freeze fixes (ordered; these are the consensus showstoppers)

1. **Worker = out-of-process stdio, not in-process.** Security + SRE + QA
   converge here; it is THE consequential decision. The architect left it
   ambiguous. `worker_api: "1"` must be a spawn/stdio contract (Worker ABI v1
   messages over stdin/stdout JSONL), not an in-process driver interface.
   In-process = shared fate (crash isolation is physically impossible) AND
   controls on the wrong side of the trust boundary.
2. **Fix `src/store.ts` defects** (SRE verified against actual source): the
   lock loop is a busy-spin (blocks the event loop), there is no `fsyncSync`
   despite the doc comment claiming it, and a stale lock deadlocks. Rewrite the
   store before anything depends on it.
3. **Resolve the two conflicting worker contracts** (QA S-1): Architect's
   `WorkerSpec.handle(op, emit)` vs Domain's `WorkerFactory.start(task, ctx)`.
   Pick the **transport-shaped WorkerSpec** (the spawn/stdio one) — it's the one
   that makes the conformance suite target a single door.
4. **Add a real LLM adapter** (Product S-1): only `FakeAdapter` exists; the
   system cannot perform its core function as specified. One OpenAI-compatible
   adapter with usage plumbing (input/output/cached tokens) is the vertical
   MVP.
5. **Freeze the permission vocabulary with default-deny.** MCP tools must pass
   through the *same* permission gate as built-in tools. No unfrozen strings.
6. **Audit trail = hash-chained, append-only, write-time secret redaction.**
   Not regex-at-render. Replay produces a new audited run, never a rewrite.
7. **HITL approval primitive frozen into the ABI** (request/approve/deny/timeout)
   or plugins will fake approval.
8. **Replay/exactly-once: intent journaling.** Write-ahead intent + per-tool
   `replay: "never" | "safe"` (Pi's contract). Re-run = new `attempt_id`,
   effects gated by replay-safety, never double-applied.
9. **Liveness signal.** The 11 ABI events cannot carry crash/heartbeat (dead
   workers don't emit) — add OS-level process liveness + a core-side
   `ATTEMPT_STALLED` silence-timeout, outside the ABI.
10. **Zero-config contradiction** (Product S-2): `plugins.allow` "absent =
    disabled" means a fresh install loads no worker. The own-agent worker must
    be **enabled by default** so `init` + one command runs with zero config.
11. **Prompt-engine cacheable prefix**: trusted-layers-only + hash-verified
    prefix stability; template variables taint-escaped (never trusted when
    filled from tool output / RAG).

## Big decisions (weighted, from the Architect doc)

| Choice | Decision | Why |
|--------|----------|-----|
| Worker transport | **Out-of-process stdio** (upgraded from architect's ambiguous spec) | crash isolation + trust boundary; all 3 critics |
| TUI framework | Ink/React, quarantined in its own package | 3.85 weighted; but **defer to v1.1** (Product) |
| Plugin mechanism | Own directory loader (Lane A: `~/.codeharness/plugins`), MCP only as a tool source behind the gate | 4.15; npm packages rejected |
| Config format | JSONC + JSON Schema, single file | 4.55; unknown keys = startup error; no env-var spaghetti |

## Final frozen-core surface (what's IN `core/`)

- Worker ABI v1 (out-of-process stdio: 6 ops, 11 events + `ATTEMPT_STALLED` + approval + usage events)
- Permission vocabulary (default-deny) + the single tool gateway (`max_observe` + timeout)
- Atomic store (rewritten: fsync, non-spinning lock)
- Audit ledger (hash-chained append-only) — owns leases + effects; store is a rebuildable projection
- Adapter interface (provider-agnostic) + usage accounting
- Template resolver (layered, deterministic, versioned)
- Config loader (JSONC + schema)
- Plugin host (load/validate/disable, additive-only 1.x API)
- Supervisor (process liveness, lease expiry, retry/replay)

Everything else — own-agent loop, prompt engine, RAG, TUI, panels, MCP bridge —
is a **plugin or peripheral**, none privileged in core.

## MVP slice (Product's verdict, endorsed)

Ship the **vertical slice first**, then stop:

1. Frozen ABI + rewritten store + audit journal
2. Permission-gated gateway + 6 tools (edit-tool semantics validated on a small task corpus)
3. One real OpenAI-compatible adapter with usage plumbing
4. `own-agent` loop as an out-of-process worker, enabled by default
5. Three CLI verbs: `run` / `status` / `log --follow`
6. Plain-JSON task templates, whole-file override

**Defer to v1.1+ (or cut until a real consumer exists):** daemon + SSE, Ink TUI,
MCP bridge, panel extension API, adapter/template/event-sink plugin slots,
template layering + pins, lease machinery at 1-worker scale, Chat transcript tab.
The frozen journal + contracts make all of it safely retrofittable — which is
exactly why none of it should be built before it's needed.

## Cross-cutting contracts now in scope (from mid-party steers)

agent-as-plugin (ours first; Pi/OpenSwarm deferred, ABI kept neutral) · MCP as
untrusted tool source · idempotency/duplicate-safety · plugin HITL · auditing
(append-only, hash-chained) · replay (exactly-once at effect level) ·
per-model prompt/skills/AGENTS.md templatization · visualizer/drill-in
(read-only fold of the journal) · cost controls for fan-out/in (tree-wide
budget invariant, no self-raise) · hooks (lifecycle seam, cannot bypass gates)
· workflow (declarative DAG, checkpointable/replayable).

## Open questions — RESOLVED by the focused design pass

Two focused designs now close the gaps the Product steer missed. Read
[`prompt-engine.md`](prompt-engine.md) and [`rag-offline-cache.md`](rag-offline-cache.md).

1. **Prompt engine (model/cache-aware)** — **CORE**, as a ~300-line pure
   library `core/prompt.ts` (Prompt API v1). `assemble(AssembleInput) →
   PromptPlan` enforces the byte-stable cacheable prefix (sha256-prefix
   provenance), taint rules, and prefix/suffix partition. All provider churn —
   cache style, message shape, per-model system-prompt/skills/AGENTS.md
   template selection, pricing — lives in peripheral **model profile data
   files** (`templates/profiles/*.json`) resolved once at attempt start. This
   corrects the earlier "plugin or peripheral" line: the engine is core because
   cacheability is a core invariant; per-model *knowledge* is swappable data.
   MVP: `assemble()` + prefix/suffix partition + taint enforcement, two model
   profiles, `cached_tokens` plumbing into `MODEL_REQUEST_FINISHED`, four
   journal records (`PROMPT_RENDERED`, cache record, `PREFIX_CHANGED`,
   `TAINT_VIOLATION`) feeding `cache HIT 91%` boring-log lines, one `"prompt"`
   JSONC block.

2. **Offline/cache + RAG (enterprise-pluggable)** — **RAG peripheral,
   offline-cache semantics core.** The vector DB / embedder / chunker live in
   an **out-of-process stdio adapter** (per Security — an in-process client
   could exfiltrate the corpus); `core/` freezes only the tiny **Retriever Port
   v1** (`index/query/stats/health` → `Hit[]` with hash-verified chunk
   byte-ranges) plus the `IndexManifest`, the cold/warm/stale/invalid state
   machine, atomic build-into-versioned-dir + symlink swap, `skip_retrieval`
   degraded mode, and five journal events. Enterprise swap = plugin dir + two
   JSONC keys (`rag.adapter`, `rag.adapter_settings`), proven by a shipped
   conformance suite; `rag_api: 1` additive-only. MVP: frozen port + a ~300-line
   pure-TS lexical adapter (no embeddings, zero network), three CLI verbs
   (`rag ingest|build|status`), one `rag.search` tool, golden-fixture tests.

## Next action

Freeze nothing yet. Implement the **pre-freeze fixes** (1–11) as TDD slices in
`core/` — now including the two new core contracts (Prompt API v1, Retriever
Port v1) — run the QA conformance + neutrality gates against a trivial second
worker, then — and only then — declare Worker ABI v1 frozen and start the
vertical MVP.
