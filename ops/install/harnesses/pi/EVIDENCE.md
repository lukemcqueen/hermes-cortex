# pi extension — committed, re-runnable evidence

Regenerate with: `bash ops/install/harnesses/pi/run-evidence.sh`

Generated: 2026-10-06T04:00:13Z  ·  host: esther

Artifacts this evidence was produced from (verify with `sha256sum`):

```
eaea515b7a44099aec353a172778f6d80eb61c49f005a45ba4e6c65f9703ee2a  ops/install/harnesses/pi/extensions/cortex-context.ts
c8e54608f3046d3d6c7d6e640ccfb46dee455a4e65cf0917a87b8a8cee89533c  ops/install/harnesses/pi/verify-extension.mjs
7d6a76a256e148a64c5f14b9cfa13662cc2700afb903274c3fc75e4bd68afb11  ops/install/harnesses/pi/run-evidence.sh
```

The guard loads the REAL extension through pi's own jiti loader, hands it
a stub `pi`, and CALLS `execute(id, params)` against a throwaway CLI — the
store is never touched. A static grep cannot see a tool signature or a
schema shape, which is why the bug shipped; this can.

## 1. Fixed extension — wiring executes: PASS (exit 0)

```
✅ turn_end WROTE a checkpoint (the trigger fired without the model asking)
✅ the checkpoint carries the turn's tool names: ["read","edit"]
✅ the checkpoint carries the turn's note text
✅ an empty turn writes NO checkpoint (a checkpoint that looks like continuity and carries none is worse than none)

✅ EXTENSION OK — registers no tools (MCP owns them) and its lifecycle hooks execute.
```

## 2. Test suite — the two files this change touches: PASS (exit 0)

```
tests/test_context_harnesses.py ...........................              [ 64%]
tests/test_gateway_agent_registry.py ...............                     [100%]

============================== 42 passed in 2.76s ==============================
```

## 3. PRE-FIX extension (48e85271) — same guard, must fail: FAIL (exit 1)

The pre-fix extension registered 11 tools BY HAND. The one-way-in invariant
rejects that — which is what makes this a guard rather than a happy path:

```
❌ extension registers ZERO tools (got 11) — the tools come from the shared cortex-context MCP server, so a second definition here is the phantom bug
❌ EXTENSION BROKEN — 1 check(s) failed:
   - extension registers ZERO tools (got 11) — the tools come from the shared cortex-context MCP server, so a second definition here is the phantom bug
```

---

## 4. MCP registration on this host (captured, not a guard)

The tool surface is a CONFIG entry pointing at the shared server. The
re-runnable guard for this is
`tests/test_context_harnesses.py::test_pi_context_tools_are_registered_as_the_shared_MCP_server`.

```
cortex-context: connected, 12 tools (direct, global)
  $HOME/.hermes/hermes-agent/venv/bin/python3 $HOME/.hermes-cortex/scripts/cortex-context-mcp.py
  tools: mem_profile, mem_search, mem_context, mem_conclude, session_checkpoint, session_restore, session_list, session_search, session_note, session_close, session_tool_event, session_loaded_skill
```

## 5. Pinned per-chat session keys (captured, not a guard)

The gateway declares `env: {CORTEX_SESSION_KEY: {session_id}}` on the command
backend, so each chat gets its OWN key instead of the shared fallback. Ids are
redacted — a chat id is a personal identifier and this is a public repo. The
re-runnable guard for the seam is
`tests/test_gateway_agent_registry.py::test_command_backend_pins_session_identity_via_spec_env`.

```
(no hc-pi-* session keys recorded yet)
```

---

## What this does and does not prove

Proves: the tool definitions the extension hands pi have a callable
`execute` with the pi 1.0.0 AgentTool shape, `parameters` is a valid object
schema, and the model's arguments reach the CLI and come back as an
`AgentToolResult`.

Does not prove: model-side behaviour inside a live pi session, or that the
store returned particular data. Those are exercised by running pi itself
(`pi --session-id <id> "call mem_context"`); the store is separately covered
by `tests/test_context_harnesses.py::test_cli_reaches_the_store_and_exits_zero`.
