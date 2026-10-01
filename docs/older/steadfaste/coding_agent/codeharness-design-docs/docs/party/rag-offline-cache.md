# Design — Offline/Cache + Enterprise-Pluggable RAG (Surface 7)

> Focused design pass closing the gap left by the architecture party (Product's
> steer missed this surface). Designed INTO the frozen-core shape decided in
> `decision.md`: out-of-process stdio Worker ABI v1, journal-as-truth, single
> JSONC config, additive-only 1.x plugin API, permission-gated tool gateway.
> Inputs: security.md §1.9b, sre.md §5.13, qa.md §5.7, architect.md tree.

---

## 1. Verdict: RAG is PERIPHERAL. Offline-cache semantics are CORE.

**Confirmed — the party's lean is right, with one sharpening.** Split the
surface in two:

- **Peripheral (adapters, may churn):** everything probabilistic and
  vendor-shaped — the vector DB client, the embedding model, the chunker, the
  ranking. These are exactly the "churn-prone third-party code" the two-lane
  design exists for. A Pinecone client from 2026 will not look like one from
  2029; embeddings from `text-embedding-3` are incomparable with anything
  later. Freezing any of this into `core/` would break the 3-year promise
  within months.
- **Core (frozen, tiny):** the **Retriever Port v1** (the one door every
  backend walks through), the **index manifest + lifecycle semantics**
  (cold/warm/stale, atomic swap, staleness detection), the **degraded-mode
  policy**, the **journal events** (`RAG_INDEX_BUILT`, `RAG_STALE`,
  `RAG_DEGRADED`), and the **taint rule** (retrieved chunks are untrusted
  input, never in the cacheable prefix). These are contracts other core pieces
  (audit, replay, prompt engine) depend on, so they must version with core.

Rationale beyond the party's: (a) QA showed retrieval *quality* is untestable
as a frozen contract but retrieval *plumbing* is — so the freeze line must sit
exactly at the plumbing/quality boundary, which is the port; (b) Security
showed the corpus is often more sensitive than any task — the trust mediation
(core reads corpus, adapter only sees query text + returns refs) must be core
or it isn't a guarantee; (c) SRE showed a dead remote backend must degrade,
never wedge — degraded-mode policy is supervisor-adjacent, i.e. core.

**One refinement over the party sketch:** the adapter is **out-of-process**
(Lane A-style, stdio JSONL — same discipline as Worker ABI v1), per Security
§1.9b. An in-process vector-DB client can exfiltrate the whole corpus and
phone home embeddings. Out-of-process, it receives only `(query, k)` frames
and returns `(chunk_ref, score)` frames; chunk *text* is re-read by the core
from the hash-verified corpus.

---

## 2. The frozen interfaces (Retriever Port v1)

File: `core/retriever.ts`. Additive-only within v1, same regime as `abi.ts`.

```ts
// ---- identity & versioning -------------------------------------------------
export const RETRIEVER_API_VERSION = 1; // "rag_api": additive-only within 1

// ---- corpus & chunks -------------------------------------------------------
export type DocRef = {
  corpus_id: string;      // which registered corpus
  doc_id: string;         // stable id (relative path within the corpus root)
  content_hash: string;   // sha256 of the doc at index time
};

export type Chunk = {
  doc: DocRef;
  chunk_id: string;       // `${doc_id}#${seq}`
  byte_range: [number, number]; // offsets into the source doc — text is
                                // re-read from the corpus, never trusted
                                // from the adapter (security §1.9b)
};

export type Hit = {
  chunk: Chunk;
  score: number;          // adapter-defined, non-increasing in result order
};

// ---- the port ---------------------------------------------------------------
// Implemented BY the adapter process; these types define the stdio frame
// shapes the core sends/expects (JSONL, one frame per line; the hello
// handshake carries { rag_api: 1, adapter: "name@version" }).

export interface Retriever {
  /** Rebuild or incrementally update the index for a corpus snapshot. */
  index(req: IndexRequest): Promise<IndexInfo>;
  /** Top-k retrieval. Query text only — no task metadata ever crosses. */
  query(q: string, k: number, corpus_id: string): Promise<Hit[]>;
  /** Cheap introspection; feeds `codeharness status` and admission checks. */
  stats(): Promise<RetrieverStats>;
  health(): Promise<"ok" | "degraded" | "down">;
}

export type IndexRequest = {
  corpus_id: string;
  corpus_hash: string;            // merkle root over doc content hashes
  docs: { ref: DocRef; text: string }[]; // core streams these; adapter never
                                         // gets ambient fs access
  mode: "full" | "incremental";
  changed?: DocRef[];             // for incremental: added/updated/removed
};

export type IndexInfo = {
  corpus_id: string;
  corpus_hash: string;
  embedder: string;               // e.g. "text-embedding-3-small@2024-01" — or
  chunker: string;                //      "lexical@1" for the built-in adapter
  doc_count: number;
  vector_count: number;
  bytes_on_disk: number;
  built_at: string;               // ISO 8601
};

export type RetrieverStats = {
  indexes: IndexInfo[];
  est_resident_memory_mb: number;
};

// Embedder and Chunker are NOT separate core ports. They are internal
// concerns of the adapter, but their identity strings are part of the frozen
// index-manifest format (below) because a change to either invalidates the
// index by definition (vectors aren't comparable across embedders).
```

### The offline-cache core (index manifest + status)

File: `core/rag-cache.ts`. This is core code, not adapter code.

```ts
export type IndexManifest = {
  manifest_v: 1;
  corpus_id: string;
  corpus_hash: string;    // what was indexed
  embedder: string;       // identity pair — mismatch at load = refusal,
  chunker: string;        //   "rebuild required", never silent garbage
  adapter: string;        // "retriever-lexical@1.0.0"
  info: IndexInfo;
  manifest_hash: string;  // sha256 over the above; verified on every open
};

export type IndexState =
  | { kind: "cold" }                                   // no index exists
  | { kind: "warm";  manifest: IndexManifest }         // hash matches corpus
  | { kind: "stale"; manifest: IndexManifest;          // corpus drifted
      current_corpus_hash: string }
  | { kind: "invalid"; reason: "hash_mismatch" | "embedder_mismatch"
                              | "chunker_mismatch" | "schema" };

export interface RagCache {
  state(corpus_id: string): Promise<IndexState>;
  /** Retrieval facade used by the retrieval tool / prompt engine.
      Applies degraded-mode policy; journals every call with provenance. */
  retrieve(q: string, k: number, corpus_id: string): Promise<RetrievalResult>;
}

export type RetrievalResult =
  | { ok: true;  hits: Hit[]; index_state: "warm" | "stale";
      texts: string[] /* re-read from corpus, hash-verified */ }
  | { ok: false; degraded: "cold" | "backend_down" | "invalid_index" };
```

Journal events (ride the existing `CoreEvent` envelope; NOT new ABI events —
workers never see them):

- `RAG_INDEX_BUILT { corpus_id, corpus_hash, embedder, chunker, docs, vectors, bytes, duration_ms }`
- `RAG_RETRIEVED { corpus_id, query_hash, k, chunk_ids, index_state, corpus_hash }` — provenance for audit/replay
- `RAG_STALE { corpus_id, index_corpus_hash, current_corpus_hash, age_s }` (rate-limited)
- `RAG_DEGRADED { corpus_id, reason, action }`
- `RAG_INGESTED { corpus_id, path, docs, corpus_hash }` — operator ingest is journaled

---

## 3. Module / file layout

```
codeharness/
  core/
    retriever.ts          ★ Retriever Port v1 — types + stdio frame schemas
    rag-cache.ts          ★ IndexManifest, IndexState, RagCache, degraded policy
    rag-lifecycle.ts      ★ build/update orchestration, atomic swap, staleness
                          #   scan (walks corpus, computes merkle hash)
  plugins/
    retriever-lexical/    # built-in reference adapter (MVP, always shipped):
      manifest.json       #   pure-TS BM25-ish lexical index, no embeddings,
      main.ts             #   no network, deterministic tie-break by chunk_id.
                          #   Doubles as the conformance target.
    retriever-example-http/ # documented example: proxies to an enterprise
      manifest.json         #   embedding service + vector DB (not enabled by
      main.ts               #   default; requires a "net" grant)
  test/
    conformance/retriever-port.test.ts   # parameterized suite (QA §5.7)
    fixtures/rag/corpus/                 # ~30 small docs
    fixtures/rag/queries.json            # query → acceptable doc_id sets
    fixtures/retriever-memory/           # in-memory fake for unit tests
  data/                   # runtime, gitignored (config: rag.data_dir)
    rag/
      corpora/<corpus_id>/     # ingested docs (outside every Task.workspace)
      index/<corpus_id>/
        current -> v_2026-09-10T02-11-05Z/   # symlink — the atomic swap
        v_2026-09-10T02-11-05Z/
          manifest.json
          <adapter-owned files>
```

Rules: `core/rag-*.ts` never imports an adapter. Adapters never touch
`data/rag/corpora/` directly — doc text is streamed to them over stdio during
`index()`, and at query time they return only refs. The corpus store lives
outside every workspace (security: a running task cannot poison retrieval).

---

## 4. Config surface (in the ONE `config/harness.jsonc`)

```jsonc
"rag": {
  "enabled": false,                    // off by default; zero cost when off
  "data_dir": "./data/rag",

  // which adapter serves retrieval. "retriever-lexical" ships in-repo and
  // needs zero network — the offline default. Enterprises point this at
  // their own plugin (plugins.dirs + plugins.allow as usual).
  "adapter": "retriever-lexical",
  "adapter_settings": {                // passed opaquely at the adapter's
    // e.g. for an enterprise adapter:  // hello handshake; schema owned by
    // "endpoint": "https://vectors.corp.internal:8443",   // the adapter's
    // "embedding_model": "corp-embed-v2",                 // manifest.json
    // "chunker": { "strategy": "code-aware", "max_tokens": 512 }
  },

  "corpora": {
    "docs": { "path": "/srv/knowledge/handbook", "include": ["**/*.md"] }
    // ingestion stays explicit: `codeharness rag ingest docs` — this block
    // declares WHAT may be ingested, it never ingests by itself
  },

  "query": {
    "k": 5,
    "timeout_ms": 3000,                // gateway-style; a slow backend fails
    "max_chunk_bytes": 4000            //   the retrieval, not the task
  },

  "lifecycle": {
    "max_index_age_hours": 168,        // chronic staleness → status warning
    "max_memory_mb": 512,              // admission check refuses larger loads
    "on_missing_index": "skip_retrieval", // | "build_sync" | "fail"
    "on_backend_down": "skip_retrieval",  // | "fail_task"
    "on_stale_index": "serve_and_warn"    // | "skip_retrieval" | "fail"
  }
}
```

Validated by `schema/config.schema.json`; unknown keys = startup error (the
decided config rule). `adapter_settings` is the one deliberately opaque bag —
validated against the *adapter's* declared JSON Schema at handshake, not by
core, so enterprise knobs never force a core schema change.

---

## 5. Lifecycle: build, swap, cold/warm/stale, degraded

**Build / rebuild / incremental.** Explicit commands only, never a silent
background daemon:

- `codeharness rag ingest <corpus_id>` — copy/refresh docs into
  `data/rag/corpora/<id>/`, compute per-doc hashes + the merkle corpus hash,
  journal `RAG_INGESTED`. This is the ONLY way corpus content changes
  (security: ingestion is an explicit journaled operator action, never an
  ambient side effect of running tasks).
- `codeharness rag build <corpus_id>` — full index. Core streams docs to the
  adapter's `index(mode:"full")`; the adapter writes into a **new versioned
  directory** the core hands it (`index/<id>/v_<timestamp>/`).
- `codeharness rag update <corpus_id>` — incremental: core diffs current
  corpus hashes against the manifest and sends only `changed` docs with
  `mode:"incremental"`. Adapters that can't do incremental reply
  `{unsupported: true}` and core falls back to a full build. Output still
  lands in a new versioned directory (copy-forward is the adapter's problem).
- Optional cadence: a documented cron line, not an in-process scheduler.

**Atomic swap — never a torn index.** Same temp-then-rename discipline as the
rewritten store: build into `v_<timestamp>/`, fsync files, write
`manifest.json` last (with `manifest_hash`), fsync the directory, then
atomically repoint the `current` symlink (rename a new symlink over the old).
The old index serves reads throughout. A crash mid-build leaves `current`
untouched and an orphan `v_*` dir that `codeharness rag gc` removes. On open,
core verifies `manifest_hash` and the embedder/chunker identity pair — hash
mismatch = **refusal** (tampered), embedder/chunker mismatch = refusal with
"rebuild required", never silent cross-version vector soup.

**Cold / warm / stale.**

| State | Definition | Behavior |
|---|---|---|
| cold | no `current` index | per `on_missing_index` — default skip retrieval + `RAG_DEGRADED{reason:"cold"}` + status warning |
| warm | manifest `corpus_hash` == live corpus hash | serve; `RAG_RETRIEVED{index_state:"warm"}` |
| stale | corpus drifted since build | default serve + `RAG_STALE` (rate-limited) + every retrieval stamped `index_state:"stale"` — visible, never silent; `max_index_age_hours` breach shows in `codeharness status` |
| invalid | hash/identity mismatch | refuse to load; retrieval degrades as cold; loud status error |

Staleness is *measured* (hash comparison against ingest-recorded hashes), not
felt. The drift scan is cheap: per-doc hashes are stored at ingest, so
detection is an mtime-guarded re-hash.

**Degraded mode / offline.** The stock adapter (`retriever-lexical`) is fully
offline — no network, no embedding model; "offline-first" is literal. For
remote adapters: every `query()` is timeout-bounded (`query.timeout_ms`) and
circuit-broken exactly like MCP tools (SRE §5.8); a dead vector DB produces
`{ok:false, degraded:"backend_down"}`, the task **continues without
retrieval** (default `skip_retrieval`), and `RAG_DEGRADED` is journaled per
affected request so a later quality drop is diagnosable. `codeharness status`
shows `rag: retriever-lexical (local)` vs `rag: corp-vectors (remote,
circuit: open)`. Choosing a remote adapter requires the `net` permission
grant with named endpoints in its manifest — offline is the default posture;
network is an explicit, visible choice.

**Replay.** Retrieval results that entered a prompt are captured by
`RAG_RETRIEVED` provenance (chunk ids + corpus hash) and the audit record.
**Replay never re-queries RAG** — it replays what was actually retrieved
(byte-reproducible from the content-addressed corpus store). Fresh retrieval
happens only in fresh attempts. The RAG index is never part of checkpoint
state.

**Taint (frozen rule, from Security).** Every retrieved chunk enters model
context wrapped in the untrusted-source envelope with provenance attached
(corpus id, doc id, chunk hash), exactly like tool output. Retrieved content
may **never** be promoted into the cacheable prompt prefix or into template
variables that render outside the envelope.

---

## 6. Enterprise swap-in story

A company with its own vector DB + embedding model + chunker does this,
touching zero core files:

1. Write `plugins/corp-retriever/` — a `manifest.json` declaring
   `{ "rag_api": 1, "capabilities": ["retriever"], "permissions": ["net:vectors.corp.internal:8443"], "settings_schema": {...} }`
   and a `main.ts` speaking the stdio JSONL frames (index/query/stats/health).
   Inside it they call whatever they want — pgvector, Vertex, an internal
   embedding service, a tree-sitter chunker. Core never knows.
2. Config: add to `plugins.allow`, set `rag.adapter: "corp-retriever"`, put
   their knobs in `rag.adapter_settings` (validated against their own
   `settings_schema` at handshake).
3. Prove it: run the shipped conformance suite against their adapter —
   `bun test test/conformance/retriever-port.test.ts --adapter corp-retriever`.
   Green = it will behave under the harness (cold/warm/stale, timeouts,
   additive-field tolerance).
4. `codeharness rag build <corpus>` and go.

**Versioning so a 2026 adapter works in 2029:** the handshake carries
`rag_api: 1`; the port is additive-only within v1 (new optional frames/fields
only — an adapter answering 4 of a future 6 methods still works; unknown
frames get a typed `{unsupported}` reply, and core treats unsupported `update`
as "do a full build"). Extra fields on `Hit`/`IndexInfo` are tolerated;
missing required fields are refused at handshake, not at 3am. Embedder/chunker
upgrades are the adapter's internal business *except* that their identity
strings live in the manifest — so a new embedding model forces a visible
"rebuild required". If a `rag_api: 2` ever exists, core supports 1 and 2 side
by side, selected by handshake — the same add-alongside rule as the ABI.

---

## 7. MVP slice (smallest offline-capable, enterprise-pluggable RAG)

Consistent with the decision doc's "build nothing before it's needed":

1. `core/retriever.ts` — the port types + frame schemas (frozen).
2. `core/rag-cache.ts` + `core/rag-lifecycle.ts` — manifest verify, atomic
   swap, cold/warm/stale, `skip_retrieval` degrade, the 5 journal events.
3. `plugins/retriever-lexical/` — pure-TS lexical scorer, deterministic,
   offline, ~300 lines. No embeddings in the MVP at all.
4. Three CLI verbs: `codeharness rag ingest | build | status` (`update`/`gc`
   can wait).
5. One consumption point: a gateway tool `rag.search(query, k)` — permission
   `"rag:query"`, results envelope-wrapped like any tool output. (Prompt-
   engine auto-injection is v1.1; the tool proves the plumbing without
   touching the prompt engine's cacheable-prefix rules.)
6. The conformance suite + fixtures (§8), runnable against any adapter.

Deliberately absent from MVP: embeddings, incremental update, the remote
circuit breaker (no remote adapter exists yet — but the query timeout is
there from day one because the port is out-of-process), auto-injection,
multi-corpus routing. The frozen port makes all of it retrofittable — which
is exactly why none of it should be built before a real consumer exists.

---

## 8. Test strategy

Straight adoption of QA §5.7, with the pieces named:

- **`test/conformance/retriever-port.test.ts`** — parameterized
  `retrieverConformance(name, makeRetriever)`; CI runs it against
  `retriever-lexical` and the in-memory fake; enterprises run it against
  their adapter. Cases: index→query returns ≤k hits with non-increasing
  scores and real doc_ids; query-before-index → typed cold result, never a
  crash; warm determinism (re-query without re-index → identical results);
  mutate a doc without re-index → `state() === stale` and retrievals stamped
  `index_state:"stale"`; hang/throw → timeout → degraded result, task
  continues; extra fields tolerated, missing required fields refused.
- **Golden query fixtures** — `test/fixtures/rag/corpus/` (~30 docs) +
  `queries.json` mapping each query to a *set of acceptable doc_ids*.
  Asserted as "top-k contains ≥1 acceptable id" — never exact ranking, never
  exact scores. **Never commit embedding vectors as fixtures** (they change
  with every model rev and turn every test into a change-detector); commit
  acceptable answer sets instead.
- **Fake adapter** — `test/fixtures/retriever-memory/`: in-memory, lexical,
  stable tie-break by `chunk_id`; both the unit-test double and the
  conformance reference.
- **Deterministic lifecycle tests** (fault injection, no network): crash the
  build after adapter files but before the manifest → `current` still serves
  the old index, orphan `v_*` detected by `rag gc`; corrupt one byte of
  `manifest.json` → load refused as `invalid`; flip the embedder string →
  "rebuild required" refusal; symlink swap under a concurrent reader →
  reader finishes on the old index.
- **Quality is a nightly threshold, not a CI gate:** `bench/rag-recall.ts`,
  `recall@5 ≥ 0.8` on the fixture query set with a real backend — alerts,
  doesn't block PRs. Exact-score assertions are banned by review rule.
- **Taint test:** a retrieved chunk containing prompt-injection text appears
  in the message log only inside the untrusted envelope, with provenance;
  a chunk never appears in the bytes hashed as the cacheable prefix.

---

## 9. Open questions

1. **Chunk granularity ownership.** `byte_range` re-reading assumes the
   adapter chunks deterministically against the ingested bytes. Should core
   instead pre-chunk (making the chunker a core-supplied default with an
   adapter override), so `chunk_id → bytes` is provable core-side? Leaning
   yes-for-v2, no-for-MVP (the lexical adapter chunks by paragraph,
   trivially verifiable).
2. **Workspace-as-corpus.** Enterprises will ask to retrieve over the repo
   being edited. That collides with the "tasks can't poison retrieval" rule.
   Probable answer: a per-attempt, throwaway, workspace-scoped index that is
   *never* shared across tasks and never persisted — needs its own mini
   design before anyone builds it.
3. **Embedding-model egress.** A remote *embedding* call at query time leaks
   query text (and embeddings are invertible enough to leak content). Do we
   require query-time embedding to be local-only, with remote allowed only at
   index time? Security leans yes; needs an owner call.
4. **Multi-corpus routing** (which corpus for which task/template) — defer
   until two corpora exist.
5. **Index encryption at rest** for crown-jewel corpora — defer; the corpus
   sits on the same disk as the journal, so it's a whole-disk question.
