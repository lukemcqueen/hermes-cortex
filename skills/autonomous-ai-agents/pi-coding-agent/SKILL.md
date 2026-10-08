---
version: 1.0.0
name: pi-coding-agent
description: "Operate the Pi coding agent CLI — install, extensions, Jev."
---

# Pi Coding Agent

The coding-agent harness the fleet owner wants for steadfaste (replacing hermes).
`@earendil-works/pi-coding-agent` — a MANAGED install, not an npm global (see
Install below). The reference for pi + Jev
integration is `github.com/disler/ten-levels-of-jev` (30 tested Jev use cases in
10 levels; levels 6–10 put Jev inside pi).

## Install — a MANAGED install, NOT an npm global (corrected 2026-10-02)

Pi installs itself into its own agent directory and pins each release; there is no
`npm install -g`. Measured on a live host:

    ~/.pi/agent/bin/pi                        launcher (sh): reads the version, execs the release
    ~/.pi/agent/install/current-version       the authoritative version string (1.0.0 here)
    ~/.pi/agent/install/managed-install.json  {kind: pi-managed-install, layout: releases-v1,
                                               entrypoint: symlink -> <user bin dir>/pi}
    ~/.pi/agent/install/releases/<v>/node_modules/.bin/pi    the real executable
    ~/.local/share/pi-node/current/bin        Node.js that PI installs and manages

Consequences that cost time and must not be re-learned:

- **`command -v pi` is NOT a reliable probe.** The entrypoint is a symlink into the
  user's bin dir (a linuxbrew `bin/` on one measured host). When that
  dir is not on PATH, `pi` looks *missing* to every caller while being installed and
  working. Invoke the launcher directly — `~/.pi/agent/bin/pi` — or read
  `~/.pi/agent/install/current-version` without executing anything.
- **Pi's Node is deliberately NOT on shell profiles.** The launcher puts
  `~/.local/share/pi-node/current/bin` on PATH for itself and its children, so `node`
  and `npm` resolve correctly inside pi and nowhere else. Do not "fix" that by
  exporting it globally.
- **Extension type defs live in the release, not an npm root:**
  `V=$(cat ~/.pi/agent/install/current-version)` then
  `$HOME/.pi/agent/install/releases/$V/node_modules/@earendil-works/pi-coding-agent/dist/...`
- **Never infer the version from a doc or a package name** — read `current-version`
  (or the launcher's `--version`). A harness registry claiming a shipped version can
  be stale on any given host: these hosts run 1.0.0 while the registry said 0.87.1.
- Verify: `~/.pi/agent/bin/pi --version` and `--help` (read/bash/edit/write tools, plus
  the `pi install/remove/list/config/auth` extension commands).

## Core
- Built-in tools: read, bash, edit, write.
- `pi install <source>` / `pi remove <source>` manage extension sources;
  `pi list` shows installed extensions.
- An extension is loaded as `pi -e extensions/<name>.ts --tools read,bash,edit,write[,<jev tools>]`
  — the `--tools` allowlist is explicit; only listed tools are available.

## stdout shape non-interactive — MEASURED, do not guess

A non-interactive pi turn writes EXACTLY the assistant's final answer to stdout and
nothing else — verified with a plain prompt and with a prompt that used the bash tool:

    $ ~/.pi/agent/bin/pi --model <m> "List three fruits, one per line, numbered 1. 2. 3."
     1. Apple
     2. Banana
     3. Cherry

- **Chatter goes to stderr and pi's own log, never to stdout.** So a wrapper that uses
  stdout verbatim is CORRECT, and one that takes "the last line" only TRUNCATES every
  multi-line answer down to its final line — a reply that arrives but is not complete.
  Verify stdout and stderr separately before choosing any output-shaping mode.
- **A fresh `--session-id` prints a benign stderr warning** — `Warning: No project session
  found with id '<id>'; creating a new session with that id.` — and still exits 0. That is
  how a per-chat session gets created, not a failure to report.
- **Call the launcher by absolute path from a service or wrapper.** `~/.pi/agent/bin/pi` is
  the launcher; the `pi` symlink in a user bin dir is not on a service PATH. Wrappers pass
  an ARGV LIST rather than a shell line, so nothing expands `~`/`$HOME` — a relative or
  guessed path becomes a silent per-message no-op. Pin the session identity too (e.g. a
  `CORTEX_SESSION_KEY`): a harness started outside a git repo cannot derive repo/branch and
  every chat otherwise collapses onto ONE session.

## Driving pi from another process — control calls go over RPC, never a prompt

A wrapper that only sends prompts is missing half the interface, and the missing half
fails in ways that read as pi being broken (working adapter to copy:
`ops/scripts/cortex_gateway/pi_control.py` in hermes-cortex).

- **A built-in slash command sent as a prompt is a NO-OP.** `/compact`, `/model`,
  `/new`, `/restart`, `/settings` are handled only in the interactive/RPC surfaces; as a
  prompt they become conversation (a forwarded `/new` is answered as prose while every
  bit of context stays). Session and state operations go over **RPC mode**:
  `pi --mode rpc` takes one JSON record per line on stdin (`{"type":"get_state"}`,
  `{"type":"compact"}`, `{"type":"set_model", …}`) and answers with a `response`
  record on stdout — correlate by the `id` you sent, never by response order.
- **Pass `--no-mcp` for a control call.** pi connects its MCP servers at RPC startup,
  and with them enabled the control call sat ALIVE and SILENT (no stdout, no stderr)
  for the whole deadline on ~40% of runs; the same call answered 8/8 in ~1.2 s with
  `--no-mcp`. A control call uses no MCP tool, so those servers are pure risk there.
- **Watch the process EXIT as well as EOF.** EOF is not the only end of an answer:
  pi's MCP children inherit its stdio, so a lingering grandchild holds the write end of
  the pipe open — no data, no EOF — and a reader waiting only for EOF blocks for its
  full deadline. Start pi in its own process group (`start_new_session=True`) and kill
  the GROUP on timeout, so a wedged control call does not also leak children.
- **`compact` never answers for a session whose transcript does not exist yet**
  (45 s+, repeated), while `get_state` on the same id answers in ~1.2 s and creates it.
  Ask for the state first and answer "no conversation yet" — a chat that has just
  started a fresh session is exactly this case, and it is the common one.
- **Give a check three outcomes, not two**: `0` ok · `1` a NEGATIVE answer · `3` could
  not verify. `--offline --list-models <pattern>` prints `No models matching "x"` and
  still **exits 0**, so a verdict read off the exit code is wrong in both directions —
  decide from the OUTPUT, and make "pi cannot be run at all" its own outcome rather
  than a failed check. The same split lets a caller refuse a bad model name instead of
  breaking every later turn with it.

## Extension API (the Jev-hook surface)

**Read the installed type defs before writing a hook — never infer the signature.**
```bash
V=$(cat ~/.pi/agent/install/current-version)
P="$HOME/.pi/agent/install/releases/$V/node_modules/@earendil-works/pi-coding-agent"
sed -n '1,60p' "$P"/dist/core/extensions/types.d.ts   # + grep the event interfaces
grep -n -A20 'registerTool' "$P"/dist/core/extensions/types.d.ts        # the tool registration contract
grep -n -A8  'interface ToolDefinition' "$P"/dist/core/extensions/types.d.ts
# AgentToolResult is NOT in this package — it comes from the agent core:
grep -rn -A12 'interface AgentToolResult' "$P"/../pi-agent-core/dist/types.d.ts
```

Read `ToolDefinition` FIRST. It is the contract the extension must satisfy, and a
doc or an older example that disagrees with it is what breaks the harness silently.

- **Hooks** — `pi.on("tool_call" | "tool_result" | "turn_end" | "before_agent_start" | "session_before_compact", fn)`. A `tool_call` hook can `return { block: true, reason }` to stop a tool call before it runs; the agent sees only the reason + a notice that the block is final.
- **The handler's FIRST parameter is the EVENT, not a ctx**: `ExtensionHandler<E> = (event: E, ctx: ExtensionContext) => R`. Reading `ctx.<thing>` off that first parameter yields `undefined`.
- **Injection is the RETURN VALUE.** `before_agent_start` returns `BeforeAgentStartEventResult` (`{ message?, systemPrompt? }`); there is **no `ctx.addSystemPrompt()`**. To add context, return an augmented `systemPrompt` (or a `message`).
- **Event payloads carry the data**: `turn_end` → `{ turnIndex, message, toolResults, entries, outcome }`; `before_agent_start` → `{ prompt, images, systemPrompt, systemPromptOptions }`. Derive what you need from the event.
- **Tools** — `pi.registerTool({ name, label, description, parameters, execute })`.
  `execute(toolCallId, params, signal?, onUpdate?)` returns an `AgentToolResult`:
  `{ content: [{ type: "text", text }], details }`. **`run` is the pi 0.87.1 shape and
  is silently ignored on 1.0.0** — every call then fails with
  `definition.execute is not a function`, which an agent reads as "memory is broken"
  when the store is fine and the tool WIRING is not. `parameters` must be an object
  schema (`{ type: "object", properties, required }`); a bare param→schema map
  (`{peer:{type:"string"}}`) is not validatable, so a correct `execute` still fails.
  Build the schema AND the argument extraction from ONE properties map so the two
  cannot drift apart. Tool descriptions carry the question schema.
- **Verify a hook fires AND does its job** — a stderr marker in the handler proves the hook ran, not that the effect landed. Assert the effect (did the injected text appear? did the row have content?).
- **Compaction** — `.pi/settings.json` sets `compaction.keepRecentTokens` low so compaction has material; `ctx.compact()` wraps pi's compaction; `ctx.getContextUsage()` feeds the numbers.

Exact type shapes, the probe commands, and the executable-guard recipe:
`references/extension-tool-api.md`.
- **Side channel** — report every decision on stderr as `JEV_EVENT` lines (and as session entries) so a run is auditable line-by-line (tool call, hook decision, Jev call, model, cost, context).

## Cortex context (memory + session)

**Pi >= 0.99 / 1.0 has an MCP client** (pi 1.0.0, reproduced: `pi mcp list` reports
`cortex-context: connected, N tools`): it reads
`mcpServers` from `~/.pi/agent/mcp.json` (user scope) and `.pi/mcp.json` (trusted
projects only), the same shape as Claude Code. Governance is therefore an MCP
registration — never hand-write a lock:

```bash
bash ~/hermes-cortex/ops/scripts/install/install-pi-mcp.sh   # loop-governance, tasks, executor, agent-bus, cortex-context
pi mcp list                                                 # expect 5 servers, state "connected"
```

**Verify a host VERSION-AWARE — never by assuming the route.**
`bash ~/hermes-cortex/ops/scripts/manage/audit-pi-integration.sh` reports PASS/FAIL
per layer (MCP servers, curated skills, extension, governance gate, `agent.env`),
reads the installed version from the Pi install itself, and takes the curated skill
list from the `skills.yaml` `always:` manifest instead of a hardcoded list. Auditing
with the MCP checklist on a Pi that has no MCP client reports FAIL for something
that route cannot deliver — the failure is in the checklist, not the host. A server
missing from `mcp.json` on a non-orchestrator host is usually a DEPLOY-SCOPE bug
(a server registered `register_orch` ships only to orchestrators), not a broken
installer: `install-pi-mcp.sh` warns and registers the rest, so 3-of-4 looks normal.

The **memory/session TOOLS** also come from that MCP server — the SAME
`cortex-context-mcp.py` Claude Code and Codex use, so the schemas are DERIVED
from the store contract and there is no per-harness tool list left to drift.
The extension keeps ONLY the lifecycle triggers, which MCP cannot provide:

```bash
bash ~/hermes-cortex/ops/scripts/install/install-pi-mcp.sh   # + cortex-context
cp ~/hermes-cortex/ops/install/harnesses/pi/extensions/cortex-context.ts extensions/
pi -e extensions/cortex-context.ts --tools read,bash,edit,write
```

An older Pi (<= 0.87, no MCP client) reaches the same governance through the
`loop-gov` CLI instead.

The extension registers **NO tools** and wires only the lifecycle:

- `before_agent_start` → restore + inject the checkpoint (a fresh session resumes)
- **`turn_end` → write a checkpoint** — the harness owns WHEN, never the model
- `session_before_compact` → checkpoint before continuity is lost
- **`tool_result` → record the tool event** for tools a gate asks about. The git hook
  is GLOBAL, so a Pi commit is gated by the same reflexion gate as a Hermes one, and
  that gate reads HC's store — not the harness's own DB. With no `tool_result` hook a
  Pi session has no recorded evidence and **every commit is refused** no matter how
  well the agent behaved.

**Do NOT register the shared tools in the extension.** They used to live there as a
hand-written `tool()` list with hand-written parameter maps — a SECOND definition of
tools that already existed in the contract, and the copy that broke silently when pi
moved 0.87.1 → 1.0.0. Two definitions of one capability means the runtime resolves one
and the other becomes a phantom. Tools stay in the shared MCP server; only the
triggers stay in the extension.

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
                "key": "!bash ~/.hermes-cortex/scripts/env-value.sh OPENROUTER_API_KEY"}}
```

`env-value.sh` prints one named value (cortex env first, then the Hermes env, first
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
- **A presence probe can be wrong about a managed install.** `command -v pi` reports
  "missing" on a host where Pi is installed and working, because the entrypoint is a
  symlink into a bin dir that need not be on PATH. When a probe says a tool is absent,
  check the install LAYOUT (launcher, `current-version`, `releases/`) before reporting
  it missing to anyone — a false "not installed" sends the user chasing a non-problem,
  and the correction costs more than the check did.
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
- **Verify a hook's or tool's EFFECT without an LLM run.** A host with no provider
  ready cannot run a turn, so don't wait on one to test wiring: load the extension
  with **pi's OWN TypeScript loader** (it ships jiti in its release `node_modules`),
  call its default export with a fake `pi` (`{ on, registerTool }`) that captures the
  handlers/tools, fire a synthetic event in Pi's real shape, and assert the effect
  landed (a store row exists) — a stderr marker alone proves only that the handler ran.
- **A guard that greps cannot see a signature or a schema shape — EXECUTE the wiring.**
  Guards asserting that tool NAMES exist and that the shared CLI is called all passed
  while every tool was dead, because the defect was the tool definition's SHAPE. Load
  the real extension, hand it a stub `pi`, and CALL `execute(id, params)` against a
  throwaway CLI — never the real store. Then prove the guard discriminates: run it
  against the PRE-FIX extension and require it to FAIL
  (`TypeError: <tool>.execute is not a function`). A guard that has never failed on the
  broken artifact is a happy path, not a guard. Recipe and exact shapes:
  `references/extension-tool-api.md`.
- **`ToolResultEventBase` carries `input`/`content`/`isError` but NOT `toolName`** —
  only the concrete variants (`BashToolResultEvent`, …) declare it. Read `toolName`
  defensively in a generic `tool_result` handler.
- **Never put `*/` inside a block comment — a GLOB will close it early.** Writing an
  identifier like `mem_*/session_*` (or any `foo_*/bar`) in a `/** … */` header ends
  the comment at the `*/`, so the rest parses as code and the extension fails to LOAD
  (`ParseError: Missing semicolon`, or `SyntaxError: Unexpected token '*'`). Pi then
  reports the tools as missing, which reads like a wiring problem rather than a typo.
  Write `memory/session`, or space it (`mem_* / session_*`). The same trap applies to
  any glob you paste into a JSDoc/TSDoc comment.
- **`python3` may not be on pi's PATH on macOS** — Homebrew is `/opt/homebrew/bin`
  (Apple Silicon) or `/usr/local/bin` (Intel), and a GUI-launched pi sees a narrower
  PATH than your shell. Make the interpreter overridable (e.g.
  `CORTEX_CONTEXT_PYTHON`) instead of hardcoding `python3`.
