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
- **Hooks** — `pi.on("tool_call" | "tool_result" | "turn_end" | "before_agent_start" | "session_before_compact", fn)`. A `tool_call` hook can `return { block: true, reason }` to stop a tool call before it runs; the agent sees only the reason + a notice that the block is final.
- **Tools** — `pi.registerTool({ name, label, description, parameters, run })`. Tool descriptions carry the question schema; a `before_agent_start` hook injects a one-line system-prompt nudge so the agent knows the tool exists.
- **Compaction** — `.pi/settings.json` sets `compaction.keepRecentTokens` low so compaction has material; `ctx.compact()` wraps pi's compaction; `ctx.getContextUsage()` feeds the numbers.
- **Side channel** — report every decision on stderr as `JEV_EVENT` lines (and as session entries) so a run is auditable line-by-line (tool call, hook decision, Jev call, model, cost, context).

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
