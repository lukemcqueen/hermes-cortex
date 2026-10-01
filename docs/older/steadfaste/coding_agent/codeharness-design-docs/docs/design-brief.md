# Design Brief — Codeharness TUI / Plugins / Templates / Tooling / Visibility

> This brief is read by the Fable model (Nous provider) subagents during the
> elicitation + architecture party. It is the single source of context. Read
> `../README.md` and `manus-openmanus-notes.md` first — they describe the
> existing frozen-core scaffold and the Pi / OpenSwarm / Manus research.

## North star (non-negotiable, in priority order)

1. **The core is extremely stable.** The frozen `Worker ABI v1` (`src/abi.ts`)
   never breaks for 3 years (2026–2029). The core defines reality; workers
   adapt to it. It must cover **90% of functionality** out of the box with no
   customization.
2. **Easy to customize.** The remaining 10% (and opinionated surfaces) are
   customized without touching the core — via plugins, templates, and config.
3. **Readable.** A new engineer (or the owner) can read every important line
   and understand it. No magic, no framework sprawl.
4. **Easily configurable.** Configuration is declarative, validated, and
   discoverable — never hidden in code, never env-var spaghetti.

## The five surfaces to design

For each surface, produce: (a) what it is, (b) the concrete shape (files,
interfaces, extension points), (c) what is IN the frozen core vs. what is a
plugin/peripheral, (d) the config surface, (e) the key risks and how the
"boring/stable" requirement constrains it.

### 1. TUI
A terminal UI to supervise the swarm (like OpenSwarm's Ink cockpit: tabs for
Chat / Pipeline / Logs / Monitor, `ContextBar` + `TabBar` + `HelpBar`, a
`PipelinePanel` subscribing to a daemon SSE stream rendering `StageTimeline` +
`SubagentTree` + `LiveLog`). Questions: what framework (Ink/React vs. Pi's
`pi-tui` vs. raw)? How does the TUI consume the core's event stream? What is
frozen vs. plugin-extensible (panels, themes, keybindings)? How does it stay
"readable" and not become a 100-component app?

### 2. Plugins
The extension mechanism for the 10%. Questions: what is the plugin boundary
(Pi's extension model, MCP servers, npm-installable packages, or our own)?
What can a plugin do (add tools, add TUI panels, add providers, add templates)?
Versioning + compatibility contract (a plugin written in 2026 works in 2029)?
How do plugins get loaded, validated, sandboxed, and disabled cleanly?

### 3. Template (templating)
The "boring" defaults for tasks, prompts, workflows, and scaffolded projects.
Questions: how are prompts/task-templates versioned and owned (Pi's prompt
templates + OpenManus's `planning` prompt)? How does a user override a
template without forking the core? How do templates compose (base + patch)?
How does the core's prompt-template surface stay frozen while templates evolve?

### 4. Tooling
The tool gateway + the tool contract. Questions: the frozen tool interface
(Pi's `AgentTool`: schema validation, `prepareArguments`, `execute`, `replay`
policy, `executionMode`)? How are tools added/removed at runtime (OpenManus's
MCP boundary)? How do we keep tool output bounded (`max_observe` truncation)?
What is the standard toolset that covers 90% (shell, file edit, search, git,
test-run)?

### 5. Visibility (observability)
How the operator sees what's happening. Questions: the event stream contract
(the 11 worker events already in `abi.ts` — are they enough)? Structured logs,
audit trail, cost accounting, checkpoint/replay. What is the minimum visibility
for "boring" (OpenSwarm's "12:00 task leased / 12:04 checkpoint / 12:07 tests
passed / 12:08 complete" log shape)? What's frozen vs. what's a plugin (metrics
sinks, dashboards)?

## Constraints that shape every answer

- **No auto-updates, pinned versions.** Workers are immutable images. The
  running agent cannot mutate its own runtime.
- **Semver per component.** `core 1.x` never breaks. Workers/plugins version
  independently.
- **Reproduce to the byte.** Lockfiles + container digests + pinned runtime.
- **Maintenance fork, not innovation fork.** Security patches only by default.
- **Provider-agnostic core.** The core never knows what a "Pi session" or a
  "Claude conversation" is — only `task_id`, `attempt_id`, `worker_id`,
  `workspace_id`, `checkpoint_id`, `lease_id`.
- **The plan is the context** (Manus): decompose into a structured tracked plan,
  dispatch narrow slices, truncate tool output, detect duplicate turns.

## Existing scaffold (already built, tests green)

```
~/codeharness/
  README.md
  docs/manus-openmanus-notes.md
  src/abi.ts        # Worker ABI v1 — the frozen vocabulary
  src/loop.ts       # agent loop (Pi-derived, simplified)
  src/store.ts      # atomic durable task store (OpenSwarm-derived)
  src/adapter.ts    # LLM adapter interface + FakeAdapter
  test/loop.test.ts # 3 passing bun tests
```

Language is TypeScript (Node 22 + Bun 1.3 installed). The core's loop, store,
adapter, and ABI are the only things that exist today. Everything in this brief
is DESIGN to be produced — nothing is built yet.
