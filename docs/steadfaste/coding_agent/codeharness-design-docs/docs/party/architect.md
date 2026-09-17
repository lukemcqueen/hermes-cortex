# ARCHITECT — Reference Architecture for the Five Surfaces

> Role: ARCHITECT in the architecture party. Inputs: `README.md`,
> `docs/manus-openmanus-notes.md`, `docs/design-brief.md`, and the frozen core
> (`src/abi.ts`, `src/loop.ts`, `src/store.ts`, `src/adapter.ts`).
> Audience: Security / SRE / Product / QA critics.
> Optimization target: a 1–2 person maintainer who reads every important line.
> North star: core covers 90% frozen; the 10% is plugins/templates/config.
>
> **Owner directive (hard requirement, reflected throughout):** the coding
> agent itself is a PLUGIN — a *worker plugin* with zero special status in the
> core. The core is the runtime; it knows only Worker ABI v1 (`task_id`,
> `attempt_id`, `worker_id`, `workspace_id`, `checkpoint_id`, `lease_id` + the
> 11 events / 6 operations). We START with exactly ONE worker plugin: our own
> tiny agent. Pi and OpenSwarm workers are **deferred** (see §2.g) — the only
> obligation now is that the ABI stays neutral so they can plug in later
> without a core change. A worker plugin failing must never force a core
> upgrade.

---

## 0. The shape of the whole system

One repo, one process by default. The daemon (core) owns the store, the tool
gateway, worker supervision, and an **event bus** that everything else — TUI,
logs, metrics, plugins — merely *subscribes to*. The five surfaces are all
consumers or peripherals of the same frozen contracts, and the coding agent
sits *outside* the core, behind the same plugin host as everything else:

```
frozen contracts (semver "core 1.x never breaks"):
  1. Worker ABI v1        core/abi.ts         (exists as src/abi.ts — untouched)
  2. Event Stream v1      core/events.ts      (new — CoreEvent envelope over WorkerEvent)
  3. Tool Contract v1     core/tool.ts        (new — formalizes the loop's Tool)
  4. Plugin Host API v1   core/plugin-host.ts (new — incl. the `worker` capability)

peripherals (version independently, may churn):
  workers/own-agent (THE coding agent — a plugin), TUI, other plugins,
  templates, metric sinks
```

Proposed final tree (`src/` is renamed `core/` to make the freeze boundary a
directory name; files marked ★ are FROZEN; everything else is peripheral and
replaceable without a core change):

```
codeharness/
  core/                   # ★ the frozen runtime — knows NO worker by name
    abi.ts            ★ Worker ABI v1 (exists; moved from src/, content unchanged)
    store.ts          ★ atomic durable task store (exists)
    adapter.ts        ★ LLM adapter iface + fake (exists)
    events.ts         ★ CoreEvent envelope + EventBus (append-only NDJSON + subscribe)
    tool.ts           ★ Tool Contract v1 (schema, replay, executionMode, max_observe)
    gateway.ts        ★ tool gateway: registry, permission check, truncation, audit
    config.ts         ★ config loader: JSONC + JSON-Schema validation
    plugin-host.ts    ★ plugin loader/validator/lifecycle; registers workers too
    supervisor.ts     ★ task queue/leases → dispatch to a registered worker by
                      #   worker_id; speaks ONLY WorkerOperation/WorkerEvent
    template.ts       ★ template resolver + renderer (layered lookup, Mustache-subset)
    daemon.ts         ★ wires store+gateway+bus+supervisor, serves SSE on localhost
    main.ts             CLI entry (thin; parses args, starts daemon or one-shot task)
  workers/                # worker PLUGINS — peers, none privileged
    own-agent/            # v1 ships with exactly this one
      plugin.json         # capabilities: ["worker"] — same manifest as any plugin
      index.ts            # activate(api) → api.registerWorker(spec)
      loop.ts             # the agent loop (moved from src/loop.ts — it is WORKER
                          #   code, not core: the core never runs a loop itself)
      context.ts          # max_observe budget, stuck/duplicate-turn detection,
                          #   token-limit → graceful FAILED (Manus patterns 1,3,4)
    # (future, NOT designed now: pi/, openswarm/, claude-code/ — see §2.g)
  tools/                  # standard toolset — peripheral, each file self-contained
    shell.ts  read.ts  edit.ts  search.ts  git.ts  test-run.ts
  tui/                    # peripheral — its own package.json, versions independently
    main.tsx  app.tsx  panels/  chrome/  theme.ts  keymap.ts
  templates/              # peripheral — versioned prompt/task templates
    system/  tasks/  plans/  manifest.json
  plugins/                # user-installed non-worker plugin dirs (gitignored except examples/)
  schema/
    config.schema.json  plugin.schema.json  template.schema.json
  config/
    harness.jsonc         # the ONE config file
  test/
```

Two rules the critics should enforce:
1. **Anything under `core/` gets a 3-year freeze and a test; anything outside
   may be rewritten without notice.**
2. **`core/` contains zero imports from `workers/`, `tools/`, `tui/`, or
   `plugins/`** — enforced by a CI grep. The supervisor dispatches to "the
   worker registered under this `worker_id`", never to a named implementation.
   Our own agent gets no back door: it talks to the core through
   `WorkerOperation` in and `WorkerEvent` out, exactly like a future Pi worker
   would.

Note the deliberate demotion: `src/loop.ts` moves INTO the worker plugin. The
loop is how *our* agent thinks; a future Pi or Claude-CLI worker has its own
loop. Keeping it in core would silently privilege one worker — exactly what
the owner forbade. The core's frozen pieces are the contracts + store +
gateway + supervisor, not any agent's cognition.

---

## 1. TUI

### (a) What it is
A supervision cockpit (OpenSwarm shape): tabs Chat / Pipeline / Logs / Monitor,
`ContextBar` + `TabBar` + `HelpBar` chrome, panels rendering the core's event
stream. It is a **pure consumer**: TUI → SSE/NDJSON → render. It can send only
the six `WorkerOperation`s (start/send/cancel/checkpoint/status/kill) via the
daemon's localhost HTTP API. If the TUI dies, nothing else notices. It never
knows which worker implementation is running — it sees `worker_id` and events.

### (b) Module/file layout
```
tui/
  package.json          # own deps (ink, react) — pinned exact, own semver
  main.tsx              # entry: connect SSE, mount <App/>
  app.tsx               # tab router + global keymap dispatch (~150 lines)
  client.ts             # EventSource/NDJSON client for the daemon; typed on CoreEvent
  chrome/
    ContextBar.tsx      # task id, budget spent/remaining, model
    TabBar.tsx
    HelpBar.tsx
  panels/
    ChatPanel.tsx       # send/steer messages to a running attempt
    PipelinePanel.tsx   # StageTimeline + SubagentTree + LiveLog
    LogsPanel.tsx       # raw CoreEvent tail, filterable
    MonitorPanel.tsx    # cost, tokens, leases, worker health
    registry.ts         # PanelSpec[] — the ONE extension point
  theme.ts              # named color roles only (no per-component styling)
  keymap.ts             # default keybindings, overridden by config
```
Budget: ≤ 20 components total. `panels/registry.ts` is the guard — a new view
is a new PanelSpec, not a new component tree.

### (c) Key interfaces
```ts
// tui/panels/registry.ts — Panel API v1
export interface PanelContext {
  events: AsyncIterable<CoreEvent>;      // read-only live stream (replay + tail)
  ops: (op: WorkerOperation) => Promise<void>; // the only write path
  config: Readonly<HarnessConfig>;
}
export interface PanelSpec {
  id: string;                 // "pipeline"
  title: string;              // tab label
  panelApiVersion: 1;         // hard-checked at registration
  render: (ctx: PanelContext) => React.ReactElement;
}

// core/events.ts — the frozen envelope the TUI consumes
export interface CoreEvent {
  seq: number;                // monotonic, per store
  ts: string;                 // ISO-8601
  task_id: TaskId;
  attempt_id?: AttemptId;
  worker_id?: WorkerId;
  event: WorkerEvent | CoreLifecycleEvent; // TASK_QUEUED|LEASED|RETRIED|EXPIRED
}
```

### (d) Frozen core vs peripheral
- **Frozen (in core):** `CoreEvent` schema, the SSE/NDJSON endpoint
  (`GET /v1/events?since=<seq>`), the ops endpoint (`POST /v1/ops`). That's it.
- **Peripheral:** the entire `tui/` directory — framework, panels, themes,
  keymaps. The TUI could be rewritten in pi-tui or a web page and the core
  wouldn't know. Plugins may contribute `PanelSpec`s (see §2), but built-in
  panels never depend on plugins.

### (e) Config surface
```jsonc
"tui": {
  "theme": "default",                    // name in theme.ts or plugin-provided
  "tabs": ["chat","pipeline","logs","monitor"],  // order + which panels show
  "keymap": { "next_tab": "tab", "cancel_task": "ctrl+c ctrl+c" },
  "refresh_ms": 250,                     // render throttle
  "logs": { "max_lines": 2000 }
}
```

### (f) Extension points + versioning
One extension point: `PanelSpec` with `panelApiVersion: 1`. Mismatched version
→ panel refused at load, TUI still starts (fail-open for viewing, fail-closed
for the plugin). Themes are a data-only map (`Record<Role,string>`) — data
can't break. Panel API v2, if ever needed, is *additive*: registry accepts
both versions side by side, same discipline as `abi.ts`.

Risk & constraint: Ink/React is the largest dependency in the whole system.
Containment: it lives in `tui/package.json` only — the core builds and runs
with zero TUI deps installed. `bun test` on core never imports React.

---

## 2. Plugins

### (a) What it is
The extension mechanism for the 10% — **and for the coding agent itself.**
There is one plugin system with capability kinds; `worker` is simply one of
the kinds. **Two-lane design:**
- **Lane A — MCP servers (runtime tools).** Out-of-process, language-agnostic,
  the industry contract. Used ONLY to add tools. The gateway speaks MCP as a
  client; an MCP tool is wrapped into Tool Contract v1 at the boundary
  (schema imported, `max_observe` applied, replay defaulted to `"never"`).
- **Lane B — local plugin dirs (in-process, TS).** A directory with a
  `plugin.json` manifest + an entry module, loaded by `core/plugin-host.ts`.
  Capabilities: `worker | tool | panel | adapter | templates | event_sink`.
  Our coding agent (`workers/own-agent/`) is a Lane B plugin with the
  `worker` capability — loaded, validated, versioned, and disable-able by the
  identical mechanism as a metrics sink.

No npm-install-at-runtime, ever (violates "no auto-updates, reproduce to the
byte"). A plugin arrives as files on disk, pinned by the operator, optionally
checksummed.

### (b) Module/file layout
```
core/plugin-host.ts       ★ loader: read manifest → validate vs schema/plugin.schema.json
                          #   → check hostApiVersion → import entry → register caps
schema/plugin.schema.json ★ manifest schema (additionalProperties: false)
workers/own-agent/          # the coding agent — a worker-capability plugin
  plugin.json  index.ts  loop.ts  context.ts
plugins/
  examples/hello-panel/
    plugin.json  index.ts
  <operator-installed dirs...>
```
(`workers/` and `plugins/` are two search roots for the same loader; the split
is purely for human navigation — the host treats them identically.)

### (c) Key interfaces
```ts
// plugin.json (manifest — validated before any code loads)
{
  "name": "own-agent",
  "version": "1.0.0",
  "hostApiVersion": 1,           // must equal the core's PLUGIN_HOST_VERSION
  "capabilities": ["worker"],    // subset of: worker|tool|panel|adapter|templates|event_sink
  "entry": "index.ts",
  "sha256": "<optional integrity pin set by operator>"
}

// core/plugin-host.ts — Host API v1 (the frozen contract)
export const PLUGIN_HOST_VERSION = 1;
export interface PluginApi {
  registerWorker(w: WorkerSpec): void;           // → supervisor registry
  registerTool(tool: ToolSpec): void;            // → gateway (still permission-gated)
  registerPanel(panel: PanelSpec): void;         // → TUI registry
  registerAdapter(name: string, a: Adapter): void;
  registerTemplates(dir: string): void;          // → template resolver search path
  onEvent(sink: (e: CoreEvent) => void): void;   // read-only tap; errors isolated
  config<T>(schema: JsonSchema): T;              // plugin's own validated config slice
  log: (level: "info"|"warn"|"error", msg: string) => void;
}
export interface Plugin { activate(api: PluginApi): void | Promise<void>; }

// WorkerSpec — the worker capability. NOTHING beyond ABI v1 crosses this line.
export interface WorkerSpec {
  worker_id: WorkerId;                       // "own-agent"
  abiVersion: 1;                             // Worker ABI version it speaks
  handle(op: WorkerOperation,                // the 6 operations in,
         emit: (e: WorkerEvent) => void      // the 11 events out —
        ): Promise<void>;                    // that is the ENTIRE surface
}
```
The supervisor holds a `Map<WorkerId, WorkerSpec>` and routes by
`task → config → worker_id`. It cannot call anything on a worker except
`handle()`. Our own agent's `loop.ts`/`context.ts` (Manus-style `max_observe`,
stuck detection, token-limit-as-state) live entirely behind `handle()` — the
core never sees them. A future out-of-process worker (e.g. Pi in a pinned
container) is a `WorkerSpec` whose `handle()` speaks NDJSON-over-stdio to the
process; the supervisor is unchanged.

### (d) Frozen core vs peripheral
- **Frozen:** `plugin-host.ts`, the manifest schema, `PluginApi` v1 (including
  `WorkerSpec`), the supervisor's dispatch, the MCP client in the gateway. The
  *host* is core; it is small (~250 lines) and boring: read, validate, import,
  register, catch.
- **Peripheral:** every plugin — **including `workers/own-agent/`** — and the
  MCP servers themselves. A crashing/broken worker plugin is skipped at load,
  or its tasks end in `FAILED` events; the core never needs an upgrade to
  cope (owner's hard requirement).
- **Sandboxing honesty:** Lane B plugins are in-process TypeScript = full
  trust. The security story is *provenance* (operator installs files, pins
  hashes, `plugins.allow` list), not runtime isolation. Anything untrusted or
  churn-prone goes in Lane A (MCP, out-of-process, kill-able) — or, for
  workers, out-of-process behind a stdio `WorkerSpec`. This split IS the
  sandbox boundary and should be the Security critic's focus.

### (e) Config surface
```jsonc
"plugins": {
  "dirs": ["./workers", "./plugins"],
  "allow": ["own-agent", "hello-panel"],     // allowlist; absent = disabled
  "settings": { "own-agent": { "max_observe": 4000, "stuck_threshold": 2 } }
},
"workers": {
  "default": "own-agent"                     // which worker_id gets new tasks
},
"mcp": {
  "servers": {
    "browser": { "command": "bunx", "args": ["@playwright/mcp@0.4.2"], "tools_allow": ["*"] }
  }
}
```

### (f) Extension points + versioning
- `hostApiVersion` integer, checked before import; mismatch → skip + log, never
  crash. Host API only ever *adds* methods within v1 (a 2026 plugin calling 6
  of 9 methods still works in 2029).
- Workers additionally declare `abiVersion` — checked against the ABI versions
  the supervisor supports. ABI evolution is add-a-new-schema-alongside, per
  `abi.ts`'s own header.
- Per-capability versions ride on their own contracts (`panelApiVersion`,
  Tool Contract v1) — each registry checks its own version.
- Disable = remove from `plugins.allow` + restart. No hot reload in v1
  (hot reload is where loaders stop being boring). MCP servers are the
  exception: they may connect/disconnect at runtime by design.

### (g) Deferred: Pi / OpenSwarm / Claude-Code workers (NOT designed now)
Per the owner's refinement these are out of scope for v1. The only present
obligation is neutrality, which the design above satisfies: a future
`workers/pi/` (vendored pinned pi-ai + pi-agent-core loop behind a stdio
`WorkerSpec`), `workers/openswarm/` (its orchestrator driving Codex/Claude
CLI), or `workers/claude-code/` is just another manifest + `registerWorker()`
call — no core file changes, no supervisor changes, no new ABI. Their detailed
design happens if/when they are scheduled.

---

## 3. Template

### (a) What it is
Versioned, file-based defaults for prompts (system prompt, planner prompt,
tool-result framing), task presets (a partial `Task`), and plan scaffolds
(Manus-style tracked step lists). Templates are **data, never code**:
Mustache-subset interpolation (`{{var}}`, `{{#section}}`) with a fixed
variable dictionary — no logic, no eval, no partial-include recursion.
Templates are consumed by *workers* (our own agent renders its system prompt
through the resolver); the core only provides the resolver.

### (b) Module/file layout
```
templates/
  manifest.json           # { "templateApiVersion": 1, "templates": { name: {file, vars} } }
  system/
    worker-base.md        # base system prompt (used by own-agent)
    planner.md            # Manus-style plan-as-context prompt
  tasks/
    default.json          # partial Task: budget/model/verification defaults
    bugfix.json           # preset: require_evidence: true, test command wired
  plans/
    feature.md            # tracked-step plan scaffold ([ ] / [→] / [✓])
core/template.ts        ★ resolver + renderer (~150 lines): layered lookup,
                        #   interpolate, warn-don't-throw on unknown vars
schema/template.schema.json ★
```

### (c) Key interfaces
```ts
// core/template.ts — Template API v1
export interface TemplateRef { name: string; version?: string } // "system/worker-base"
export interface TemplateResolver {
  /** Layered: user dir > plugin dirs > built-in. First hit wins per NAME. */
  resolve(ref: TemplateRef): { source: string; layer: "user"|"plugin"|"builtin" };
  render(ref: TemplateRef, vars: Record<string, string>): string;
}
// Task presets are JSON Merge Patch (RFC 7386) over tasks/default.json —
// base + patch composition with zero custom semantics.
```

### (d) Frozen core vs peripheral
- **Frozen:** the resolver/renderer (`core/template.ts`), the layered-lookup
  order, the variable dictionary for built-in call sites (documented list:
  `objective`, `plan_status`, `current_step`, `workspace`, `tool_names`, …),
  and the Mustache-subset grammar.
- **Peripheral:** every template file. Built-in templates ship with the repo
  but overriding one is a *file drop*, not a fork: put
  `~/.codeharness/templates/system/worker-base.md` (or a plugin template dir)
  and the resolver picks it up. Core upgrades never overwrite user layers.

### (e) Config surface
```jsonc
"templates": {
  "dir": "~/.codeharness/templates",      // user override layer
  "task_defaults": "tasks/default.json",  // which preset seeds new Tasks
  "pins": { "system/worker-base": "1.2.0" } // optionally pin a template version
}
```

### (f) Extension points + versioning
Each template file carries frontmatter `version:` (semver) and the manifest
carries `templateApiVersion: 1` (the grammar + variable dictionary). Renderer
warns when an override references an unknown `{{var}}` (renders it literal +
warns, never throws — a stale template must degrade, not crash the worker).
Composition is only base+patch (presets) and whole-file override (prompts).
No template inheritance chains — that's the readability line.

---

## 4. Tooling

### (a) What it is
Tool Contract v1 + the tool gateway. The gateway is the single chokepoint
between "worker wants X" and "X happens": registry lookup → permission check
against `task.permissions` → argument schema validation → execute (with
timeout, rooted in workspace) → truncate to `max_observe` → audit event →
return. All workers — ours today, any future worker — reach the world only
through this gateway.

### (b) Module/file layout
```
core/tool.ts     ★ Tool Contract v1 (interfaces below)
core/gateway.ts  ★ registry + permission gate + truncation + audit (~300 lines)
tools/           # standard toolset — peripheral, one file each, no shared helpers
  shell.ts       # bash -c with timeout, cwd = workspace   (perm: "shell")
  read.ts        # read file w/ offset/limit                (perm: "fs.read")
  edit.ts        # exact-match find/replace write           (perm: "fs.write")
  search.ts      # ripgrep content + glob file search       (perm: "fs.read")
  git.ts         # status/diff/add/commit/log; no push by default (perm: "git")
  test-run.ts    # run verification_policy.command, structured pass/fail (perm: "shell")
```
Six tools = the 90%. Everything else is an MCP server.

### (c) Key interfaces
```ts
// core/tool.ts — Tool Contract v1 (lifted from Pi's AgentTool, minimized)
export interface ToolSpec {
  toolApiVersion: 1;
  name: string;
  description: string;
  parameters: JsonSchema;                 // additionalProperties: false enforced
  permission: string;                     // must be ⊆ task.permissions to run
  replay: "never" | "safe";               // may this re-run on crash recovery?
  executionMode: "sequential" | "parallel";
  timeoutMs?: number;                     // default from config
  execute(args: unknown, ctx: ToolContext): Promise<ToolResult>;
}
export interface ToolContext {
  task_id: TaskId; attempt_id: AttemptId;
  workspace: string;                       // execution is rooted here
  emit: (e: WorkerEvent) => void;
}
export interface ToolResult {
  ok: boolean;
  output: string;        // gateway truncates to max_observe AFTER this returns
  evidence?: string[];   // paths/hashes feeding verification_policy
}
```
The own-agent worker's loop consumes tools through the gateway (it holds a
gateway handle, not the tool list) — so permissioning and truncation apply
identically to every worker, and the loop's minimal `Tool` shape is adapted
from `ToolSpec` inside the worker.

### (d) Frozen core vs peripheral
- **Frozen:** `tool.ts`, `gateway.ts` (permission model, truncation, audit,
  MCP client wrapping).
- **Peripheral:** every file in `tools/` (they only import `core/tool.ts`),
  all MCP servers, plugin-registered tools. A standard tool can be patched or
  replaced without a core release; its *contract* cannot.

### (e) Config surface
```jsonc
"tools": {
  "max_observe": 4000,            // chars of tool output entering context (Manus #1)
  "default_timeout_ms": 60000,
  "enable": ["shell","read","edit","search","git","test-run"],
  "shell": { "denylist": ["rm -rf /"], "network": false },
  "git":   { "allow_push": false }
}
```

### (f) Extension points + versioning
Registration is the only extension point: `PluginApi.registerTool` (Lane B) or
`mcp.servers.*` (Lane A). `toolApiVersion: 1` is checked at registration; MCP
tools get it stamped by the wrapper. Contract evolution is additive-only:
optional fields may be added to `ToolSpec`; required fields never. Name
collisions: built-ins win, plugin duplicate → refused + logged. Runtime
add/remove: MCP servers may connect/disconnect mid-daemon (OpenManus pattern);
Lane B tools are fixed at startup.

---

## 5. Visibility

### (a) What it is
One append-only event log per task, and everything else derived from it. The
11 `WorkerEvent`s + 4 core lifecycle events (`TASK_QUEUED`, `TASK_LEASED`,
`TASK_RETRIED`, `LEASE_EXPIRED`) wrapped in the `CoreEvent` envelope (§1c) are
**sufficient** — cost accounting derives from `MODEL_REQUEST_FINISHED.usage`,
the audit trail from `TOOL_*`, and the boring timeline ("12:00 leased / 12:04
checkpoint / 12:07 tests passed / 12:08 complete") from a trivial fold. No
second telemetry system. Because workers speak only ABI events, visibility is
worker-implementation-agnostic by construction.

### (b) Module/file layout
```
core/events.ts    ★ CoreEvent, EventBus (subscribe + replay-from-seq)
core/eventlog.ts  ★ NDJSON append via store.ts atomic discipline (fsync; one file
                  #   per task: <data_dir>/tasks/<task_id>/events.ndjson)
core/costs.ts     ★ fold usage events → per-task/per-model USD vs budget
core/daemon.ts    ★ GET /v1/events (SSE, ?since=seq), GET /v1/tasks/:id/timeline
plugins/examples/prometheus-sink/   # metrics sinks are event_sink plugins, not core
```

### (c) Key interfaces
```ts
// core/events.ts — Event Stream v1
export interface EventBus {
  emit(e: CoreEvent): void;                       // append + fan out; emit never throws
  subscribe(sinceSeq?: number): AsyncIterable<CoreEvent>; // replay + live tail
}
// Timeline = derived view, not stored state:
export function timeline(events: CoreEvent[]): Array<{ ts: string; line: string }>;
// Cost accounting = another fold:
export function costs(events: CoreEvent[], prices: PriceTable): CostReport;
```
Sink failures are isolated: a throwing `event_sink` plugin is detached and
logged; the log file is the source of truth regardless.

### (d) Frozen core vs peripheral
- **Frozen:** `CoreEvent` envelope, the NDJSON-file-per-task format (this is
  the *replay/debug archive*, so the format is a 3-year commitment like the
  ABI), seq monotonicity, the SSE endpoint, cost fold, timeline fold.
- **Peripheral:** metrics sinks (Prometheus, OTLP), dashboards, alerting,
  fancy TUI visualizations — all `event_sink` plugins reading the same stream.

### (e) Config surface
```jsonc
"visibility": {
  "data_dir": "~/.codeharness/data",
  "retain_days": 90,                       // event-log GC
  "timeline": true,                        // also write human timeline.txt per task
  "prices": { "anthropic/claude-x": { "input_per_mtok": 3.0, "output_per_mtok": 15.0 } },
  "redact": ["OPENAI_API_KEY", "AWS_SECRET"]   // patterns scrubbed before append
}
```

### (f) Extension points + versioning
`event_sink` capability (Host API v1). Event evolution follows ABI discipline:
new event *types* may be added to the union (consumers must ignore unknown
types — written into the contract doc and tested with a fuzz event); existing
event shapes never change. `CoreEvent` carries no schema-version field —
`seq`/`ts`/`task_id`/`worker_id`/`event` is the frozen envelope; the union
grows additively.

---

## 6. Weighted trade-off decisions

Weights (from the north star, sum = 1.0):
**Stability 0.35 · Readability/maintainer-fit 0.30 · Customizability 0.20 ·
Effort-to-build 0.15.** Scores 1–5. Weighted score = Σ(weight × score).

### Decision 1 — TUI framework: Ink/React vs pi-tui vs raw ANSI

| Criterion (weight) | Ink/React | pi-tui | raw ANSI |
|---|---|---|---|
| Stability (.35) | 3 — big dep tree, but pinned + isolated in `tui/`; React itself is stable | 2 — Pi permits breaking minors; inherits their lifecycle | 5 — zero deps |
| Readability (.30) | 4 — declarative panels, OpenSwarm precedent to crib | 3 — small but someone else's idioms, thin docs | 2 — escape-code plumbing obscures intent |
| Customizability (.20) | 5 — PanelSpec = React element; trivial plugin panels | 3 | 2 — every panel hand-rolls layout |
| Effort (.15) | 4 — vendor OpenSwarm's cockpit shape | 3 | 1 — weeks of terminal plumbing |
| **Weighted** | **3.85** | **2.60** | **2.80** |

**→ Ink/React**, with the containment rule: all TUI deps live in
`tui/package.json`, pinned exact; the core never imports from `tui/`; the TUI
is officially rewritable. (Note raw ANSI beats pi-tui — telling: inheriting
Pi's release lifecycle is exactly the problem this project exists to avoid.)

### Decision 2 — Plugin mechanism: MCP-only vs npm packages vs own loader vs two-lane

| Criterion (weight) | MCP-only | npm packages | own loader (dirs) | **two-lane (own loader + MCP)** |
|---|---|---|---|---|
| Stability (.35) | 4 — industry protocol, out-of-process; but MCP spec itself still moves | 2 — registry churn, install scripts, violates reproduce-to-byte | 4 — tiny frozen host we own | 4 |
| Readability (.30) | 3 — tools only; workers/panels/adapters/templates need a second mechanism anyway | 3 | 5 — ~250-line loader, everything inspectable on disk | 4 — two mechanisms, each simple |
| Customizability (.20) | 2 — cannot host workers, TUI panels, templates, providers | 4 | 4 | 5 — right lane per job |
| Effort (.15) | 3 | 3 | 4 | 3 — build both (each small) |
| **Weighted** | **3.15** | **2.85** | **4.30** | **4.15** |

Own-loader alone scores highest, but it cannot host *untrusted or churn-prone
runtime tools* out-of-process — the Security-relevant lane, and the design
brief names MCP as the runtime tool boundary (Manus pattern #6). The owner's
"agent is a plugin" requirement also demands a loader that can register a
`worker` capability, which MCP cannot express.
**→ Two-lane: own directory loader (Host API v1, incl. workers) for
in-process capabilities + MCP client strictly for runtime tools.** The second
mechanism is justified because each lane stays trivially simple and the trust
boundary is explicit. npm-as-plugin-transport is rejected outright (supply
chain + reproducibility).

### Decision 3 — Config format: YAML vs TOML vs JSONC + JSON Schema

| Criterion (weight) | YAML | TOML | **JSONC + JSON Schema** |
|---|---|---|---|
| Stability (.35) | 2 — parser dep, Norway/octal footguns, spec ambiguity | 4 — small dep, stable spec | 5 — parser is ~50 own lines (strip comments → JSON.parse); schema lives in-repo |
| Readability (.30) | 4 — human-friendly | 4 | 4 — comments allowed; nesting is honest about structure |
| Customizability (.20) | 3 | 3 | 5 — schema = validation + editor autocomplete + generated docs; plugin config slices (`PluginApi.config(schema)`) reuse the same machinery |
| Effort (.15) | 4 | 4 | 4 |
| **Weighted** | **3.10** | **3.70** | **4.55** |

**→ One `config/harness.jsonc`, validated against `schema/config.schema.json`
(`additionalProperties: false`) at startup; unknown key = fail fast with the
schema path.** This directly delivers "declarative, validated, discoverable"
and gives plugins validated config slices for free. No env vars except
secrets, which are *referenced* from config (`"api_key_env":
"ANTHROPIC_API_KEY"`), never read ad hoc.

---

## 7. What the critics should attack first

1. **Lane B plugins are in-process, full-trust — including the worker**
   (Security): the mitigation is provenance (allowlist + optional sha256 pin +
   files-on-disk review), not isolation. Acceptable for v1's single own-agent
   worker? Future third-party workers should be out-of-process `WorkerSpec`s.
2. **The loop moved out of core** (QA): `src/loop.ts` had the passing tests.
   Moving it to `workers/own-agent/loop.ts` must carry its tests along and
   add a supervisor-level ABI conformance test (fake worker, 6 ops, 11 events)
   that any future worker plugin can be run against.
3. **NDJSON event log as a 3-year frozen format** (SRE): growth/GC/redaction
   are config'd, but is one-file-per-task right at 10k tasks?
4. **Six built-in tools = 90%** (Product/QA): is the 90% claim tested? Propose
   a task-corpus benchmark before freezing the toolset list.
5. **No hot reload; restart-to-change plugins** (Product): deliberate — cheap
   restarts (durable store makes them safe) vs. loader complexity.

---

## Summary

**Recommended architecture:** rename `src/` → `core/` and keep it brutally
frozen (ABI v1, store, adapter, plus small new modules — events, tool
contract, gateway, config, plugin host, supervisor, template resolver, daemon
— each ≤ ~300 readable lines, additive-only contracts); move the agent loop
OUT of core into `workers/own-agent/`, the one v1 worker plugin, registered
through the same Plugin Host API v1 (`worker` capability, `WorkerSpec` =
6 operations in / 11 events out and nothing else) as any panel or sink — no
worker is privileged, and future Pi/OpenSwarm/Claude workers are deferred
designs that plug in with zero core changes; the TUI is a quarantined
Ink/React consumer of the frozen `CoreEvent` SSE stream, templates are
layered logic-free data files, tools live behind one permission-gated
`max_observe`-truncating gateway (six built-ins + MCP for the rest), and all
configuration is one JSON-Schema-validated JSONC file. **The single biggest
risk:** the own-agent worker quietly re-acquiring privileged status — because
it ships in-repo and in-process, convenience pressure will push core code to
import from `workers/` or grow ABI/PluginApi fields only it needs, which
would silently re-couple core to one agent and void both the 3-year freeze
and the "any worker can plug in" guarantee; the mitigations are the CI
import-boundary check (core imports nothing outside `core/`), the additive-
only rule on all v1 contracts, and a supervisor-level ABI conformance test
that our own worker must pass through the same door a stranger's worker would.
