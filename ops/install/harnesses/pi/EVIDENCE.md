# pi extension — committed, re-runnable evidence

Regenerate with: `bash ops/install/harnesses/pi/run-evidence.sh`

Generated: 2026-10-03T06:44:55Z  ·  host: esther

Artifacts this evidence was produced from (verify with `sha256sum`):

```
582e5654cabd0503598c8583301bb1479352e3c145311ff2f17d06e204e2c1b5  ops/install/harnesses/pi/extensions/cortex-context.ts
a20ab85eb54ba28febeac5c35fa81029fc6f5e6ff242d781331176e18f238520  ops/install/harnesses/pi/verify-extension.mjs
a79d4a3179165d6cc9ce2957687faba8839ba2bc3c2e0770c150d600acf16a6b  ops/install/harnesses/pi/run-evidence.sh
```

The guard loads the REAL extension through pi's own jiti loader, hands it
a stub `pi`, and CALLS `execute(id, params)` against a throwaway CLI — the
store is never touched. A static grep cannot see a tool signature or a
schema shape, which is why the bug shipped; this can.

## 1. Fixed extension — wiring executes: PASS (exit 0)

```
✅ the checkpoint carries the turn's tool names: ["read","edit"]
✅ the checkpoint carries the turn's note text
CORTEX_CHECKPOINT_EMPTY turn=2 keys=turnIndex
✅ an empty turn writes NO checkpoint (a checkpoint that looks like continuity and carries none is worse than none)

✅ EXTENSION OK — registers no tools (MCP owns them) and its lifecycle hooks execute.
```

## 2. Test suite (includes the executable guard): PASS (exit 0)

```

tests/test_context_harnesses.py ..........................               [100%]

============================== 26 passed in 1.66s ==============================
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

## What this does and does not prove

Proves: the tool definitions the extension hands pi have a callable
`execute` with the pi 1.0.0 AgentTool shape, `parameters` is a valid object
schema, and the model's arguments reach the CLI and come back as an
`AgentToolResult`.

Does not prove: model-side behaviour inside a live pi session, or that the
store returned particular data. Those are exercised by running pi itself
(`pi --session-id <id> "call mem_context"`); the store is separately covered
by `tests/test_context_harnesses.py::test_cli_reaches_the_store_and_exits_zero`.
