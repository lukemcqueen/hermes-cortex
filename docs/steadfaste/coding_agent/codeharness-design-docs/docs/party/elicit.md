# Requirements Elicitation — Codeharness Five Surfaces

> Role: REQUIREMENTS ELICITATION (architecture party).
> Scope: WHAT must be true, prioritized — not the full design.
> Inputs read: `README.md`, `docs/manus-openmanus-notes.md`, `docs/design-brief.md`,
> and the frozen core source: `src/abi.ts`, `src/loop.ts`, `src/store.ts`, `src/adapter.ts`.
>
> North star (priority order): (1) core extremely stable, 90% out of the box;
> (2) easy to customize; (3) readable; (4) easily configurable.
> Owner allergies: auto-updates, unpinned versions, framework sprawl,
> env-var spaghetti, magic, hidden config.
>
> **Owner directive (2026-09-10, supersedes earlier drafts):** the coding agent
> itself is a PLUGIN — exactly like every other plugin, with no special status
> in the core. The core is the runtime; "our own tiny coding agent" is one
> worker plugin among peers. THIS ROUND builds only our own coding-agent
> plugin. Pi and OpenSwarm workers are explicitly deferred (Won't, this
> round); the only obligation toward them is that Worker ABI v1 stays neutral
> so a future Pi/OpenSwarm worker can plug in without a core change.

**Scoring conventions.**
RICE = (Reach × Impact × Confidence) / Effort, each dimension scored 1–5.
Reach = how many tasks/sessions touch it; Impact = effect on the north star;
Confidence = how sure we are the requirement is right as stated;
Effort = build + freeze cost. Higher score = do sooner.
MoSCoW = Must / Should / Could / Won't (for v1, 2026–2029 window).

**Global invariant (applies to every requirement below).** Nothing in these five
surfaces may require a change to `src/abi.ts` (Worker ABI v1: 11 `WorkerEvent`
variants, 6 `WorkerOperation` variants, `Task`, `TaskOutcome`). Any requirement
whose only satisfying design mutates the ABI is automatically rejected and must
be re-elicited. This is the design test stated in `manus-openmanus-notes.md`:
"a three-year-old worker can adopt new behavior without a core change."

---

## Surface 1 — TUI

The operator cockpit: supervise running tasks/workers, read the event stream,
steer, and stop. Reference shape: OpenSwarm's Ink cockpit (tabs Chat / Pipeline /
Logs / Monitor; `ContextBar` + `TabBar` + `HelpBar`; `PipelinePanel` →
`StageTimeline` + `SubagentTree` + `LiveLog`).

### 1a. Functional requirements

- **F-101 — Event-stream consumer, ABI-only.** The TUI consumes *exclusively*
  the 11 `WorkerEvent` types from `src/abi.ts` (plus core-emitted lifecycle
  records like lease/checkpoint from the store). It never imports worker
  internals, never parses a "Pi session" or "Claude conversation." Concretely:
  the TUI subscribes to a single append-only event feed (file tail or local
  SSE/socket exposed by the core daemon), each line one JSON `WorkerEvent`
  envelope `{ts, task_id, event}`.
- **F-102 — Task list + detail view.** Show every task in the store
  (`~/.codeharness/state.json` via `store.getTask`/an added `listTasks`) with
  status derived from events: pending / running / checkpointed / completed /
  failed / stopped(reason). Selecting a task shows its full event timeline.
- **F-103 — Live log panel.** A scrollback panel rendering `PROGRESS`,
  `TOOL_STARTED/FINISHED`, `MODEL_REQUEST_*` events in the OpenSwarm "boring
  log" shape: `12:00 task leased / 12:04 checkpoint / 12:07 tests passed /
  12:08 complete`. One line per event, timestamped, no ANSI art.
- **F-104 — Operator actions map 1:1 to WorkerOperations.** The only verbs the
  TUI exposes are the 6 ABI operations: `start`, `send` (steer/follow-up),
  `cancel`, `checkpoint`, `status`, `kill`. No TUI-invented verbs.
- **F-105 — Budget/cost display.** Per task, render budget consumption
  (tokens from `MODEL_REQUEST_FINISHED.usage`, turns counted from
  `MODEL_REQUEST_STARTED`, cost from the core's cost accounting) against
  `Task.budget` caps, with a visible warning at ≥80%.
- **F-106 — Headless parity.** Every piece of information the TUI shows must be
  obtainable without the TUI (CLI subcommand or reading the event log file).
  The TUI is a *view*, never the only access path. (Guards against the TUI
  becoming load-bearing frozen surface by accident.)
- **F-107 — Panel extension point (plugin-provided panels).** A frozen, tiny
  `Panel` interface (name, keybinding slot, render(events, tasks) → lines) so
  plugins can add tabs without patching TUI source. The stock panels
  (Tasks / Timeline / Logs / Monitor) are built against the same interface.
- **F-108 — Degraded-terminal fallback.** If the terminal lacks capabilities
  (no TTY, dumb term, CI), the same binary falls back to plain streaming log
  output rather than crashing.

### 1b. Non-functional requirements

- **NF-101 — Dependency budget.** TUI dependency tree ≤ ~10 direct pinned deps
  (Ink + React counted). Exact-pinned (`save-exact`), lockfile is ground truth,
  no postinstall scripts outside the reviewed allowlist. If Ink cannot meet
  this, a raw-ANSI implementation is preferred over adding deps.
- **NF-102 — Crash isolation.** A TUI crash must never affect a running task,
  worker, or the store. The TUI holds no locks and does no writes except
  issuing operations through the core's command channel.
- **NF-103 — Readability cap.** Whole TUI ≤ ~2,500 lines across ≤ ~15 files;
  one afternoon to read. A "100-component app" is a requirements failure.
- **NF-104 — Event-volume resilience.** Must remain responsive tailing ≥ 10k
  events / ≥ 20 concurrent tasks (bounded in-memory ring buffer, not
  unbounded arrays).
- **NF-105 — Zero required config.** `codeharness tui` works with no config
  file; all config (theme, keybindings, default tab) is optional and lives in
  the one declarative config file (see cross-surface F-001), never env vars.
- **NF-106 — Versioned independently.** The TUI is a peripheral (`tui 1.x`),
  semver-independent of `core 1.x`; a TUI release never forces a core upgrade.

### 1c. User stories

- **US-101 (operator supervises the swarm).** As the owner running 5 parallel
  tasks overnight, I open `codeharness tui` in the morning and immediately see
  which tasks completed, failed, or stalled, and why.
  *Acceptance:* with 5 tasks in the store in mixed states, the Tasks panel
  lists all 5 with correct status within 1s of launch; selecting a failed task
  shows the `FAILED` event with its `error` string and the preceding 20 events;
  no network access is required.
- **US-102 (operator steers a running task).** As an operator watching a worker
  go down a wrong path in LiveLog, I press the steer key, type a message, and
  it is delivered as `{op:"send"}` to that attempt.
  *Acceptance:* keypress opens an input bound to the selected task's current
  `attempt_id`; submitting produces exactly one `send` operation on the core's
  command channel; the sent message appears in the timeline; cancelling the
  input sends nothing.
- **US-103 (headless CI parity).** As a CI job, I run
  `codeharness status <task_id>` and get the same status/budget data the TUI
  shows, as JSON.
  *Acceptance:* command exits 0 with a JSON document containing status, event
  count, token/turn/cost consumption vs. budget; output is stable-schema
  (versioned) and identical in content to the TUI detail view.

### 1d. RICE + MoSCoW

| Req | R | I | C | E | RICE | MoSCoW |
|---|---|---|---|---|---|---|
| F-101 event-stream consumer | 5 | 5 | 5 | 2 | 62.5 | Must |
| F-102 task list/detail | 5 | 4 | 5 | 2 | 50.0 | Must |
| F-103 live log panel | 5 | 4 | 5 | 2 | 50.0 | Must |
| F-104 ops = 6 ABI verbs | 4 | 5 | 5 | 2 | 50.0 | Must |
| F-105 budget/cost display | 4 | 4 | 4 | 2 | 32.0 | Should |
| F-106 headless parity | 4 | 4 | 5 | 2 | 40.0 | Must |
| F-107 panel extension point | 2 | 3 | 3 | 3 | 6.0 | Should |
| F-108 degraded fallback | 3 | 3 | 4 | 1 | 36.0 | Should |
| NF-101 dep budget | 5 | 5 | 5 | 2 | 62.5 | Must |
| NF-102 crash isolation | 5 | 5 | 5 | 1 | 125.0 | Must |
| NF-103 readability cap | 5 | 4 | 4 | 2 | 40.0 | Must |
| NF-104 event volume | 3 | 3 | 4 | 2 | 18.0 | Should |
| NF-105 zero required config | 5 | 4 | 5 | 1 | 100.0 | Must |
| NF-106 independent semver | 5 | 5 | 5 | 1 | 125.0 | Must |
| Themes beyond light/dark, mouse support, chat-with-worker panel | – | – | – | – | – | Could |
| Web dashboard, remote multi-host cockpit | – | – | – | – | – | Won't (v1) |
| SubagentTree multi-worker drill-down (OpenSwarm shape) | – | – | – | – | – | Won't (this round — single own-agent worker first) |

### 1e. Open questions

- **Q-101:** Ink/React vs. Pi's `pi-tui` vs. raw ANSI? Ink pulls React into the
  dep tree (tension with NF-101); raw ANSI raises Effort on F-102/103. Needs an
  explicit decision with a dep-tree count for each option.
- **Q-102:** Transport for the live feed — tail the event journal file
  (simplest, crash-safe, no daemon) vs. SSE from a core daemon (OpenSwarm
  shape, needed anyway for multi-process)? Is there a core daemon at all in v1?
- **Q-103:** Is `Chat` a v1 tab? `send` exists in the ABI, but full
  conversational rendering pulls in message-format knowledge the core
  deliberately lacks. Proposal: steering input yes, chat transcript no —
  confirm with owner.
- **Q-104:** Where does the TUI get the command channel to issue operations —
  writing to the store, a unix socket, or spawning `codeharness <op>`?

---

## Surface 2 — Plugins

The extension mechanism for the customizable 10% — AND, per the owner
directive, the mechanism by which **the coding agent itself** attaches to the
core. The core is the runtime (state machine, queue/leases, store, gateway,
governance, journal); every agent, including our own, is a worker plugin
speaking Worker ABI v1.

### 2a. Functional requirements

- **F-200 — The coding agent is a plugin, not the core. (OWNER DIRECTIVE)**
  Our own coding agent — the composition of `src/loop.ts` + a real `Adapter` +
  the standard toolset into a runnable worker — ships as a worker plugin
  (proposed `plugins/worker-own/`) registered through the same manifest,
  loading, validation, versioning, and disable path as every other plugin
  (F-201–F-206). It has zero private hooks into the core: it communicates only
  via `WorkerEvent` / `WorkerOperation` / `Task` / `TaskOutcome` from
  `src/abi.ts`. Litmus tests: (a) deleting `plugins/worker-own/` leaves the
  core compiling, its tests green, and `codeharness plugins` clean; (b) the
  core source contains no import from, and no string reference to, the own
  agent; (c) `codeharness plugins` lists `worker-own` with the same metadata
  shape as any other plugin. Note: `loop.ts`/`adapter.ts` remain in the core
  repo as *vendored reference pieces* a worker may reuse — the core never
  executes them itself; if that dual role proves confusing, they move into the
  plugin (see Q-206).
- **F-201 — Single plugin manifest + entry contract.** A plugin is a directory
  (or pinned npm package) with `plugin.json`: `{name, version,
  abi_compat: "1"}` plus declared capability sections, and one entry module
  exporting a typed `register(host)` function. No decorators, no reflection,
  no auto-scanning of node_modules — plugins load only if explicitly listed
  in config (F-204).
- **F-202 — Five capability slots, enumerated and closed.** A plugin may
  contribute exactly: (1) **workers** (a `WorkerDriver` speaking Worker ABI v1
  — the slot `worker-own` uses; F-200), (2) tools (the frozen tool contract,
  Surface 4), (3) adapters (implement `Adapter.complete` from
  `src/adapter.ts`), (4) TUI panels (F-107 `Panel` interface), (5) templates
  (Surface 3 template packages) — plus a read-only event-sink subscription
  (F-505). Anything else is out of scope for v1. The host object passed to
  `register()` exposes only these registration functions.
- **F-203 — Compatibility declaration + refusal.** Every plugin declares
  `abi_compat` and per-slot interface versions (`worker_api: "1"`,
  `tool_api: "1"`, `panel_api: "1"`). The loader refuses (with a clear
  one-line error, not a warning) any plugin whose declared versions the host
  doesn't support. A 2026 plugin declaring v1 interfaces must load unmodified
  in 2029.
- **F-204 — Explicit, declarative loading.** Plugins are enabled only via the
  config file, e.g. `plugins: [{ path: "./plugins/worker-own" }, { path:
  "./plugins/gitlab-tools", integrity: "sha256-…" }]`. No env vars, no global
  plugin dir auto-load, no network fetch at load time. Disabling =
  removing/commenting the entry; next start is clean.
- **F-205 — Load-time validation.** On load, the host validates the manifest
  schema, checks the integrity hash (if given), and dry-validates every
  contributed tool schema. A plugin failing validation is skipped and reported;
  it never partially registers.
- **F-206 — Failure isolation.** A plugin tool that throws is encoded as a
  failed tool result (existing `loop.ts` behavior, lines 79–87); a plugin
  panel that throws is unmounted with an error line; a worker plugin that
  crashes produces `FAILED`/`STOPPED` events and a recorded `TaskOutcome`,
  never a core crash. A crashing plugin never takes down the loop, the store,
  or other plugins.
- **F-207 — MCP servers as arm's-length plugins.** An MCP server may be
  attached as a *tool provider* via one built-in bridge plugin (the OpenManus
  boundary pattern), configured declaratively (command + pinned version +
  allowed tool names). MCP is a supported transport for tools, not a second
  plugin system.
- **F-208 — `codeharness plugins` introspection.** A CLI command lists loaded
  plugins with name, version, declared compat, contributed slots, and
  enabled/disabled/failed state. Nothing about plugins is hidden.
- **F-209 — ABI neutrality proven, future workers deferred.** Worker ABI v1
  and the `worker_api` plugin slot stay strictly neutral: nothing in the core
  or the plugin host may assume the own agent's internals (its loop shape, its
  message format, its toolset). The neutrality proof is a CI fixture: a second
  trivial worker plugin (a scripted fake, ~50 lines) runs the same task suite
  through the same slot. **Pi and OpenSwarm worker plugins are explicitly NOT
  designed or built this round** — they are deferred future work that this
  requirement keeps possible without a core change.

### 2b. Non-functional requirements

- **NF-201 — Frozen plugin API surface.** The `register(host)` host interface
  is versioned like the ABI: additive-only within v1, documented in one file
  (`src/plugin-api.ts` proposed), small enough to read in 10 minutes.
- **NF-202 — Stock install covers the 90%.** The stock install — core + the
  `worker-own` plugin + standard toolset + stock templates + stock panels —
  covers the 90% path with zero additional plugins and zero config beyond
  enabling `worker-own`. Third-party plugins are strictly the 10%.
- **NF-203 — No plugin dependency injection into core.** Plugins cannot patch,
  wrap, or monkey-patch core modules; the host passes capabilities in,
  plugins never reach out. This applies with full force to `worker-own`: being
  first-party earns it no back door. (Enforced by review + by not exporting
  core internals from the package entry.)
- **NF-204 — Deterministic load order.** Plugins load in config-file order;
  name collisions (two plugins registering tool `git`, or two workers with the
  same name) are a hard startup error, not last-wins.
- **NF-205 — Pinning discipline extends to plugins.** npm-delivered plugins are
  exact-pinned in the lockfile; path plugins are versioned in the repo or
  hash-checked. `latest` anywhere in plugin config is a validation error.
- **NF-206 — Own agent versions independently.** `worker-own` carries its own
  semver (`worker-own 1.x`), releases independently of `core 1.x`, and a
  broken own-agent release never forces a core change — the same rule the
  README already states for `worker-pi` / `worker-claude`.

### 2c. User stories

- **US-200 (the own agent is provably just a plugin).** As the owner, I want
  proof that the coding agent has no special status, so the core stays frozen
  when the agent evolves.
  *Acceptance:* with `worker-own` removed from config, `bun test` (core suite)
  passes and `codeharness plugins` lists zero workers; re-adding the config
  entry restores full task execution; `grep -r "worker-own\|worker_own"
  src/` returns nothing; the CI neutrality fixture (F-209) runs a task
  end-to-end through a second, trivial worker plugin using the identical
  `worker_api` slot.
- **US-201 (add a company-internal tool).** As the owner, I write a
  `deploy-preview` tool plugin in one file + manifest, add its path to config,
  restart, and the worker can call it.
  *Acceptance:* plugin dir with `plugin.json` + `index.ts` (< 100 lines) is
  listed in config; `codeharness plugins` shows it loaded with 1 tool; a fake-
  adapter test task invoking `deploy-preview` produces `TOOL_FINISHED ok:true`;
  removing the config line and restarting removes the tool with no residue.
- **US-202 (three-year-old plugin still works).** As a future maintainer in
  2029 on core 1.x, I load an unmodified 2026 plugin declaring
  `abi_compat: "1", tool_api: "1"` and it works; a plugin declaring
  `tool_api: "2"` (unknown) is refused with an actionable message.
  *Acceptance:* compatibility test suite in core CI loads a frozen fixture
  plugin from 2026 and exercises its tool end-to-end; the unknown-version
  fixture produces exit-fail at startup with a message naming the plugin, the
  declared version, and the supported versions.
- **US-203 (disable a misbehaving plugin cleanly).** As an operator seeing a
  plugin tool fail repeatedly, I comment out its config entry and restart;
  everything else runs unchanged.
  *Acceptance:* after disable, `codeharness plugins` no longer lists it, tasks
  referencing its tool get the standard "tool not found" tool-result error
  (loop.ts line 77 behavior), and no startup warning persists.

### 2d. RICE + MoSCoW

| Req | R | I | C | E | RICE | MoSCoW |
|---|---|---|---|---|---|---|
| F-200 coding agent is a plugin (owner directive) | 5 | 5 | 5 | 2 | 62.5 | Must |
| F-201 manifest + register contract | 4 | 5 | 4 | 3 | 26.7 | Must |
| F-202 five closed capability slots | 4 | 5 | 4 | 2 | 40.0 | Must |
| F-203 compat declaration + refusal | 4 | 5 | 5 | 2 | 50.0 | Must |
| F-204 explicit declarative loading | 5 | 5 | 5 | 1 | 125.0 | Must |
| F-205 load-time validation | 4 | 4 | 4 | 2 | 32.0 | Must |
| F-206 failure isolation | 4 | 5 | 4 | 3 | 26.7 | Must |
| F-207 MCP bridge plugin | 3 | 4 | 3 | 4 | 9.0 | Should |
| F-208 plugins introspection CLI | 4 | 3 | 5 | 1 | 60.0 | Should |
| F-209 ABI neutrality fixture (future workers stay possible) | 3 | 5 | 4 | 2 | 30.0 | Must |
| NF-201 frozen plugin API | 4 | 5 | 4 | 2 | 40.0 | Must |
| NF-202 stock install covers 90% | 5 | 5 | 5 | 1 | 125.0 | Must |
| NF-203 no core patching (incl. worker-own) | 4 | 5 | 4 | 1 | 80.0 | Must |
| NF-204 deterministic order/collisions | 3 | 4 | 5 | 1 | 60.0 | Must |
| NF-205 plugin pinning | 4 | 5 | 5 | 1 | 100.0 | Must |
| NF-206 own agent versions independently | 5 | 5 | 5 | 1 | 125.0 | Must |
| Sandboxed (process-isolated) plugin execution | – | – | – | – | – | Could |
| **Pi worker plugin (vendored pinned pi loop)** | – | – | – | – | – | **Won't (this round — deferred; F-209 keeps it possible)** |
| **OpenSwarm worker plugin (orchestrator driving Codex/Claude CLI)** | – | – | – | – | – | **Won't (this round — deferred; patterns already vendored in store/TUI)** |
| Plugin marketplace/registry, hot reload | – | – | – | – | – | Won't (v1) |

### 2e. Open questions

- **Q-201:** In-process plugins (simple, fast, but a plugin can still crash the
  process or exfiltrate) vs. subprocess isolation? For tools/panels/templates,
  in-process is the lean default; for **worker plugins** the README's model is
  immutable images / separate processes. Does `worker-own` run in-process in
  v1 (simplest) or out-of-process from day one (matches the ABI's
  transport-oriented design)? Needs the owner's call — it shapes `worker_api`.
- **Q-205:** What exactly is the `worker_api: "1"` surface — a `WorkerDriver`
  interface (`start(task) → AsyncIterable<WorkerEvent>` + `op(WorkerOperation)`),
  or a process/transport spec (spawn command + JSONL over stdio)? The second is
  more neutral for future non-TS workers (Pi, OpenSwarm, anything); the first
  is simpler this round. Must be answered before F-200/F-209 freeze.
- **Q-206:** Do `src/loop.ts` and `src/adapter.ts` stay in the core repo as
  vendored reference code that `plugins/worker-own` imports, or move into the
  plugin directory entirely? Owner's "no special status" pushes toward moving
  them; "readable, one sitting" pushes toward keeping the reference loop
  visible in `src/`.
- **Q-203:** TypeScript plugins executed via Bun directly, or must plugins ship
  compiled JS? Bun runs TS natively — but does that tie the 3-year contract to
  Bun's TS semantics?
- **Q-204:** Integrity hash mandatory or optional for path-local plugins?

---

## Surface 3 — Template (templating)

The boring defaults: system/planner prompts, task templates, workflow templates
(e.g. Manus-style "plan is the context" prompt shapes), and scaffolds for new
plugins/workers. Overridable without forking.

### 3a. Functional requirements

- **F-301 — Templates are files, not code.** Every prompt/task template is a
  plain file on disk (`templates/` in the repo: e.g.
  `templates/system/worker-base.md`, `templates/planning/plan-status.md` —
  the Manus `CURRENT PLAN STATUS / YOUR CURRENT TASK` shape,
  `templates/task/bugfix.json`), with a minimal, documented placeholder syntax
  (`{{objective}}`, `{{plan_status}}`, `{{step}}`). No template logic
  (no loops/conditionals) in v1 — composition happens via F-303, not a
  template language.
- **F-302 — Deterministic override resolution.** Lookup order is exactly:
  (1) task-level inline override, (2) project `./.codeharness/templates/`,
  (3) user `~/.codeharness/templates/`, (4) built-in `templates/`. First hit
  wins; the resolution is printable (`codeharness template which
  system/worker-base` prints the winning path and the shadowed ones). No other
  sources.
- **F-303 — Base + patch composition.** A user override may either replace a
  template wholly or declare `extends: system/worker-base@1` and provide named
  section overrides (front-matter + named blocks). Composition result is
  materializable: `codeharness template render <name> --vars file.json` prints
  the final text.
- **F-304 — Versioned template identity.** Every built-in template carries a
  name + integer version in front-matter (`name: system/worker-base`,
  `version: 1`). Overrides pin the base version they extend; extending a base
  version the install doesn't have is a startup error (same refusal discipline
  as plugins F-203).
- **F-305 — Task templates prefill the ABI `Task`.** A task template is a JSON
  file producing a partial `Task` (permissions, budget, model_policy,
  verification_policy defaults) + a prompt-template reference.
  `codeharness run --template bugfix --objective "…"` merges template →
  config defaults → CLI flags, in that documented precedence.
- **F-306 — Frozen render surface, evolving content.** The template *engine*
  (placeholder syntax + resolution + composition rules) is part of the frozen
  peripheral contract (`template_api: "1"`); template *content* may change
  freely per release. Content changes never require engine changes. Prompt
  templates are consumed by the `worker-own` plugin (the worker layer) —
  the core itself never renders prompts into model requests.
- **F-307 — Stock template set covers the 90%.** Ship, at minimum: the
  `worker-own` base system prompt; Manus-style plan-status prompt; task
  templates `bugfix`, `feature`, `refactor`, `investigate`; a plugin scaffold
  (`codeharness new plugin <name>` emits a working F-201-conformant skeleton,
  including the worker slot variant).

### 3b. Non-functional requirements

- **NF-301 — Inspectability.** Any prompt actually sent to a model must be
  reproducible after the fact: the rendered template (name, version, resolved
  source path, variable-values hash) is recorded per attempt in the event
  journal / audit trail. No hidden prompt assembly.
- **NF-302 — No magic variables.** The set of available placeholders per
  template type is a documented closed list; an unknown placeholder in a
  template is a validation error at load, not silent empty-string at render.
- **NF-303 — Plain-text diffability.** Templates and overrides are reviewable
  with `git diff`; no binary/DB storage, no runtime-generated templates.
- **NF-304 — Render determinism.** Same template + same variables →
  byte-identical output (no timestamps/randomness injected by the engine).
- **NF-305 — Size discipline.** Template engine ≤ ~400 lines, zero new deps
  (string replacement + front-matter parse; no Handlebars/Nunjucks/EJS).

### 3c. User stories

- **US-301 (override the system prompt without forking).** As the owner, I want
  my worker system prompt to add house rules (commit style, test commands)
  without editing `templates/` in the repo.
  *Acceptance:* creating `~/.codeharness/templates/system/worker-base.md` with
  `extends: system/worker-base@1` + one overridden section changes rendered
  output (verified via `template render`); `template which` shows my file
  winning and the built-in shadowed; deleting my file restores stock behavior;
  the core repo is untouched (`git status` clean).
- **US-302 (repeatable task kickoff).** As an operator, I start a bugfix task
  with one command and get consistent budget/permissions/verification defaults.
  *Acceptance:* `codeharness run --template bugfix --objective "fix flaky test
  X"` produces a stored `Task` whose `budget`, `permissions`, and
  `verification_policy.require_evidence: true` match
  `templates/task/bugfix.json`; a CLI flag `--max-turns 5` overrides only that
  field; the merged provenance (template name + version) is recorded with the
  task.
- **US-303 (audit what the model saw).** As a reviewer of a bad outcome, I
  reconstruct the exact system prompt used by attempt N.
  *Acceptance:* given a task_id/attempt_id, a CLI command prints the template
  name, version, resolved path, and rendered text (or its stored hash +
  re-render with recorded variables) matching what was sent.

### 3d. RICE + MoSCoW

| Req | R | I | C | E | RICE | MoSCoW |
|---|---|---|---|---|---|---|
| F-301 templates are files | 5 | 5 | 5 | 1 | 125.0 | Must |
| F-302 deterministic override order | 5 | 5 | 5 | 2 | 62.5 | Must |
| F-303 base + patch composition | 4 | 4 | 3 | 3 | 16.0 | Should |
| F-304 versioned identity + refusal | 4 | 4 | 4 | 2 | 32.0 | Must |
| F-305 task templates → ABI Task | 5 | 4 | 5 | 2 | 50.0 | Must |
| F-306 frozen engine / evolving content | 4 | 5 | 4 | 2 | 40.0 | Must |
| F-307 stock set covers 90% | 5 | 4 | 4 | 3 | 26.7 | Must |
| NF-301 prompt inspectability | 4 | 5 | 5 | 2 | 50.0 | Must |
| NF-302 no magic variables | 4 | 4 | 5 | 1 | 80.0 | Must |
| NF-303 diffability | 5 | 4 | 5 | 1 | 100.0 | Must |
| NF-304 render determinism | 4 | 4 | 5 | 1 | 80.0 | Must |
| NF-305 engine ≤400 lines, 0 deps | 4 | 4 | 4 | 1 | 64.0 | Must |
| Conditionals/loops in templates | – | – | – | – | – | Won't (v1) |
| Template linting beyond placeholder check | – | – | – | – | – | Could |
| Templates for foreign workers (Pi/OpenSwarm prompt packs) | – | – | – | – | – | Won't (this round — no foreign workers this round) |

### 3e. Open questions

- **Q-301:** Is `extends` + named-section patching (F-303) worth it in v1, or
  is whole-file replacement (F-302 alone) enough for the 10%? Section patching
  is the most magic-adjacent thing on this surface.
- **Q-302:** Front-matter format — YAML (needs a dep or hand-parser) vs. JSON
  header vs. sibling `.json` metadata file? Interacts with NF-305 (zero deps).
- **Q-303:** Since the coding agent is a plugin, template *rendering* for
  prompts clearly belongs in the worker plugin — but does the *engine* (F-306)
  live in the core (shared by all future workers, one implementation) or is it
  a library the worker plugin vendors? Core-side keeps it frozen and shared;
  plugin-side keeps the core smaller.
- **Q-304:** Should `Task.objective` itself ever be templated, or is templating
  strictly for prompts/policies around the verbatim objective?

---

## Surface 4 — Tooling

The tool gateway and tool contract: how tools are defined, validated, executed,
bounded, and extended (Pi `AgentTool` + OpenManus MCP boundary + `max_observe`).

### 4a. Functional requirements

- **F-401 — Frozen tool contract v1.** Extend today's minimal
  `Tool {name, description, execute}` in `src/loop.ts` into a frozen
  `AgentTool` contract (proposed `src/tool.ts`, `tool_api: "1"`): JSON-schema
  (TypeBox, `additionalProperties: false`) parameter validation;
  `execute(call, ctx)`; `replay: "never" | "safe"`; `executionMode:
  "sequential" | "parallel"`; optional `prepareArguments`. Arguments failing
  schema validation are returned as a failed tool result *before* execute runs.
- **F-402 — Standard toolset for the 90%.** Ship built-in tools: `shell`
  (command exec inside the task `workspace`, permission-gated), `read_file`,
  `edit_file` (find/replace or unified-diff apply), `write_file`, `search`
  (ripgrep-style content + name), `git` (status/diff/commit/log subset),
  `run_tests` (executes `verification_policy.command`). Nothing else in core.
- **F-403 — Permission gating at the gateway.** Every tool declares required
  permission strings; the gateway checks them against `Task.permissions`
  before execution. Denial is a failed tool result naming the missing
  permission (visible to model and operator), never a silent skip. `shell`
  and `write`/`edit` are deny-by-default without the corresponding permission.
- **F-404 — Bounded tool output (`max_observe`).** Every tool result is
  truncated to a configurable per-tool char budget (global default, e.g.
  20,000 chars, head+tail) before entering the message list, with an explicit
  truncation marker including original size. This happens in the gateway, not
  in each tool.
- **F-405 — Workspace confinement.** File and shell tools resolve all paths
  inside `Task.workspace`; escaping paths (`..`, absolute outside workspace,
  symlink escape) is a failed tool result. This is the tool-layer face of the
  core's "workspace isolation."
- **F-406 — Runtime tool extension only via plugins/MCP.** Tools are added by
  (a) built-ins, (b) plugin registration (F-202), (c) the MCP bridge (F-207)
  — declared in config, resolved at startup. No runtime self-modification of
  the toolset by the running agent (matches "an agent does not mutate its own
  runtime").
- **F-407 — Tool event emission.** The gateway emits the ABI tool triplet
  (`TOOL_REQUESTED`, `TOOL_STARTED`, `TOOL_FINISHED{ok}`) for every execution
  — already the `loop.ts` shape — plus records tool name, args hash, duration,
  and truncated-result hash to the audit trail (Surface 5).
- **F-408 — Parallel-safe execution semantics.** Tools declaring
  `executionMode: "parallel"` may run concurrently within a turn; `sequential`
  tools serialize; mixed batches preserve call order for sequential ones.
  Semantics documented and tested — no implicit concurrency surprises.
- **F-409 — Replay policy honored on recovery.** After crash/checkpoint
  restore, only `replay: "safe"` tools may be re-executed automatically;
  `"never"` tools require the recorded result or a fresh model decision.

### 4b. Non-functional requirements

- **NF-401 — Tool contract frozen for 3 years.** `tool_api: "1"` is
  additive-only; a tool written against it in 2026 passes the compatibility
  fixture suite in 2029 (same regime as US-202).
- **NF-402 — Deterministic, testable tools.** Every built-in tool has unit
  tests with a fixture workspace; tool behavior contains no environment
  sniffing beyond the declared ctx (workspace path, permissions, config).
- **NF-403 — Bounded execution.** Every tool execution has a timeout (per-tool
  default, config-overridable); timeout is a failed tool result (`ok: false`),
  never a hung loop.
- **NF-404 — No output-format magic.** Tool results are plain strings (or
  JSON-stringified), as `loop.ts` already does — no rich objects smuggled
  through side channels.
- **NF-405 — Size discipline.** Gateway ≤ ~600 lines; each built-in tool one
  file, ≤ ~200 lines, dependency-free where possible (ripgrep may be a pinned
  binary dependency — decide in Q-403).

### 4c. User stories

- **US-401 (the 90% task needs no tool config).** As the owner, I run a bugfix
  task on a repo with zero tool configuration and the worker can read, search,
  edit, run tests, and commit.
  *Acceptance:* fresh install + `codeharness run --template bugfix` on a
  fixture repo: the worker completes a scripted (fake-adapter) sequence using
  `search → read_file → edit_file → run_tests → git commit`, all
  `TOOL_FINISHED ok:true`, with no tools section present in config.
- **US-402 (huge output cannot flood context).** As an operator, when a worker
  cats a 5 MB file, the context stays bounded.
  *Acceptance:* `read_file` on a 5 MB fixture yields a tool message ≤ the
  configured `max_observe` budget with a truncation marker stating original
  size; the subsequent `MODEL_REQUEST_STARTED` proceeds normally; the full
  untruncated output is NOT stored in messages (may be referenced on disk).
- **US-403 (permission denial is visible and safe).** As an operator running a
  read-only investigation task, the worker cannot write.
  *Acceptance:* task with `permissions: ["read"]`: `edit_file` and `shell`
  calls return failed tool results naming the missing permission;
  `TOOL_FINISHED ok:false` events appear; no file in the workspace is
  modified (verified by checksum).
- **US-404 (crash recovery honors replay policy).** As the core recovering an
  attempt after a crash mid-turn, side-effecting tools are not silently re-run.
  *Acceptance:* fixture: a `replay:"never"` tool (e.g. `git commit`)
  interrupted after execution but before result persistence is NOT re-executed
  on recovery; a `replay:"safe"` tool (`read_file`) is; both paths covered by
  tests.

### 4d. RICE + MoSCoW

| Req | R | I | C | E | RICE | MoSCoW |
|---|---|---|---|---|---|---|
| F-401 frozen tool contract | 5 | 5 | 5 | 2 | 62.5 | Must |
| F-402 standard toolset | 5 | 5 | 4 | 3 | 33.3 | Must |
| F-403 permission gating | 5 | 5 | 4 | 2 | 50.0 | Must |
| F-404 max_observe truncation | 5 | 5 | 5 | 1 | 125.0 | Must |
| F-405 workspace confinement | 5 | 5 | 4 | 2 | 50.0 | Must |
| F-406 extension via plugins/MCP only | 4 | 5 | 4 | 1 | 80.0 | Must |
| F-407 tool event emission | 5 | 4 | 5 | 1 | 100.0 | Must |
| F-408 parallel semantics | 3 | 3 | 3 | 2 | 13.5 | Should |
| F-409 replay policy on recovery | 3 | 5 | 3 | 4 | 11.3 | Should |
| NF-401 3-year tool contract | 5 | 5 | 4 | 2 | 50.0 | Must |
| NF-402 testable tools | 5 | 4 | 5 | 2 | 50.0 | Must |
| NF-403 timeouts | 5 | 5 | 5 | 1 | 125.0 | Must |
| NF-404 plain-string results | 5 | 4 | 5 | 1 | 100.0 | Must |
| NF-405 size discipline | 4 | 4 | 4 | 1 | 64.0 | Must |
| Browser tool, network fetch tool | – | – | – | – | – | Could (plugin) |
| Container-per-tool sandboxing | – | – | – | – | – | Won't (v1; workspace + permissions instead) |

### 4e. Open questions

- **Q-401:** Where does the gateway live — in the frozen core (permission +
  truncation + audit are governance, arguably core) or inside the
  `worker-own` plugin (the Manus notes place `max_observe` worker-side, and
  the owner directive says the agent is just a plugin)? Sharpened by F-200:
  if the gateway is core, it must be usable by ANY future worker plugin, not
  shaped around our own agent. Needs the architecture role's call because it
  decides what's frozen.
- **Q-402:** TypeBox as the schema library adds a dep to the frozen surface —
  acceptable (Pi pins it too), or hand-rolled minimal JSON-schema validation?
- **Q-403:** `search` via bundled ripgrep binary (pinned digest, "reproduce to
  the byte") vs. pure-TS search (slower, zero binary deps)?
- **Q-404:** Is `edit_file` find/replace-based or diff-apply-based? This
  determines the biggest single failure mode workers will hit.
- **Q-405:** Exact permission-string vocabulary (`read`, `write`, `shell`,
  `git_write`, `network`?) — must be enumerated before F-403 freezes; it is
  effectively part of the ABI's `Task.permissions` semantics.

---

## Surface 5 — Visibility (observability)

How the operator sees what happened and what it cost: event stream contract,
structured logs, audit trail, cost accounting, checkpoint/replay visibility.

### 5a. Functional requirements

- **F-501 — Append-only event journal per task.** Every `WorkerEvent` (plus
  core lifecycle events: task created, leased, lease renewed/expired, outcome
  recorded) is appended, envelope-wrapped `{ts, seq, task_id, source, event}`,
  to a per-task JSONL file (proposed `~/.codeharness/events/<task_id>.jsonl`)
  using the same fsync/rename discipline as `store.ts`. This journal is the
  single source of truth for all views (TUI F-101, CLI, audit).
- **F-502 — The boring human log.** A derived, human-readable per-task log in
  the OpenSwarm shape — one line per significant event:
  `12:00 task leased · 12:04 checkpoint ckpt-2 · 12:07 tests passed · 12:08
  complete`. Produced by rendering the journal (`codeharness log <task_id>`),
  never a separate write path that can drift.
- **F-503 — Cost accounting from usage events.** Core aggregates
  `MODEL_REQUEST_FINISHED.usage` per attempt/task against `budget.max_tokens`
  and (via a pinned, config-declared price table file — not a live API)
  against `budget.max_cost_usd`. `codeharness cost <task_id>` and a store
  rollup expose totals. Prereq: `loop.ts` line 55 currently hardcodes zero
  usage — real usage plumbing from `Adapter` is required in the `worker-own`
  plugin (add optional `usage` to `AssistantTurn`; additive, non-breaking).
- **F-504 — Audit trail for every mutation.** Every operation the core sends
  (`start/send/cancel/checkpoint/status/kill`, with initiator: cli|tui|plugin),
  every tool execution (name, args hash, ok, duration, result hash — F-407),
  and every prompt render (NF-301) appears in the journal. The question "what
  did the system do and why" is answerable from files on disk alone.
- **F-505 — Event sink extension point.** Plugins can register a read-only
  `EventSink {onEvent(envelope)}` (fed *after* the journal write, so a slow or
  crashing sink can never lose or delay the durable record). Stock sinks:
  stdout-JSONL and the human-log renderer. Metrics/OTel/webhooks are plugins,
  never core.
- **F-506 — Checkpoint visibility + replay inspection.** `CHECKPOINT` events
  and stored checkpoint metadata are listable (`codeharness checkpoints
  <task_id>`); recovery/restore actions themselves emit journal events so a
  resumed task's history reads continuously.
- **F-507 — Status derivation is pure.** Task status shown anywhere is a pure
  function of (store record, event journal) — no separate mutable status field
  that can disagree. Ambiguity (e.g. lease expired, no terminal event) renders
  as an explicit `stalled?` state rather than a guess.

### 5b. Non-functional requirements

- **NF-501 — Versioned journal format.** Envelope schema (`journal_v: 1`) is
  frozen-additive like the ABI. A 2029 reader parses a 2026 journal.
- **NF-502 — Zero-loss durability.** An event acknowledged into the journal
  survives process kill (fsync discipline); at most the tail event in flight
  is lost, never a torn line (a partial line is tolerated-and-skipped on read,
  with a warning).
- **NF-503 — Bounded overhead.** Journaling + sinks add < 5% wall-clock
  overhead to a tool-heavy task; sink dispatch is fire-and-forget with a
  bounded queue (drop + count for slow sinks; drops are themselves visible).
- **NF-504 — Grep-ability.** JSONL, one event per line, stable key order —
  every operator question answerable with grep/jq before any TUI exists.
- **NF-505 — Retention is explicit config, not magic.** Journals are kept
  forever by default; pruning happens only via an explicit
  `codeharness prune --older-than` command or a declared config policy.
  Nothing deletes silently.
- **NF-506 — No telemetry, ever.** No network egress from the visibility layer
  except through explicitly configured plugin sinks. Core phones home to
  nothing.

### 5c. User stories

- **US-501 (morning-after forensics).** As the owner reviewing an overnight
  failed task, I reconstruct the full story — prompts, tool calls, costs,
  checkpoints, the failure — from disk, with no processes running.
  *Acceptance:* with the daemon stopped, `codeharness log <task_id>` renders
  the human timeline; `jq` over the JSONL answers "which tool failed first";
  `codeharness cost` shows tokens/cost vs. budget; the `FAILED` event carries
  the worker's error string.
- **US-502 (budget accountability).** As an operator, I know before and during
  a run what it costs, and hard caps actually stop it.
  *Acceptance:* a task with `max_turns: 3` against the fake adapter emits
  exactly 3 `MODEL_REQUEST_STARTED` events then a budget-exhausted outcome
  (`STOPPED{reason:"budget"}`); with a real adapter + price table, reported
  cost matches Σ(usage × pinned prices) to the cent; `cost` output flags which
  cap bound.
- **US-503 (ship events to my dashboard without touching core).** As a power
  user, I write a 30-line sink plugin posting event envelopes to my own
  endpoint.
  *Acceptance:* a sink plugin registered per F-202/F-505 receives every
  envelope in seq order during a test task; a throwing sink (`onEvent` raises)
  mid-task neither loses journal events nor fails the task; drop counters are
  queryable.

### 5d. RICE + MoSCoW

| Req | R | I | C | E | RICE | MoSCoW |
|---|---|---|---|---|---|---|
| F-501 append-only journal | 5 | 5 | 5 | 2 | 62.5 | Must |
| F-502 boring human log | 5 | 4 | 5 | 1 | 100.0 | Must |
| F-503 cost accounting + usage plumbing | 5 | 5 | 4 | 2 | 50.0 | Must |
| F-504 audit trail | 4 | 5 | 4 | 2 | 40.0 | Must |
| F-505 event sink extension | 3 | 4 | 4 | 2 | 24.0 | Should |
| F-506 checkpoint visibility | 3 | 4 | 3 | 2 | 18.0 | Should |
| F-507 pure status derivation | 5 | 4 | 4 | 1 | 80.0 | Must |
| NF-501 versioned journal format | 5 | 5 | 5 | 1 | 125.0 | Must |
| NF-502 zero-loss durability | 5 | 5 | 4 | 2 | 50.0 | Must |
| NF-503 bounded overhead | 4 | 3 | 4 | 2 | 24.0 | Should |
| NF-504 grep-ability | 5 | 4 | 5 | 1 | 100.0 | Must |
| NF-505 explicit retention | 4 | 4 | 5 | 1 | 80.0 | Must |
| NF-506 no telemetry | 5 | 5 | 5 | 1 | 125.0 | Must |
| Metrics dashboards, OTel exporter | – | – | – | – | – | Could (plugin) |
| Full model-transcript capture in core | – | – | – | – | – | Won't (v1 — worker-layer concern; core sees events, not transcripts) |

### 5e. Open questions

- **Q-501:** Are the 11 ABI worker events *enough*? Candidate gaps:
  `TOOL_FINISHED` lacks duration/output-size; no worker heartbeat for stall
  detection; no `LEASE_*` events (those are core-side, so fine as journal-only
  events). If gaps are real, they must land as core-side journal events
  (allowed, additive) — never as `abi.ts` edits (forbidden). Must be settled
  explicitly.
- **Q-502:** One JSONL file per task vs. one global journal with per-task
  index? Per-task is simpler and prune-friendly; global gives cheap "what's
  happening now" ordering. Interacts with Q-102 (TUI feed).
- **Q-503:** Where do model *transcripts* (full messages) live for debugging —
  `worker-own` plugin artifacts referenced by `CHECKPOINT`, or nowhere by
  default? NF-301 requires prompt reconstruction; is a variables-hash +
  re-render sufficient, or must raw sent-bytes be stored (privacy/size
  tradeoff)?
- **Q-504:** Price table ownership — checked-in versioned file per release
  (byte-reproducible, goes stale) vs. user-maintained config? Who updates it
  under the "maintenance fork" rule?

---

## Cross-surface requirements (bind all five)

- **F-001 — One config file.** A single, versioned, schema-validated
  declarative config file (proposed `codeharness.json` or `.toml`;
  `config_v: 1`) is the *only* configuration mechanism: plugins incl.
  `worker-own` (F-204), template dirs (F-302), tool budgets/timeouts
  (F-404/NF-403), TUI prefs (NF-105), sinks (F-505), price-table path (F-503).
  Unknown keys are startup errors. `codeharness config check` validates;
  `codeharness config show --effective` prints the merged effective config
  with provenance per key. The only env var permitted is the existing
  `CODEHARNESS_STATE_FILE` (`store.ts` line 27) — and even that should be
  reviewed for demotion to a config key. RICE: 5×5×5/2 = **62.5** — **Must**.
- **NF-001 — Compatibility fixture suite.** Core CI carries frozen 2026
  fixtures — a worker plugin (the F-209 trivial fake), a tool plugin, a
  template pack, a journal file, a config file — and every release must
  load/execute all of them unmodified. This is the enforcement mechanism
  behind every "3-year" claim above (US-200, US-202, NF-401, NF-501).
  RICE: 5×5×4/2 = **50.0** — **Must**.

## Consolidated top priorities (by RICE among Musts)

1. **F-200 / F-204 / NF-202 / NF-206** — the coding agent is a plugin with no
   special core status, loaded declaratively, versioned independently; the
   stock install (core + `worker-own`) covers the 90% (owner directive; 62.5–125).
2. **NF-102 / NF-106** — TUI crash isolation + independent semver (125).
3. **F-404 / NF-403** — tool-output truncation + tool timeouts (125).
4. **F-301 / NF-501 / NF-506** — templates-are-files; versioned journal; no
   telemetry (125).
5. **F-001** — one config file, the anti-env-var-spaghetti keystone (62.5).

## Explicitly deferred this round (owner refinement)

- **Pi worker plugin** (vendored pinned `pi-ai`/`pi-agent-core` loop) — Won't
  (this round). Not designed here.
- **OpenSwarm worker plugin** (its orchestrator driving Codex/Claude CLI) —
  Won't (this round). Its atomic-store and TUI *patterns* are already vendored
  into `src/store.ts` and the TUI requirements; the worker itself is not built.
- The only live obligation toward both: **F-209** — Worker ABI v1 and the
  `worker_api` plugin slot stay neutral (proven by the trivial-second-worker
  CI fixture) so either can plug in later without any core change.

## Biggest open questions (block design freeze)

1. **Q-205/Q-201** — the exact `worker_api: "1"` shape (in-process driver
   interface vs. spawn/transport spec) and whether `worker-own` runs
   in-process or out-of-process in v1. This is now the single most
   consequential decision, since the agent-as-plugin directive routes
   everything through it.
2. **Q-401** — tool gateway in core vs. inside the worker plugin (decides
   what's frozen).
3. **Q-206** — do `loop.ts`/`adapter.ts` stay in `src/` as vendored reference
   code or move into `plugins/worker-own/`?
4. **Q-101/Q-102/Q-104** — TUI framework + event transport + command channel
   (is there a core daemon in v1 at all?).
5. **Q-501 / Q-405** — sufficiency of the 11 ABI events, and the
   permission-string vocabulary (de-facto ABI semantics).
