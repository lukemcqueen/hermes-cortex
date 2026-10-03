# pi extension — committed, re-runnable evidence

Regenerate with: `bash ops/install/harnesses/pi/run-evidence.sh`

Generated: 2026-10-03T05:42:07Z  ·  host: esther

The guard loads the REAL extension through pi's own jiti loader, hands it
a stub `pi`, and CALLS `execute(id, params)` against a throwaway CLI — the
store is never touched. A static grep cannot see a tool signature or a
schema shape, which is why the bug shipped; this can.

## 1. Fixed extension — wiring executes: PASS (exit 0)

```
✅ content[0] is {type:'text', text} the model can read
✅ execute() returned details (AgentToolResult.details)
✅ execute() passed the model's argument through to the CLI: {"ok": true, "tool": "mem_context", "args": {"peer": "user"}}
✅ execute() tolerates a missing optional arg

✅ EXTENSION WIRING OK — 11 tools executed against the pi 1.0.0 AgentTool shape.
```

## 2. Test suite (includes the executable guard): PASS (exit 0)

```

tests/test_context_harnesses.py ..........................               [100%]

============================== 26 passed in 1.58s ==============================
```

## 3. PRE-FIX extension (48e85271) — same guard, must fail: FAIL (exit 1)

Reproduces the live failure verbatim (`definition.execute is not a function`):

```
   - session_note: execute() is a callable (the pi 1.0.0 AgentTool shape)
   - session_close: execute() is a callable (the pi 1.0.0 AgentTool shape)
   - session_tool_event: execute() is a callable (the pi 1.0.0 AgentTool shape)
   - session_loaded_skill: execute() is a callable (the pi 1.0.0 AgentTool shape)
   - execute() threw instead of returning a result: TypeError: target.execute is not a function
   - execute() threw on empty params: TypeError: target.execute is not a function
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
