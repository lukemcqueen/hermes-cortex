# Harness integration — how any coding agent gets cortex memory + session

This tree wires **coding-agent harnesses** to the cortex context store (memory +
session over one store, S2c). It is built to scale to ~100 harnesses without
producing ~100 disagreeing documents.

## The two rules that shape everything here

**1. The access layer is per-harness; the tool surface is shared.**
Every harness reaches ONE implementation
(`ops/services/mycortex-mem/context_tools.py`). What differs is the transport:

| Layer | Used by | Why |
|---|---|---|
| `mcp` | Hermes, Claude Code, Codex | they read MCP servers from their own config — no shim needed |
| `cli-extension` | **Pi** | Pi has **no MCP client**; its surface is `pi.on(hook)` + `pi.registerTool`, so it shells out to the shared CLI |
| `cli-hook` | anything that only needs a lifecycle command | trigger only, no tool surface |
| `none` | declared-unsupported | the gap is **visible with its reason**, never silently absent |

> **The mistake this tree exists to prevent:** assuming every harness speaks MCP.
> A wrong layer yields a wiring that "exists" and does nothing.

**2. The harness owns WHEN a checkpoint is written — never the model.**
The tool surface is only half. A session that was *killed* cannot call a tool, so
the trigger lives in the harness lifecycle (`turn_end` in Pi, a boundary call or
cron in Hermes). Putting it in the system prompt as "remember to save" is not a
mechanism — it fails exactly when it matters.

## Layout

```
registry.yaml            ← THE SINGLE SOURCE — one entry per harness
generate-harnesses.py    ← derives every README + INDEX.md from the registry
INDEX.md                 ← generated coverage table (start here)
<harness>/README.md      ← generated: install, run, verify (never hand-written)
<harness>/…              ← a bespoke artifact, only if the layer needs one
                           (e.g. pi/extensions/cortex-context.ts)
```

## Adding a harness (#37, #38, …)

```bash
python3 generate-harnesses.py --report                       # what is declared
python3 generate-harnesses.py --add aider --layer mcp --surface '~/.aider.conf.yml'
#   → fill in why / install / verify in registry.yaml
python3 generate-harnesses.py                                # derive the docs
python3 generate-harnesses.py --check                        # CI: everything current?
```

A registry entry must carry **`why`** (the evidence for the layer) and, unless the
layer is `none`, **`surface` + `install` + `verify`**. An entry without `verify`
is rejected: an unverifiable instruction is how a wiring ships broken.

Generated files carry a `GENERATED … do NOT edit by hand` banner. A hand-edit is
both a bug and futile — `--check` flags it and the generator erases it.

## Verifying a wiring

Follow the harness's generated README. The short version — **never report a
wiring you have not exercised**:

1. Read path: call `mem_context` **in the harness**; the peer card must return.
2. Write path **through the harness**: let a turn end with a marker decision, then
   `cortex-context session_restore '{}' | grep <marker>`. Missing ⇒ the hook is
   not firing.
3. Session-start injection: a second session shows the checkpoint unasked.
4. Fail-open: stop the store; the harness must continue, not error.

Full runbook: [`docs/runbooks/context-integration.md`](../../../docs/runbooks/context-integration.md)
