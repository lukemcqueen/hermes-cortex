---
version: 1.0.0
name: pi-coding-agent
description: "Operate the Pi coding agent CLI — install, extensions, Jev."
---

# Pi Coding Agent

The coding-agent harness the fleet owner wants for steadfaste (replacing hermes).
`@earendil-works/pi-coding-agent`, installed via npm. The reference for pi + Jev
integration is `github.com/disler/ten-levels-of-jev` (30 tested Jev use cases in
10 levels; levels 6–10 put Jev inside pi).

## Install
- `npm install -g @earendil-works/pi-coding-agent`
- Requires Node `>=22.19.0` — **NOT Node 24**. (Node 24 is only the ten-levels
  repo's own TypeScript requirement, not pi's. Check `npm view
  @earendil-works/pi-coding-agent engines` before assuming a Node bump is needed.)
- Verify: `pi --version` and `pi --help` (the help lists read/bash/edit/write tools
  and the `pi install/remove/list/config/auth` extension commands).

## Core
- Built-in tools: read, bash, edit, write.
- `pi install <source>` / `pi remove <source>` manage extension sources;
  `pi list` shows installed extensions.
- An extension is loaded as `pi -e extensions/<name>.ts --tools read,bash,edit,write[,<jev tools>]`
  — the `--tools` allowlist is explicit; only listed tools are available.

## Extension API (the Jev-hook surface)

**Read the installed type defs before writing a hook — never infer the signature.**
```bash
P=$(npm root -g)/@earendil-works/pi-coding-agent
sed -n '1,60p' "$P"/dist/core/extensions/types.d.ts   # + grep the event interfaces
```

- **Hooks** — `pi.on("tool_call" | "tool_result" | "turn_end" | "before_agent_start" | "session_before_compact", fn)`. A `tool_call` hook can `return { block: true, reason }` to stop a tool call before it runs; the agent sees only the reason + a notice that the block is final.
- **The handler's FIRST parameter is the EVENT, not a ctx**: `ExtensionHandler<E> = (event: E, ctx: ExtensionContext) => R`. Reading `ctx.<thing>` off that first parameter yields `undefined`.
- **Injection is the RETURN VALUE.** `before_agent_start` returns `BeforeAgentStartEventResult` (`{ message?, systemPrompt? }`); there is **no `ctx.addSystemPrompt()`**. To add context, return an augmented `systemPrompt` (or a `message`).
- **Event payloads carry the data**: `turn_end` → `{ turnIndex, message, toolResults, entries, outcome }`; `before_agent_start` → `{ prompt, images, systemPrompt, systemPromptOptions }`. Derive what you need from the event.
- **Tools** — `pi.registerTool({ name, label, description, parameters, run })`. Tool descriptions carry the question schema.
- **Verify a hook fires AND does its job** — a stderr marker in the handler proves the hook ran, not that the effect landed. Assert the effect (did the injected text appear? did the row have content?).
- **Compaction** — `.pi/settings.json` sets `compaction.keepRecentTokens` low so compaction has material; `ctx.compact()` wraps pi's compaction; `ctx.getContextUsage()` feeds the numbers.
- **Side channel** — report every decision on stderr as `JEV_EVENT` lines (and as session entries) so a run is auditable line-by-line (tool call, hook decision, Jev call, model, cost, context).

## Cortex context (memory + session)

**Pi >= 0.99 / 1.0 has an MCP client** (pi 1.0.0; one run recorded, independent reproduction pending): it reads
`mcpServers` from `~/.pi/agent/mcp.json` (user scope) and `.pi/mcp.json` (trusted
projects only), the same shape as Claude Code. Governance is therefore an MCP
registration — never hand-write a lock:

```bash
bash ~/hermes-cortex/ops/scripts/install/install-pi-mcp.sh   # loop-governance, tasks, executor, agent-bus
pi mcp list                                                 # expect 4 servers, state "connected"
```

The **memory/session** tools stay on the extension (a CLI shim), because the
extension also owns the lifecycle triggers MCP cannot provide:

```bash
cp ~/hermes-cortex/ops/install/harnesses/pi/extensions/cortex-context.ts extensions/
pi -e extensions/cortex-context.ts --tools read,bash,edit,write,mem_context,session_restore,session_checkpoint,session_close
```

An older Pi (<= 0.87, no MCP client) reaches the same governance through the
`loop-gov` CLI instead.

The extension registers `mem_*` / `session_*` tools AND wires the lifecycle:

- `before_agent_start` → restore + inject the checkpoint (a fresh session resumes)
- **`turn_end` → write a checkpoint** — the harness owns WHEN, never the model
- `session_before_compact` → checkpoint before continuity is lost
- **`tool_result` → record the tool event** for tools a gate asks about. The git hook
  is GLOBAL, so a Pi commit is gated by the same reflexion gate as a Hermes one, and
  that gate reads HC's store — not the harness's own DB. With no `tool_result` hook a
  Pi session has no recorded evidence and **every commit is refused** no matter how
  well the agent behaved.

Register every shared tool the harness must reach in the extension's `tool()` list.
A tool that exists on the store contract but not in the harness is unreachable to the
agent, and this hand-written list drifts as `context_tools.TOOLS` grows.

Harness index: `ops/install/harnesses/INDEX.md` · Adding another harness:
`registry.yaml` + `generate-harnesses.py` · Runbook:
`docs/runbooks/context-integration.md`.

## Configure a provider (OpenRouter + a model)

Verified against the installed package docs — `docs/providers.md`,
`docs/settings.md`, `docs/configuration.md` — not inferred:

```bash
# <agent-dir>/auth.json   — {"<provider>": {"type": "api_key", "key": "... | !command"}}
# <agent-dir>/settings.json — {"defaultProvider": ..., "defaultModel": ...}
# <agent-dir>/models.json — custom/compatible models and overrides
```

Set the model defaults (preserve existing keys — `extensions`, `skills`):

```json
{"defaultProvider": "openrouter", "defaultModel": "moonshotai/kimi-k2.6"}
```

**Do NOT source an env file to supply the key.** Pi's docs support a `!command`
precisely so the resolved key is never written to disk, but the obvious command —
`bash -lc 'set -a; . ~/.hermes/.env; printf %s $OPENROUTER_API_KEY'` — hands the
coding agent EVERY secret in that file, and this skill's own pitfall says the agent
can print its own environment. Supply exactly one variable:

```json
{"openrouter": {"type": "api_key",
                "key": "!bash ~/.hermes-cortex/scripts/env-secret.sh OPENROUTER_API_KEY"}}
```

`env-secret.sh` prints one named value (cortex env first, then the Hermes env, first
match wins), fails closed when absent, and refuses a name that isn't
`^[A-Z][A-Z0-9_]*$` so it can't become a pattern. Point it at a Hermes-only key and
copy that key into the cortex env: no harness should reach into a Hermes-owned file
for a provider key.

Verify all three, in this order — the last one is the only real proof:

```bash
pi auth check --provider openrouter          # ready
pi --list-models kimi                        # the model, with context/thinking capabilities
pi --model "openrouter/<vendor>/<model>" "Reply with exactly: ready"   # a real turn
```

`pi auth check --model <id>` without the provider qualifier reports `not_ready` even
when the model is fine — check the provider-qualified form.

## Jev integration (the cost-routing hooks)
The five high-value Jev hooks in the pi loop, from ten-levels-of-jev and mapped in
steadfaste `docs/design/coding-cost-routing.md`:
1. task-routing classifier (before any model is chosen — the biggest saving)
2. destructive-command gate (before tool execution)
3. compaction scoring (when context fills — prune lowest-scored instead of a summariser LLM)
4. cheap file reads (judge a file without reading it into context — $0.00049 vs $0.091)
5. output-type screening (after an LLM response)

## Pitfalls
- **Local small models (qwen2.5:3b) are weak at tool-calling** — use offline/local
  for *generation* and let pi do the *loop*; a ROUTINE task that needs tool-chaining
  routes to a hosted workhorse rather than forcing the local model to tool-call.
- **A block notice is an instruction, not a control** — an agent was observed
  routing around a write gate by writing the same file via a bash heredoc. The
  deterministic gate remains the authority; Jev gates add scrutiny, never remove it.
- **The agent can read its own environment** — its bash tool can print every env
  var it was given. Hand pi only shell basics + the Jev/provider keys + Jev settings;
  treat `.sessions/` as sensitive.
- **Never let the agent author its own Jev question blocks at runtime** (steadfaste
  MN-3: the question is the policy). The questions are Steward-ratified Decision
  Class config; the agent reaches for Jev, it does not write the questions.
- **Fail closed on routing** — an undecidable/unknown/missing classification routes
  pessimistically to the most capable (most expensive) tier, never a silent cheap
  default.
- **An optional chain over a guessed API hides the defect** — `event.completed?.()`
  returned `undefined` against a non-existent method, so every checkpoint was
  written EMPTY while the code looked defensive. When a hook must produce output,
  assert the output is non-empty (warn loudly with the observed keys) rather than
  letting `?.` be the difference between working and silent.
- **Verify a hook's EFFECT without an LLM run.** A host with no provider ready
  cannot run a turn, so don't wait on one to test wiring: import the extension with
  Node 22's `--experimental-strip-types`, call its default export with a fake `pi`
  (`{ on, registerTool }`) that captures the handlers, fire the handler with a
  synthetic event in Pi's real shape, and assert the effect landed (a store row
  exists) — a stderr marker alone proves only that the handler ran.
- **`ToolResultEventBase` carries `input`/`content`/`isError` but NOT `toolName`** —
  only the concrete variants (`BashToolResultEvent`, …) declare it. Read `toolName`
  defensively in a generic `tool_result` handler.
- **`python3` may not be on pi's PATH on macOS** — Homebrew is `/opt/homebrew/bin`
  (Apple Silicon) or `/usr/local/bin` (Intel), and a GUI-launched pi sees a narrower
  PATH than your shell. Make the interpreter overridable (e.g.
  `CORTEX_CONTEXT_PYTHON`) instead of hardcoding `python3`.
