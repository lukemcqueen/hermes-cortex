# SRE — Operational-Reliability Critique

> Role: SRE in the architecture party. Primary target: `docs/party/architect.md`,
> read against `README.md`, `docs/manus-openmanus-notes.md`, `docs/design-brief.md`,
> `docs/party/elicit.md`, and the actual code (`src/store.ts`, `src/abi.ts`).
> Scope extensions (owner, mid-review): the model/cache-aware **prompt engine**
> (6th surface), **offline/cache + enterprise-pluggable RAG** (7th surface),
> **prompt/context templatization** (8th surface), the **visualizer/drill-in**,
> plus MCP hang/circuit-breaker, exactly-once effects, HITL-as-state,
> audit-ledger-as-truth, and replay-as-first-class-recovery.
> The question I answer: **can 1–2 people run this 24/7 without 3am archaeology?**

---

## 1. Can 1–2 people operate this 24/7? What breaks at 3am?

**Verdict: the shape is right — single process, files on disk, journal as
truth, no required network dependencies. That is exactly the 1–2-person
profile. But the failure path where a worker or the daemon dies without
saying goodbye is unspecified, and the store as written will deadlock itself
after its first crash.**

The 3am inventory, in order of likelihood:

### A — Daemon dies mid-task (OOM, kill -9, power loss)
One process by default, and `worker-own` is a Lane B **in-process** plugin.
A worker bug takes down the daemon, event bus, SSE endpoint, and journal
writer simultaneously. F-206's promise ("a crashing worker produces
`FAILED`/`STOPPED` events") is **physically impossible in-process** — the
thing that would emit `FAILED` is the thing that died. No systemd unit, no
restart owner, no boot-time reconciliation is specified. The morning operator
finds `WORKER_STARTED … TOOL_STARTED` then silence; F-507 honestly renders
`stalled?` — a question mark, not an answer.

### B — Store lock file survives a crash
`src/store.ts` acquires `state.json.lock` with `O_EXCL` and removes it only on
clean exit. **No stale-lock detection, no PID check, no age break.** A killed
process leaves the lock forever; every later write spins 5s and throws. After
scenario A the restarted daemon **cannot write its own store** until a human
deletes the lock by hand. Worse: the wait loop is
`while (Date.now() < until) {}` — a busy-spin that **blocks the Node event
loop**, freezing SSE, the bus, and every other task in the shared process
while one writer waits.

### C — The fsync that isn't there
The store's comment says "write temp → fsync → atomic rename → fsync dir."
The code does `writeFileSync` + `renameSync` — **no fsync anywhere**. On power
loss you can get a zero-length/torn `state.json` after a "successful" rename
(classic ext4 delayed-allocation failure). NF-502 "zero-loss durability" is
currently a comment, not a property — and `core/eventlog.ts` is told to copy
this exact discipline, so the journal (the single source of truth) inherits
the gap.

### D — Lease expiry with nobody home
`TASK_LEASED / LEASE_EXPIRED / TASK_RETRIED` events exist, but nothing
specifies lease duration, renewal, who expires a lease when the supervisor
and worker share a wedged process, retry count/backoff, or whether re-dispatch
honors `replay: "never"` history (F-409 is Should-tier, effort 4 — i.e.
realistically deferred). Lease machinery that can't fire when the process is
hung is decoration.

### E — Provider outage / budget bleed / silent cache miss
The ABI has `MODEL_REQUEST_STARTED/FINISHED` but **no failure/retry event**.
A 429-storm is invisible except as started-with-no-finished gaps; retries burn
`max_cost_usd` with zero per-retry visibility. With a cache-aware prompt
engine (§5.7) there is a second, quieter variant: the cacheable prefix stops
hitting (a template edit, a mid-run prefix mutation, provider cache eviction)
and every request silently costs 5–10× more. No error, no failed task — just a
cost graph bending upward at 3am while budgets drain.

### F — Disk full / index bloat
Append-only journals + checkpoints + workspaces + orphaned `.tmp` files (the
store never cleans them) + the RAG embedding index (§5.13), which can dwarf
all of them. ENOSPC during journal append is unhandled-by-specification. On a
1–2 person box, disk-full is Tuesday.

### G — External dependency wedge (MCP servers, RAG backends)
A Lane A MCP server that hangs (not crashes) holds a tool call — and therefore
a task and its lease — open indefinitely; no timeout/circuit-breaker contract
is specified (§5.8). An enterprise RAG backend (network vector DB) that goes
away turns "offline-capable harness" into a lie unless degraded-mode behavior
is defined (§5.13).

### What's genuinely good for the 3am operator
- Everything on disk, grep/jq-able, no daemon needed for forensics (US-501).
- No telemetry, no external DB required, no network egress — less to page about.
- Restarts are rehearsed (no hot reload) — *if* crash recovery gets specified.
- One fail-fast validated config file; TUI crash isolation (NF-102).

**Answer: yes — after the crash-recovery story is written down and the store
defects fixed. Today it is excellent at remembering what happened and
unspecified at surviving it.**

---

## 2. Operational-reliability score: **5 / 10** (8/10 with §4 mitigations)

- **+** Right substrate: journal-as-truth, pure status derivation, atomic-store
  *pattern*, explicit retention, headless parity, failure-as-state philosophy
  (token-limit → state, tool throw → failed result) consistently applied *for
  failures the process survives*.
- **−** The dominant real failure — process death / worker hang — has no
  detection (no heartbeat), no recovery (lease semantics undefined), and an
  in-process worker model that guarantees the failure is total.
- **−** The store contradicts its own durability claims (no fsync, stale-lock
  deadlock, event-loop-blocking spin) — and it's the pattern the journal copies.
- **−** No boot reconciliation; checkpoint content/location unspecified;
  replay (F-409) and checkpoint visibility (F-506) both Should-tier despite
  crash recovery depending on them; no exactly-once contract for effects.
- **−** External dependencies (MCP, RAG backends) have no bounded-failure
  contract.

A 5 because every fix is cheap and local — `supervisor.ts`, `eventlog.ts`, a
rewritten `store.ts`, gateway policy — with **zero ABI edits**.

---

## 3. SHOWSTOPPERS

1. **S-1 — In-process worker = shared fate.** F-206 is unimplementable while
   `worker-own` runs inside the daemon. SRE answer to Q-201/Q-205:
   **out-of-process from day one** (stdio `WorkerSpec` — architect §2c already
   sketches the transport for future Pi workers).
2. **S-2 — `store.ts` defects**: stale-lock deadlock, missing fsync,
   event-loop-blocking spin — in the one component everything else imitates.
   A crashed daemon cannot restart cleanly without manual `rm *.lock`.
3. **S-3 — No specified crash-recovery / boot reconciliation.** Undefined:
   what the daemon does on start with tasks in leased/running state.
4. **S-4 — No worker liveness signal.** Nothing distinguishes *working* from
   *wedged*. `PROGRESS` is optional and model-paced; stall detection cannot be
   built on events only healthy workers emit.
5. **S-5 — Journal envelope has no version field.** Architect §5f drops it,
   directly contradicting elicitation NF-501 (`journal_v: 1`, Must, RICE 125).
   A 3-year archival format without a version marker is unfixable later.
6. **S-6 — No exactly-once story for effects.** Nothing prevents crash + retry
   from double-applying a non-idempotent effect (`git commit`, deploy tool,
   MCP write). `replay: never|safe` exists as a field, but the journal/lease
   mechanics that make it *enforceable* are unspecified (§5.9).
7. **S-7 — MCP servers can wedge a task forever.** Lane A tools are external
   processes with no timeout, health, or circuit-breaker contract; a hung MCP
   server holds a lease indefinitely (§5.8).

---

## 4. Mitigations (all ABI-clean — no `abi.ts` edits)

| # | For | Mitigation |
|---|-----|-----------|
| M-1 | S-1 | Run `worker-own` out-of-process (NDJSON over stdio). Process exit **is** the crash detector; `kill` becomes honest SIGTERM→SIGKILL. |
| M-2 | S-2 | Rewrite store: `write`+`fsync(fd)`+`rename`+`fsync(dir)`; lock content `{pid, host, token, acquired_at}` with dead-PID/over-age breaker; async polling instead of busy-spin; sweep orphaned `*.tmp` at boot. Same discipline for `eventlog.ts` appends. |
| M-3 | S-3 | Specified boot reconciliation in `supervisor.ts`: scan store → leased/running with no live PID → expire lease, journal `LEASE_EXPIRED{reason:"boot_reconcile"}`, apply retry policy. Ship a systemd unit (`Restart=on-failure`) in-repo. |
| M-4 | S-4 | Core-side stall detection: supervisor tracks last-event-time per attempt; `stall_after_ms` breach → journal `ATTEMPT_STALLED` → `cancel`, escalate `kill`. Lives in `CoreLifecycleEvent`; ABI stays at 11. |
| M-5 | S-5 | `v: 1` in the `CoreEvent` envelope (or a `{"journal_v":1}` header line per NDJSON file). One field, restores NF-501. |
| M-6 | E | Core-journal `MODEL_REQUEST_FAILED / MODEL_REQUEST_RETRIED` from the adapter layer; retry storms become countable and costable. Cache hit/miss + cost fields on the journal record of `MODEL_REQUEST_FINISHED` (§5.7). |
| M-7 | F | Disk watermark in config (`min_free_bytes`): refuse task admission below it; ENOSPC on append parks the task `stalled`, never drops the event silently. Journal/index sizes surfaced in `codeharness status`. |
| M-8 | D | One written paragraph of lease semantics: duration, renewal (any received event renews; OS liveness otherwise), expiry action, retry cap + backoff. Tested with a dies-on-purpose fixture worker (extend F-209's fixture). |
| M-9 | S-6 | Effect ledger + intent journaling: journal `TOOL_REQUESTED` **before** execution, fsync'd; recovery consults the ledger before any `replay:"never"` re-run (§5.9). |
| M-10 | S-7 | MCP timeout + circuit-breaker contract enforced at the gateway (§5.8). |

---

## 5. The observability & operations contract (concrete)

This is the contract the SRE role will hold the build to.

### 5.1 The boring log shape
`codeharness log <task_id>` renders one line per significant event, derived
purely from the journal (`timeline()` fold — never a second write path):

```
12:00:01 task queued                       (TASK_QUEUED)
12:00:02 task leased → own-agent lease-7f2 (TASK_LEASED)
12:00:02 worker started                    (WORKER_STARTED)
12:00:02 prompt: system/worker-base@1.2.0 → anthropic/claude-x  (audit, §5.7/§5.14)
12:00:05 model req #1  cache HIT 91%       (MODEL_REQUEST_STARTED + journal cache record)
12:00:41 model req #1 done 1.2k in / 3.4k out  $0.031 (MODEL_REQUEST_FINISHED)
12:00:41 tool edit_file                    (TOOL_STARTED)
12:00:42 tool edit_file ok  0.4s           (TOOL_FINISHED + audit record)
12:04:10 checkpoint ckpt-2                 (CHECKPOINT)
12:07:33 tests passed                      (TOOL_FINISHED tool=test-run ok=true)
12:08:01 complete  Σ $0.14 / cap $2.00     (RESULT → outcome recorded)
```

The unhappy path must read just as boringly:

```
03:12:44 tool shell                        (TOOL_STARTED)
03:14:44 attempt stalled — no events 120s  (ATTEMPT_STALLED, M-4)
03:14:45 worker killed (op: kill, initiator: core)  (audit, F-504)
03:14:45 lease lease-7f2 expired           (LEASE_EXPIRED)
03:14:46 retry 2/3 from ckpt-2             (TASK_RETRIED{attempt:2} + ATTEMPT_RESTORED)
03:14:46 skipped replay-never: git commit (recorded result reused)  (effect ledger, §5.9)
03:14:47 task leased → own-agent lease-9a1 (TASK_LEASED)
```

Rules: (1) every line is grep-able from the JSONL with no process running;
(2) the log includes **audit and lineage lines** (prompt/template version,
model, cache hit, retry attempt N/M, restored-from checkpoint, skipped
replay-never effects), not just completion lines — if the 3am story cannot be
told in this format, the event set is incomplete. That is the acceptance test
for the whole visibility surface.

### 5.2 Event journal: versioned append-only JSONL
- One file per task: `<data_dir>/tasks/<task_id>/events.ndjsonl`.
- Frozen envelope **with version (M-5)**:
  `{v: 1, seq, ts, task_id, attempt_id?, worker_id?, source: "worker"|"core", event}`.
- `seq` monotonic per store; on restart, next seq = max(tail) + 1, recovered by
  reading the last line — which also validates the tail.
- Append = `O_APPEND` write of one complete line + fsync (batchable with a
  bounded flush interval; the interval **is** the explicit at-most-N-events-lost
  budget and lives in config, not folklore).
- Torn final line (crash mid-append) is tolerated-and-skipped on read with a
  logged warning (NF-502) — never a parse abort of the whole journal.
- Additive-only union; readers ignore unknown `event.type` (fuzz-tested).
- Retention is explicit (`retain_days` + prune command); nothing deletes
  silently (NF-505).

### 5.3 The audit ledger is the operational truth (owner concern: AUDITING)
The architecture must state this inversion explicitly: **the append-only run
ledger (journal) owns leases and remote effects; the task-state projection
(`state.json`) is a cache of it.** Consequences:
- Lease grant/renew/expiry are journal events *first*; the store's
  leased/running flags are derived and may be rebuilt from the journal at any
  time (`codeharness rebuild-state` — ship it; it is also the corruption
  recovery path for scenario C).
- Every remote/side effect (tool execution, MCP call, model request) exists in
  the ledger **before** its result exists anywhere else (§5.9 intent record).
  Replay logic consults the ledger, never the projection — so a stale or lost
  `state.json` can never cause double-execution.
- Every mutation-bearing operation (`start/send/cancel/checkpoint/kill`,
  initiator: cli|tui|plugin|core) and every prompt render (template name,
  version, vars-hash) is a ledger entry (F-504, NF-301). "What did the system
  do and why" is answerable from files on disk alone, with lineage.

### 5.4 Checkpoint / replay — replay is a first-class recovery path
- `CHECKPOINT` carries only `checkpoint_id` — correct; ABI stays ignorant of
  contents. The core must specify: checkpoint payloads are worker-owned opaque
  blobs at `<data_dir>/tasks/<task_id>/checkpoints/<checkpoint_id>/`, written
  with the same fsync discipline, listed by `codeharness checkpoints`.
- **Replay contract:** `codeharness replay <task_id> [--from ckpt-N]` re-runs
  a task from a checkpoint with a **new `attempt_id`** (attempt ids are
  append-only; the old attempt's history is never rewritten). The core journals
  `ATTEMPT_RESTORED{from: checkpoint_id, prior_attempt}` so the lineage —
  original attempt → checkpoint → replayed attempt — is one `jq` query and one
  drill-in keystroke (§5.15). Effects are gated by replay-safety: `safe` tools
  may re-execute; `never` tools resolve from the ledger's recorded result
  (§5.9). Replay of a *completed* task for reproduction/debugging follows the
  identical path — recovery and reproduction are the same machinery, which is
  what "reproduce to the byte" demands.
- **Gap to close:** `TOOL_FINISHED` carries only `{tool, ok}`. F-409's "use the
  recorded result" is impossible unless the gateway journals args-hash,
  duration, result hash + result location per call. Promote F-407's audit
  record to Must — replay correctness depends on it, not just audit.

### 5.5 Crash recovery of the atomic store
- Fix the implementation to match its comment (M-2): temp-write → `fsync(fd)`
  → `rename` → `fsync(parent dir)`. Guarantee: after any kill/power-loss,
  `state.json` is either the old complete snapshot or the new one.
- Lock with `{pid, host, token, acquired_at}`; break dead-PID/over-age locks
  with a journaled `LOCK_BROKEN` note; sweep orphaned `*.tmp` at boot.
- Boot reconciliation (M-3) completes the contract: store says leased/running,
  journal tail stale, no live PID → expire, journal, retry or park. **The
  store never lies for more than one boot** — and because the ledger is truth
  (§5.3), the store can always be rebuilt from journals.
- Scale note (architect §7.3): whole-file rewrite per mutation is
  O(total-tasks); document a measured ceiling (e.g. known-good to 2k tasks,
  prune beyond) so the 2028 operator isn't surprised.

### 5.6 What the 11 ABI events do NOT cover — and why that's (mostly) fine
The 11 worker events are a vocabulary for a **healthy, cooperating worker**.
They deliberately do not cover:

| Missing | Why the ABI is the wrong place | Where it lives instead |
|---|---|---|
| Retry (attempt N/M, backoff) | Retry is a core policy decision; the worker doesn't know it's a retry | `TASK_RETRIED{attempt, max}` core event (exists — add fields) |
| Lease expiry / renewal | Core bookkeeping; workers never see leases | `TASK_LEASED`/`LEASE_EXPIRED` core events (exist); semantics must be written (M-8) |
| Worker crash / heartbeat | A dead worker cannot emit; a hung one won't. An ABI heartbeat would be emitted only by workers healthy enough not to need it | OS-level liveness (process exit/pipe EOF — needs M-1) + supervisor `ATTEMPT_STALLED` on event-silence timeout (M-4) |
| Model request failure/retry | Adapter retries are invisible today | `MODEL_REQUEST_FAILED/RETRIED` core-journal events (M-6) |
| Cache hit/miss, cost per request | Provider/prompt-engine detail, not worker cognition | Prompt-engine journal record per request (§5.7) |
| Tool result payload/duration | ABI minimalism is right; `ok` is the worker's view | Gateway audit record: args-hash, duration, result hash/location (promote F-407 to Must) |
| Approval wait (HITL) | Blocking-on-human is an operational state, not worker cognition | `APPROVAL_REQUESTED/RESOLVED` core events (§5.10) |

The pattern is consistent: **the ABI stays at 11; everything operational lands
additively as `CoreLifecycleEvent`s in the journal.** Q-501's honest answer:
sufficient *for workers*; insufficient *for operations* until the core-side
lifecycle set grows from 4 to ~10 events and lease/retry semantics are
written down. **The single biggest gap in the 11-event ABI is the absence of
any liveness/crash signal — which is unfixable inside the ABI by construction
(dead workers don't emit), so it must be OS-level liveness + core-side stall
events, and the architecture currently specifies neither.**

### 5.7 Prompt engine (6th surface): cache-aware assembly — operational contract
The prompt engine assembles per-model prompts with a **stable cacheable prefix**
(system prompt + tool schemas + templates) that is never mutated
mid-conversation. SRE requirements:
- **Cache-hit rate is a first-class cost signal.** Every model request's
  journal record carries `{cache: {prefix_hash, hit: bool, cached_tokens,
  uncached_tokens}, cost_usd}`. The boring log shows `cache HIT 91%` /
  `cache MISS (prefix changed)` per request; `codeharness cost` reports
  per-task and rolling cache-hit rate.
- **Prefix immutability is enforced, not hoped.** The engine hashes the
  assembled prefix at attempt start; any mid-attempt change to the prefix hash
  is a journaled `PREFIX_CHANGED{old_hash, new_hash, cause}` warning event.
  A silent mid-run prefix mutation is exactly the 3am cost-spike bug — make it
  loud.
- **3am scenario:** cache silently stops hitting (template edit, engine bug
  reordering tools, provider eviction) → cost per request jumps 5–10× with no
  failure. Detection: a config threshold `cache_hit_alert_below` (e.g. 0.5
  rolling over 20 requests) emits `CACHE_DEGRADED` to the journal — and, since
  budgets are hard caps, the worst case is bounded: tasks stop at
  `max_cost_usd` with `STOPPED{reason:"budget"}`, and the journal shows *why*
  (a run of MISS lines after a `PREFIX_CHANGED`).
- **Interaction with checkpoint/replay:** the prefix hash + template versions
  are part of the attempt's journaled provenance. A replayed attempt
  re-assembles its prefix from *pinned* template versions (§5.14) — replay must
  reproduce the prompt, not pick up whatever template is current. Cache
  state itself is never checkpointed (it's a provider-side optimization);
  replay correctness never depends on cache warmth, only cost does — and the
  first post-replay request being a MISS is expected and journaled as such.
- Token budgeting lives here too: the engine journals per-request
  prompt-token composition (prefix/plan/step/tool-results) so "why did context
  blow past max_observe" is answerable from disk.

### 5.8 MCP tools: timeout + circuit-breaker contract (external = untrusted)
An MCP server hanging or crashing must never wedge a task. Gateway-enforced:
- **Per-call timeout** (tool `timeoutMs`, default from config) applies to MCP
  calls identically to built-ins: timeout → `TOOL_FINISHED{ok:false,
  error:"timeout"}` — the worker's loop continues; the model sees the failure.
- **Process supervision:** MCP servers are child processes of the daemon;
  exit/pipe-EOF is detected immediately → all in-flight calls fail fast,
  journaled `MCP_SERVER_DOWN{server, code}`. Restart policy per server in
  config (`restart: "on-failure", max_restarts, backoff_ms`).
- **Circuit breaker:** N consecutive failures/timeouts (config
  `trip_after`, default 3) trips the breaker: subsequent calls fail
  *immediately* with "circuit open: <server>" (no queue of doomed 60s
  timeouts), journaled `MCP_CIRCUIT_OPEN`. Half-open probe after
  `cooldown_ms`; close on success (`MCP_CIRCUIT_CLOSED`). The TUI Monitor
  panel shows breaker states.
- **Lease interaction:** a tool call blocked on a hung MCP server still counts
  as event silence — M-4's stall detection is the backstop even if a timeout
  is misconfigured to ∞. No external process can hold a lease longer than
  `stall_after_ms`.
- MCP tool results pass the same `max_observe` truncation and audit-record
  path; replay defaults to `"never"` (already in architect §2a) — correct,
  keep it.

### 5.9 Exactly-once effects: how journal + lease prevent double-apply
Checkpoint-then-retry is not enough; a crash *between executing an effect and
persisting its result* re-runs the effect on retry unless the ledger closes
the window. The contract:
1. **Single-writer guarantee (lease):** at most one live attempt per task —
   enforced by the lease, whose grant/expiry live in the journal (§5.3). No
   concurrent duplicate; the remaining risk is *sequential* (crash + retry).
2. **Intent-before-execution:** for every `replay:"never"` tool call the
   gateway journals `TOOL_REQUESTED{call_id, tool, args_hash}` and **fsyncs
   before executing**. After execution it journals the audit record
   (`call_id, ok, result_hash, result_location`).
3. **Recovery decision table**, consulted by the new attempt for each
   journaled `never`-call of the prior attempt:
   - intent + result present → effect happened; **reuse recorded result**,
     never re-run (boring log: "skipped replay-never: git commit").
   - intent present, no result → *indeterminate*: the effect may or may not
     have happened. Never blind-rerun. Resolve by (a) tool-provided idempotency
     probe where the tool declares one (e.g. `git log` for a commit —
     an optional `verify(call)` on `ToolSpec`, additive), or (b) park the task
     `needs_review` with the exact indeterminate call named. Honest beats
     available.
   - `replay:"safe"` tools → re-run freely.
4. **Effect-level idempotency keys:** `call_id` (attempt_id + seq) is passed
   to tools in `ToolContext`; tools with remote effects (MCP writes, deploys)
   forward it as an idempotency key where the remote supports one.
This makes re-run-after-crash exactly-once **at the effect level**: the lease
serializes attempts, the fsynced intent record closes the crash window, and
the decision table refuses the one genuinely ambiguous case instead of
guessing. Test fixture: a worker that crashes between intent and result on a
`never` tool (extends F-209/US-404).

### 5.10 HITL approvals as an operational state
An approval request is **a leased-and-blocked task state**, not a chat
feature:
- Worker requests approval via `PROGRESS` (structured message) or a gateway
  permission gate; the core journals `APPROVAL_REQUESTED{approval_id, action,
  requested_perm}` and the task renders as `blocked:approval` in TUI/CLI —
  a distinct color/state, never `stalled?`.
- **The lease is held but the stall clock is suspended** for the approval
  window — a task waiting on a human is not wedged. Instead an
  `approval_timeout_ms` (config, per-task-template overridable) bounds the
  wait.
- Operator resolution paths, all journaled `APPROVAL_RESOLVED{approval_id,
  decision, initiator}`: (a) TUI/CLI approve/deny (`codeharness approve
  <task> <approval_id>`), (b) **timeout policy** — `on_timeout: deny |
  fail | park` (default `deny` → the tool call fails visibly, the worker
  decides how to proceed). Crons and unattended runs set `on_timeout: deny`
  with a short window, or pre-grant permissions in the task template —
  **nothing can HITL-forever unattended**.
- Approval state survives daemon restarts (it's in the journal; boot
  reconciliation re-parks the task as `blocked:approval`, not expired).

### 5.11 Worker crash mid-task: detection → recovery, end to end
With M-1..M-4, M-8, M-9 in place:
1. **Detection.** Out-of-process worker: supervisor holds the child; exit/pipe
   EOF fires in milliseconds → `LEASE_EXPIRED{reason:"worker_exit", code}`
   journaled. Hung-but-alive: no events for `stall_after_ms` →
   `ATTEMPT_STALLED` → `cancel`, grace, `kill` (SIGKILL). Daemon-death: next
   boot, reconciliation (M-3) — store says running, no PID, stale journal tail
   → same expiry path, `reason:"boot_reconcile"`.
2. **Recovery.** Retry policy: attempts < max → `TASK_RETRIED{attempt:n}` +
   new `attempt_id` + fresh lease; seeded from latest `CHECKPOINT` if present
   (`ATTEMPT_RESTORED{from}`), else clean. Effects gated per §5.9 —
   `safe` re-runs, `never` resolves from the ledger, indeterminate parks
   `needs_review`. Attempts ≥ max → `failed{"retries exhausted"}` recorded;
   task shows failed, not `stalled?`.
3. **Operator view** is §5.1's unhappy path: stall → kill → expiry → retry →
   re-lease, five boring lines, zero archaeology. If any recovery step is not
   reconstructible from the journal alone, the implementation is rejected.

### 5.12 Retention, disk, and the 10k-task question
- Per-task journal files are prune-friendly (right call vs one global file);
  a tiny global index (`tasks.jsonl`: task_id, created, state, dir) gives the
  "what's happening now" ordering without a second source of truth.
- Watermarks: `min_free_bytes` refuses admission (M-7); `codeharness status`
  reports data_dir size by category (journals / checkpoints / workspaces /
  rag index) so growth is visible before it's an incident.
- Architect §7.3's own worry stands: whole-file `state.json` at 10k tasks is
  the store's real ceiling — document it and rely on prune/archive, not on
  hope.

### 5.13 Offline/cache + enterprise-pluggable RAG (7th surface) — operational contract
A local corpus + embedding store + cache, with enterprise-swappable backends
(vector DB, embedding model, chunker) behind a plugin slot. SRE requirements:
- **Offline is the default and must stay true.** Stock install: local corpus,
  local embedding store (files on disk under `data_dir/rag/`), zero network.
  A network backend is an *explicit* enterprise plugin choice — and choosing
  one changes the availability math, so the contract makes that visible:
  `codeharness status` shows `rag: local` vs `rag: <plugin> (remote)`.
- **The RAG backend contract (`rag_api: "1"`, additive-only, same 3-year
  regime):** `index(docs) / query(text, k) / stats() / health()`. Every call
  is timeout-bounded and circuit-broken **exactly like MCP tools (§5.8)** — a
  dead vector DB degrades retrieval, never wedges a task. Degraded mode is
  explicit config: `on_backend_down: skip_retrieval | fail_task` (default
  `skip_retrieval`, journaled `RAG_DEGRADED` per affected request so a
  quality drop is diagnosable later).
- **Index lifecycle is scheduled, journaled, and bounded:**
  - Build/rebuild/incremental are explicit commands (`codeharness rag
    build|update`) or a declared config cadence — never a silent background
    daemon. Each run journals `RAG_INDEX_BUILT{corpus_hash, embedder@version,
    chunker@version, docs, vectors, bytes, duration}`.
  - **Staleness is measured, not felt:** the index records the corpus content
    hash at build time; queries against a drifted corpus journal
    `RAG_STALE{index_corpus_hash, current_corpus_hash, age}` (rate-limited).
    A config `max_index_age` turns chronic staleness into a visible warning
    in `status`.
  - Disk + memory cost are declared: `stats()` returns bytes on disk and
    est. resident memory; admission-time check refuses to load an index that
    would exceed a config `rag.max_memory_mb`.
  - **Rebuild = new directory + atomic symlink/rename swap**; the old index
    serves until the new one is complete. A crashed rebuild leaves the old
    index intact (same temp-then-rename discipline as the store).
  - Embedder/chunker version changes **invalidate the whole index by
    definition** (vectors aren't comparable across embedders): the version
    pair is part of the index identity; a mismatch at load is a refusal with
    a "rebuild required" message, not silent garbage retrieval.
- **3am scenarios:** (a) *stale index* — the worker retrieves outdated code
  after a big merge, producing plausible-wrong edits; defense is the
  staleness journal events + rebuild-on-corpus-change cadence, and retrieval
  provenance (retrieved doc ids + corpus hash) in the audit record so a bad
  outcome is traceable to a stale index in one query. (b) *cold cache /
  missing index* — first task after a reboot or prune hits an absent index;
  policy `on_missing_index: build_sync | skip_retrieval | fail` (default
  `skip_retrieval` + warning). (c) *remote backend outage* — §5.8 breaker
  semantics; offline local mode is the recommended default precisely because
  it removes this page.
- **Cache invalidation vs checkpoint/replay:** retrieval results that entered
  a model prompt are already captured by prompt provenance (§5.7) and the
  audit record — so **replay does not re-query RAG**; it replays what was
  actually retrieved (byte-reproducibility). Fresh retrieval happens only in
  fresh attempts, never in replays. The RAG cache itself is never part of
  checkpoint state.

### 5.14 Prompt/context templatization (8th surface) — template change = deploy event
System prompt swappable per model; skills/AGENTS.md-style context templatized.
Operationally, **a template change is a deploy event**, with everything that
implies:
- **Versioned + pinned:** every template carries `name@version` (already in
  architect §3f); the running attempt resolves versions **once at attempt
  start** and journals the full set (`TEMPLATES_RESOLVED{[name@version,
  source_layer, content_hash]}`). Mid-attempt template changes on disk do NOT
  affect running attempts — assembly reads the resolved snapshot. This is
  also what protects the cacheable prefix (§5.7): a template swap can never
  silently invalidate the prefix mid-run; it takes effect at the next attempt,
  where the new `prefix_hash` + version set is journaled as the cause of the
  expected first-request MISS.
- **Boring log shows provenance:** the `prompt: system/worker-base@1.2.0 →
  anthropic/claude-x` line (§5.1) makes every run's template version + model
  auditable and reproducible — required for morning-after "why did the agent
  behave differently tonight" forensics.
- **Rollback is config, never code:** `templates.pins` in `harness.jsonc`
  pins any template to a prior version; reverting a bad rollout is a
  one-line config edit + restart (or next-task pickup), no core change, no
  git revert of the core repo. A bad template rollout at 3am is therefore a
  two-minute revert with a journaled config-provenance trail.
- **Rollout hygiene:** `codeharness template render <name> --vars fixture`
  diffs old-vs-new rendered output before enabling; cost regression from a
  template change is visible within one task via the cache/cost journal
  (§5.7) — a template edit that grows the prefix or breaks caching shows up
  as `PREFIX_CHANGED` + falling hit-rate, attributable to the exact
  `name@version` in the provenance record.

### 5.15 Visualizer / drill-in — the 3am debugging tool
The "supervise the swarm" view (OpenSwarm cockpit shape), operationally
specified:
- **Pure function of the journal.** Every panel renders
  `f(events[, store snapshot])` — no private state files, no side databases,
  nothing to get out of sync. The same folds (`timeline()`, `costs()`, status
  derivation F-507) power TUI, CLI, and any future web view. If the TUI shows
  something `jq` can't derive from the journal, that's a defect.
- **Works offline / post-mortem.** `codeharness tui --task <id>` (and the
  drill-in views) must work with the daemon stopped, reading journal files
  directly — the 3am incident is often *after* the crash. Live mode is the
  same renderer fed by SSE tail instead of file read.
- **Cheap to render:** bounded ring buffer over the tail (NF-104), fold
  incrementally per event, virtualized scrollback. Budget: responsive at 10k
  events / 20 tasks; no giant retained DOM/state trees. Drill-in loads one
  task's journal, not the world.
- **One keystroke from alert line to cause:** the operator flow is: Tasks
  panel shows `bugfix-77  failed (retries exhausted)  03:14` → **Enter**
  drills into the task timeline (the boring log, §5.1) → cursor on any line,
  **Enter** again expands the underlying journal envelope(s): the raw event,
  its audit record (args-hash, duration, result location), and — for
  lineage lines — cross-links: `TASK_RETRIED` jumps to the prior attempt's
  tail, `ATTEMPT_RESTORED` jumps to the checkpoint entry, `APPROVAL_*` shows
  initiator, `PREFIX_CHANGED` shows old/new template provenance. Checkpoint
  timeline and replay lineage (attempt 1 → ckpt-2 → attempt 2) render as a
  vertical chain in the detail view.
- Read-only by construction: the drill-in issues zero operations; the ops
  path stays the existing 6-verb channel (F-104). A rendering bug can waste
  the operator's time but can never touch a task.
- Headless parity holds: every drill-in view has a CLI twin
  (`codeharness log/checkpoints/cost/audit <task_id>`), so the 3am story is
  recoverable over a bare ssh session with no TUI at all.

---

## Bottom line for the party

The observability spine — journal-as-truth, pure derivation, boring log — is
genuinely strong; defend it against feature creep and extend it (audit ledger
owns leases and effects, §5.3). What must change before freeze: run the worker
out-of-process (S-1), fix the store to match its own comments (S-2), specify
boot reconciliation and lease/retry semantics (S-3, M-8), add supervisor-side
stall detection (S-4), version the journal envelope (S-5), journal effect
intents for exactly-once recovery (S-6), and bound MCP/RAG externals with
timeouts + breakers (S-7, §5.13). The new surfaces slot in cleanly *because*
the journal is the spine: cache-hit rate, template provenance, RAG index
lifecycle, approvals, and replay lineage are all just more additive core
journal events — none touches `abi.ts`. The 11 events describe a worker that
is alive and honest; operations is the art of handling the worker that is
neither, and that art belongs, additively, in the core's lifecycle events.

