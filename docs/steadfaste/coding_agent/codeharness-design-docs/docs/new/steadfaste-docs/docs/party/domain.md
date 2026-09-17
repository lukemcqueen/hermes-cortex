# Domain Expert / Developer-Experience — Customization, Readability, Configurability

> Role: DOMAIN EXPERT / DX in the architecture party. Lens: the owner's goals —
> "easy to customize", "readable", "easily configurable", "core extremely
> stable + accommodates 90%". Anti-goals: auto-updates, unpinned versions,
> framework sprawl, env-var spaghetti, magic, hidden config.
>
> Design principle used throughout: **boring, explicit, versioned extension
> points**. Every extension surface is (a) a plain TypeScript interface a human
> can read in one screen, (b) declared in a manifest file, never discovered by
> magic, (c) versioned with a declared compatibility range, (d) disabled by
> deleting one line of config.
>
> **Owner's hard requirement (incorporated):** the coding agent itself is a
> PLUGIN — no special status. There is **one plugin kind with many
> capabilities**; "worker" (implements the agent loop against Worker ABI v1)
> is just one more capability, alongside tools, TUI panels, providers, and
> templates. We build ONLY our own coding-agent worker plugin first; Pi and
> OpenSwarm workers are deferred (§1.7) — the ABI stays neutral so they can
> plug in later without a core change.

---

## 0. The DX contract in one sentence

**A user who wants the default experience touches zero files; a user who wants
to customize touches exactly one file per kind of customization, and can find
that file by running `codeharness config where <knob>`.**

The five surfaces map to that contract like this:

| Surface | Frozen (core 1.x, never breaks) | Customizable (plugin/template/config) |
|---|---|---|
| TUI | Event stream contract, panel host, keybinding dispatcher | Panels, themes, keybindings, layout |
| Plugins | `PluginManifest` + `PluginApi v1` interfaces, loader, sandbox policy, Worker ABI v1 | Everything a plugin ships — including the coding agent itself (a `worker` plugin) |
| Template | Template resolution algorithm, `template.json` schema, patch semantics | Every template body |
| Tooling | `Tool` interface (Pi-shaped), gateway, `max_observe` truncation | Tools themselves (builtin set + plugin tools + MCP) |
| Visibility | The 11 worker events, JSONL audit log, cost ledger schema | Sinks, dashboards, extra metrics |

---

## 1. The Plugin API (the exact interface a user writes against)

### 1.1 Design stance

- **Plugins are local, pinned, in-process npm-style packages** — a directory
  under `~/.codeharness/plugins/<name>@<version>/` (or vendored in-repo under
  `plugins/`). No registry auto-install, no auto-update, no remote loading.
  Installing a plugin = copying a directory + adding one line to config.
  This matches "reproduce to the byte": plugins live in the lockfile-world,
  not a runtime marketplace.
- **MCP is the *runtime tool* boundary; plugins are the *harness* boundary.**
  An MCP server adds tools to a worker at runtime (already the OpenManus
  pattern) and needs no plugin API at all. A plugin extends the harness
  itself: TUI panels, templates, providers, event sinks, **workers (coding
  agents)**, and tools that need in-process access. Don't conflate the two.
- **One plugin kind, many capabilities — including the coding agent.** There
  is no "worker framework" separate from the plugin system. A plugin that
  declares the `worker` capability registers a `WorkerFactory` that speaks
  Worker ABI v1; that is the coding agent. A cost dashboard and the coding
  agent are the same species of artifact — same manifest, same lifecycle,
  same versioning, same disable path. The core ships with **zero built-in
  workers**; even our own coding agent lives in `plugins/worker-own/`.
- **The plugin talks to a versioned `PluginApi` object, never to core
  internals.** No imports from `src/` (the frozen core: `abi.ts`, `loop.ts`,
  `store.ts`, `adapter.ts`). The host hands the plugin a capability object;
  everything the plugin can do is a method on it. This is what makes
  2026→2029 compatibility possible: we freeze one interface, not a module tree.

### 1.2 The manifest (declared, not discovered)

Every plugin ships `plugin.json` — TypeBox-validated, `additionalProperties:
false`, same discipline as Pi's `protocol.ts`:

```jsonc
{
  "manifest_version": 1,
  "name": "cost-dashboard",
  "version": "1.2.0",                     // plugin's own semver
  "api": { "min": "1.0", "max": "1.x" },  // PluginApi range it was written for
  "entry": "dist/index.js",               // one prebuilt file; no build step at load
  "capabilities": ["tui.panel", "events.subscribe"],  // declared, enforced
  "config_schema": "config.schema.json",  // TypeBox JSON schema for this plugin's knobs
  "permissions": { "fs": [], "net": [], "exec": false } // sandbox declaration
}
```

Rules the loader enforces:
- **Capabilities are an allowlist.** A plugin that declared only `tui.panel`
  cannot register a tool — the capability object handed to it is constructed
  per-plugin from the declared list; the method simply isn't there.
- **`entry` is prebuilt JS.** No compile-on-load, no `ts-node` magic, no
  postinstall scripts. Same supply-chain rule as the core.

### 1.3 The interface (`PluginApi v1` — frozen, ~one screen)

```ts
// plugin-api.ts — versioned exactly like abi.ts. This is the WHOLE surface.
export const PLUGIN_API_VERSION = "1.0";

export interface Plugin {
  /** Called once after validation. Register everything here. Must not do I/O
   *  beyond reading its own config. Throwing here = plugin disabled, core fine. */
  activate(api: PluginApi): void | Promise<void>;
  /** Called on disable/shutdown. The host also auto-unregisters everything the
   *  plugin registered, so this is for the plugin's OWN resources only. */
  deactivate?(): void | Promise<void>;
}

export interface PluginApi {
  readonly apiVersion: "1.0";
  readonly pluginName: string;
  /** This plugin's validated config (per its config_schema). Read-only. */
  readonly config: Readonly<Record<string, unknown>>;
  readonly log: (level: "info" | "warn" | "error", msg: string, data?: object) => void;

  // Capability-gated sections — present only if declared in the manifest.
  tools?: {
    register(tool: Tool): Disposable;            // the frozen Pi-shaped Tool contract
  };
  templates?: {
    register(t: TemplateSource): Disposable;      // contributes template layers (§2)
  };
  events?: {
    subscribe(filter: EventFilter, fn: (e: WorkerEvent) => void): Disposable;  // read-only
  };
  tui?: {
    registerPanel(p: PanelSpec): Disposable;      // id, title, render(props) → Ink element
    registerKeybinding(k: KeySpec): Disposable;   // declarative; conflicts rejected at load
    registerTheme(t: ThemeSpec): Disposable;
  };
  providers?: {
    register(a: LLMAdapter): Disposable;          // the frozen adapter.ts interface
  };
  workers?: {
    /** Register a coding-agent implementation. The factory speaks Worker ABI v1
     *  (abi.ts) — Task in, WorkerEvents out, operations in — and NOTHING else.
     *  The core schedules/leases/supervises; the plugin only runs the loop. */
    register(w: WorkerFactory): Disposable;
  };
}

// The worker capability's one contract — a thin wrapper around the frozen ABI.
export interface WorkerFactory {
  readonly workerType: string;                    // e.g. "own" — referenced by model_policy/config
  /** Called once per attempt. Everything the worker knows arrives in `task`
   *  (frozen Task type); everything it says leaves through `emit` (the 11
   *  frozen WorkerEvents). Returns a handle for core → worker operations. */
  start(task: Task, ctx: WorkerContext): WorkerHandle;
}

export interface WorkerContext {
  readonly emit: (e: WorkerEvent) => void;        // WORKER_STARTED … RESULT/FAILED/STOPPED
  readonly tools: ToolGateway;                    // core-owned: permissions + max_observe enforced
  readonly adapter: LLMAdapter;                   // resolved per task.model_policy
  readonly workspace: string;                     // isolated dir; only writable scope
  readonly log: PluginApi["log"];
}

export interface WorkerHandle {                   // core → worker operations (ABI v1 verbs)
  send(msg: string): void;
  checkpoint(): Promise<string>;                  // returns checkpoint_id
  cancel(): Promise<void>;
  kill(): void;
}
```

Notes on shape:
- **Everything returns `Disposable`.** The host tracks every registration by
  plugin name; disabling a plugin = dispose all its registrations. Clean
  disable falls out of the API shape instead of being a cleanup protocol
  plugins must implement correctly.
- **Events are read-only for observers.** The `events` capability observes the
  stream; it never injects. The ONLY way events enter the stream is a worker
  plugin's `ctx.emit`, which the core stamps (task_id, attempt_id, worker_id,
  timestamps) and validates against the frozen event schemas before it touches
  the audit log — a worker can only tell its own story, never rewrite others'.
- **No hooks into the agent loop in v1.** Pi's `beforeToolCall` /
  `afterToolCall` stay core-internal. If a real use case appears, add a
  capability in a *minor* PluginApi bump — additive, old plugins unaffected.

### 1.4 Lifecycle: load → validate → sandbox → run → disable

1. **Discover**: read the `plugins` list from config (§3). Only listed plugins
   load, in listed order. Nothing on disk loads implicitly. One obvious place
   to see what's active; deterministic order = deterministic tool/keybinding
   registration.
2. **Validate**: manifest against schema; `api` range against
   `PLUGIN_API_VERSION`; plugin config against the plugin's `config_schema`;
   declared capabilities against the host's known list. Any failure → plugin
   **skipped with a visible one-line reason** in the TUI Logs tab and in
   `codeharness plugins list`. A broken plugin never takes the harness down.
3. **Sandbox**: two tiers, both boring.
   - *Tier 1 (default, in-process)*: capability-object gating (can't call what
     it wasn't handed) + declared `permissions` checked by the tool gateway
     when the plugin's tools execute (fs paths, net allowlist, exec flag).
     Honest framing: in-process JS is not a security boundary against a
     malicious plugin — it's a **mistake boundary**. The trust model is
     "plugins are code you chose to install and pin", same as any dependency.
   - *Tier 2 (opt-in, `"isolate": true` in the manifest)*: run in a child
     process speaking a tiny JSON-RPC mirror of `PluginApi` — for untrusted or
     crashy plugins. Same interface, so promoting a plugin to tier 2 changes
     nothing in its code. Tier 2 exists so the answer to "can I run this
     sketchy plugin?" is yes-with-isolation rather than a redesign.
4. **Run**: `activate(api)`. A plugin that throws during activation is
   disabled and reported; registrations made before the throw are disposed.
5. **Disable**: remove it from the config list (or `codeharness plugins
   disable X`, which edits the same config file — one source of truth). Host
   calls `deactivate()`, disposes all registrations, drops the capability
   object. "Restart to fully unload" is an acceptable and *documented*
   limitation for tier-1 plugins (V8 can't unload modules) — say so instead of
   pretending.

### 1.5 Versioning: why a 2026 plugin runs in 2029

- `PLUGIN_API_VERSION` follows the ABI discipline: **1.x is additive-only**.
  New capabilities appear as new optional sections on `PluginApi`; existing
  method signatures never change; removed features are stubbed to no-op + a
  deprecation log line for the full major cycle, never deleted in 1.x.
- The manifest's `api: {min, max}` range is checked at load, so incompatibility
  is a clear load-time message ("needs api 2.x, host has 1.4"), never a
  runtime explosion three tool calls in.
- The plugin's *data contracts* (`Tool`, `WorkerEvent`, `LLMAdapter`,
  `TemplateSource`) are the already-frozen core types. Freezing the ABI freezes
  most of the plugin surface for free — PluginApi is a thin capability wrapper
  around types already promised stable for three years.
- If PluginApi 2.0 ever ships, the host loads **both**: v1 plugins get a v1
  capability object, v2 plugins get v2. Two small compatibility shims beat a
  migration mandate. (Pi's `PROTOCOL_VERSION` handshake pattern, applied to
  plugins.)
- **Worker plugins get a second, even stronger promise**: the `WorkerFactory`
  wrapper is one screen of glue around **Worker ABI v1** (`abi.ts`), which is
  frozen for 2026–2029 by the project's north star. A worker plugin's real
  contract is Task-in / eleven-events-out / six-operations-in. A worker
  written in 2026 runs against the 2029 core because the ABI never learned
  anything new to break it with.

### 1.6 Authoring OUR OWN coding-agent worker plugin (the first worker)

The first — and initially only — worker is ours: `plugins/worker-own/`. It is
deliberately the existence proof that the plugin API is sufficient: if our own
agent needs a private backdoor into the core, the API has failed the owner's
requirement.

```
plugins/worker-own/
  plugin.json          # capabilities: ["worker"], api 1.x, version 1.0.0
  dist/index.js        # prebuilt entry
  src/
    index.ts           # activate(api) { api.workers!.register(ownWorker) }
    loop.ts            # THE agent loop — vendored from core scaffold's src/loop.ts
    plan.ts            # Manus-style plan-as-context (structured tracked plan)
    hygiene.ts         # max_observe truncation, duplicate-turn detection,
                       # token-limit → graceful FAILED (never a crash)
```

What the author writes, step by step:

1. `plugin.json` with `capabilities: ["worker"]` — same manifest as any plugin.
2. `activate(api)` calls `api.workers.register({ workerType: "own", start })`.
3. `start(task, ctx)` runs the loop: stream `ctx.adapter` response → extract
   tool calls → `ctx.tools.execute(...)` (gateway enforces permissions +
   `max_observe`; the worker cannot bypass it) → append results → repeat,
   emitting `MODEL_REQUEST_*`, `TOOL_*`, `PROGRESS`, `CHECKPOINT` along the
   way, ending in exactly one of `RESULT` / `FAILED` / `STOPPED`.
4. Budget (`task.budget.max_turns` etc.) is checked by the worker AND enforced
   by the core — belt and suspenders; the core kills what the worker won't stop.
5. All Manus-style worker-layer discipline (plan-as-context, stuck detection,
   truncation) lives HERE, in the plugin — exactly as the README's design test
   demands: the core never learns what a plan or a session is.

DX consequence worth stating plainly: **the core scaffold's `loop.ts` moves
into (or is vendored by) `worker-own`** — the frozen core keeps the state
machine, store, leases, gateway, and ABI; the loop is a worker concern. A new
coding-agent author copies `worker-own`, replaces `loop.ts`'s strategy, keeps
the manifest shape, and never reads core source. Selecting a worker is config:
`"models": { ... }` plus the task's `model_policy` / a `"worker": "own"`
default knob — one line, one place.

### 1.7 Deferred: Pi and OpenSwarm worker plugins (design later, not now)

NOT designed in detail now, by owner direction. What we keep today is only the
neutrality guarantee: a future `worker-pi` (vendored pi-ai/pi-agent-core) or
`worker-openswarm` plugin is *just another directory with
`capabilities: ["worker"]`* — same manifest, same `WorkerFactory`, same
lifecycle. Because Worker ABI v1 speaks only `task_id` / `attempt_id` /
`worker_id` / `workspace_id` / `checkpoint_id` / `lease_id` and never "Pi
session" or "Claude conversation", adding them in 2027 requires **zero core
changes and zero PluginApi changes** — that is the whole test, and `worker-own`
proves the socket works before anything foreign plugs into it.

---

## 2. The Template System (versioned, owned, base + patch, no forking)

### 2.1 What is a template

Everything prose-or-scaffold the harness feeds to models or writes to disk:
system prompts, planner prompts (the Manus `CURRENT PLAN STATUS` shape), task
templates, verification-command presets, project scaffolds. Templates are
**data, not code**: plain files + a small manifest. No executable templates —
that's where magic and supply-chain risk creep in.

### 2.2 Layout and ownership

```
core layer (read-only, ships with the harness, versioned WITH the core):
  templates/
    prompts/system.md
    prompts/planner.md            # the plan-as-context prompt
    tasks/fix-bug.json
    tasks/add-feature.json
    scaffold/ts-service/...
    template.json                 # manifest: id, version, vars, description

user layer (owned by the user, wins over core):
  ~/.codeharness/templates/**     # same tree shape

project layer (owned by the repo, wins over user):
  <repo>/.codeharness/templates/**

plugin layer (contributed via api.templates.register — lowest override layer)
```

**Resolution order (frozen algorithm, one sentence a user can memorize):**
project → user → plugin → core; first hit wins for replacement, and patches
stack in the same order. `codeharness template which prompts/system.md` prints
the winning file and every layer that contributed — discoverability is a
command, not tribal knowledge.

### 2.3 Composition: replace or patch, nothing cleverer

Two override modes, chosen by filename:

1. **Replace**: put `prompts/system.md` in a higher layer → it fully shadows
   the core file. Simple, obvious, the right tool for a genuinely different
   prompt.
2. **Patch**: put `prompts/system.patch.md` in a higher layer. A patch file is
   sectioned by explicit anchors that core templates declare:

   ```md
   <!-- @append: guidelines -->
   - Always run `bun test` before declaring done.
   <!-- @replace: tone -->
   Terse. No filler.
   ```

   Core templates mark anchor points (`<!-- @anchor: guidelines -->`). Patches
   may `@append`, `@prepend`, or `@replace` a named anchor. **No regex, no
   line-number diffs, no template inheritance trees.** Anchors are a public,
   versioned contract: renaming or removing an anchor in a core template is a
   breaking change and gets the same semver discipline as the ABI.

   Why patches matter: replacement alone forces users to fork the whole prompt
   to add one sentence — and then silently miss every core prompt improvement
   (edge case §5.2). Anchored patches let the 90% case ("add my two house
   rules") compose with core evolution.

3. **Variables, not logic.** Templates use `{{task.objective}}`-style
   substitution from a fixed, documented variable set derived from the frozen
   `Task` type. No conditionals, no loops, no user functions in templates. If
   you need logic, write a plugin that registers a `TemplateSource` — logic
   lives in reviewed code; templates stay readable.

### 2.4 Versioning and drift detection

- Each layer's `template.json` carries `version` and, for overrides,
  `overrides: {"prompts/system.md": {"core_version": "1.3"}}` — the core
  template version the override was written against.
- On startup (and via `codeharness template doctor`), if the core template has
  moved past the recorded `core_version`, print one line: *"your override of
  prompts/system.md was written against core 1.3; core is now 1.5 — run
  `template diff` to review."* Never auto-merge, never block. The user stays
  informed and in control; silent staleness is the failure mode we're buying
  out of.
- Rendered prompts are content-hashed into the audit log per attempt, so
  visibility can always answer "exactly which prompt did this task run with?"

---

## 3. The Config System (declarative, validated, one place per knob)

### 3.1 One file, one schema, layered like templates

```
Precedence (highest wins) — the COMPLETE list of config inputs:
  1. CLI flags                          (this invocation only)
  2. <repo>/.codeharness/config.json    (project)
  3. ~/.codeharness/config.json         (user)
  4. built-in defaults                  (in code, exported as one plain object)
```

- **JSONC** (JSON + comments): declarative, diffable, no YAML whitespace
  traps; comments allowed because config files deserve them.
- **One TypeBox schema for the whole config**, `additionalProperties: false`
  at every level. An unknown key is a *load error with a suggestion* ("did you
  mean `tui.theme`?"), never a silently ignored typo. This one rule kills the
  most common config bug in existence.
- **Env vars: exactly two, both boring**: `CODEHARNESS_CONFIG` (path override,
  for tests/CI) and `CODEHARNESS_HOME` (state-dir override). **No knob is
  env-var-settable.** Secrets are not env-spaghetti either: config references
  them by name (`"api_key_ref": "keychain:anthropic"` or `"file:~/.keys/x"`)
  and a tiny resolver reads them at use time. Secrets never live in config
  files, and config never lives in env vars.

### 3.2 The shape (top level ≈ the five surfaces + core)

```jsonc
{
  "config_version": 1,
  "core":    { "store_dir": "~/.codeharness/state",
               "budget_defaults": { "max_turns": 40, "max_cost_usd": 5 } },
  "models":  { "default": { "provider": "anthropic", "model": "claude-sonnet-4-5" },
               "worker": "own" },   // which registered worker plugin runs tasks
  "tooling": { "max_observe": 8000, "mcp_servers": {},
               "permissions_default": "workspace-only" },
  "tui":     { "theme": "default", "keybindings": {},
               "panels": ["chat", "pipeline", "logs", "monitor"] },
  "templates": { "extra_dirs": [] },
  "plugins": [
    { "name": "worker-own", "version": "1.0.0" },   // the coding agent — just a plugin
    { "name": "cost-dashboard", "version": "1.2.0", "config": { "currency": "USD" } }
  ],
  "visibility": { "audit_dir": "~/.codeharness/audit", "sinks": [] }
}
```

Per-plugin config lives **inside the plugin's entry in the plugins list**,
validated against that plugin's own `config_schema`. One knob, one home:
"where do I configure plugin X?" has exactly one answer.

### 3.3 Discoverability is tooling, not documentation

- `codeharness config show` — the full **effective** config, defaults
  included, each value annotated with its source (`default | user | project |
  flag`). A forgotten project-level override cannot hide.
- `codeharness config where tui.theme` — which file/line sets it, or "unset;
  default = 'default' (defined in config-schema.ts)".
- `codeharness config check` — validate all layers without running anything.
- `codeharness config init` — writes a config file where **every line is a
  commented-out default with its schema description as the comment**. The
  defaults file *is* the documentation, generated from the schema — a single
  source of truth.
- Validation errors are precise: file, JSON path, expected type, actual value,
  and the schema description of the knob. A config error must never require
  reading source code.

### 3.4 Config versioning

`config_version: 1` at the top. Core 1.x never changes the meaning of an
existing key; new keys ship with defaults so old files stay valid. If a rename
is ever unavoidable, the old key keeps working with a deprecation notice for
the entire 1.x line — the same additive discipline as the ABI and PluginApi.

---

## 4. "90% covered by boring defaults" — what a user should NOT configure

The out-of-box promise: **clone, set one API-key reference, run.** Zero-config
must be a great experience, not a degraded one. Things a user never touches
because the default is opinionated and correct:

- **Where state lives** (`~/.codeharness/state`) and the atomic-store
  behavior — fsync/lock/lease semantics are not configurable *at all* beyond
  the directory. No "performance mode" that trades away crash safety.
- **The standard toolset** — shell, read/write/edit file, search, git,
  test-run — present, workspace-scoped, tuned. Adding tools is easy (MCP entry
  or plugin); the base set needs no assembly.
- **Context hygiene** — `max_observe` truncation, duplicate-turn detection,
  token-limit→graceful-terminal, plan-as-context slicing. Correctness
  features: on by default, sane thresholds, only the numeric budgets are knobs.
- **Safety rails** — budget defaults, workspace-only write scope,
  lifecycle-script blocking. Loosening is explicit per-task (`permissions` on
  the Task), never a global "yolo mode" config bit.
- **The TUI** — four tabs, default theme, default keybindings, event wiring.
  Fully usable with an empty config.
- **Visibility** — JSONL audit log and cost ledger always on, **not
  disableable**. The OpenSwarm-style human log line ("12:04 checkpoint ·
  12:07 tests passed") is the default rendering.
- **Retry/recovery, lease timeouts, checkpoint cadence** — internals with
  tested defaults. Exposing them invites cargo-cult tuning and turns every bug
  report into "what are your 14 timeout settings?"

**Litmus test for adding any knob**: (1) two real users genuinely need
different values; (2) the default is right for ≥90%; (3) it fits an existing
config section; (4) we can write one sentence saying when to change it. Fail
any → no knob. Every knob is a permanent support surface and a bite out of
"reproduce to the byte".

---

## 5. The three sharpest edge cases customization systems get wrong

### 5.1 The plugin that breaks the core it extends (fault non-isolation)

The classic failure: one plugin throws in a render function or event handler
and the whole TUI/harness dies — users learn to fear plugins, and the 10%
surface poisons the 90%. Design answer: every plugin callback (panel render,
event subscriber, tool execute) runs inside a host-owned try/catch **at the
boundary**; a throwing plugin gets its panel replaced by an inline error box
and, after N faults, is auto-disabled for the session with a visible notice —
never a crash, never silent. Corollary: plugins can't inject events or mutate
the store, so a buggy plugin can degrade *its own* surface but cannot corrupt
task state or the audit trail. Worker plugins are the special case that proves
the rule: a crashing/hanging worker becomes a `FAILED`/`STOPPED` *task state*
(lease expiry + core-enforced budget + kill), never a harness crash — the core
supervises workers precisely because they are plugins, not trusted internals.
The frozen core's blast radius from any plugin must be zero.

### 5.2 The silent stale override (fork-and-forget)

A user copies `prompts/system.md` in 2026 to change one sentence. Core
templates improve for three years; the user unknowingly runs the 2026 prompt
the whole time and files bugs against behavior the core fixed long ago.
Nothing errors — quality just decays. This is the *quiet* killer. Design
answer: (a) anchored patches so the common case ("add two lines") never
requires a full copy; (b) `core_version` recorded on every override + startup
drift notice + `template diff`; (c) the audit log hashes the rendered prompt
so any bug report reveals exactly which template mix ran. The same pattern
covers config: `config show` always displays effective values with sources.

### 5.3 The load-time compatibility lie (version check ≠ contract check)

A 2026 plugin declares `api: 1.x`, loads cleanly in 2029… and misbehaves at
runtime because a *behavioral* contract shifted — an event now fires in a
different order, a never-null field became optional, tool results grew a
truncation footer. Version ranges only protect what the type system sees.
Design answer: (a) additive-only means **don't change observable behavior**,
not just "don't change signatures" — event ordering, nullability, defaults,
and error shapes are part of ABI v1 and get a pinned regression suite
(`plugin-api-compat.test.ts`, run on every core change — the plugin analog of
Pi's protocol tests); (b) anything genuinely new arrives as a *new*
event/field/capability, never a changed old one; (c) `additionalProperties:
false` on what plugins *send us*, but plugins must tolerate *extra* fields on
what they receive — the plugin template ships a lint rule and doc note saying
so. The compatibility promise is behavioral, or it is a lie.

---

## 6. Surface-by-surface summary (party cross-reference)

- **TUI**: Ink/React (matches the OpenSwarm heritage; ecosystem-boring).
  Frozen: panel host, event-stream client, keybinding dispatcher, the four
  default tabs. Extensible: additional panels/themes/keybindings via
  `api.tui.*`. Readability rule: the core TUI stays under ~15 components;
  anything fancier is a plugin.
- **Plugins**: §1. Local, pinned, manifest-declared, capability-gated,
  Disposable-based teardown, additive-only PluginApi v1. One plugin kind, many
  capabilities — the coding agent is a `worker` plugin (`worker-own`, §1.6),
  no special status; Pi/OpenSwarm workers deferred (§1.7).
- **Templates**: §2. Data-not-code, four layers, replace-or-anchored-patch,
  version-drift detection, rendered-prompt hashing.
- **Tooling**: the frozen `Tool` contract (Pi's shape: TypeBox schema,
  `prepareArguments`, `execute`, replay policy, `executionMode`) is the *same
  type* plugins register and MCP servers are adapted into — one tool contract,
  three sources (builtin / plugin / MCP), one gateway enforcing permissions
  and `max_observe`.
- **Visibility**: the 11 ABI events are the frozen contract; audit JSONL +
  cost ledger always on; plugins subscribe read-only and add sinks/dashboards.
  Nothing a plugin does can make the audit trail less true.
