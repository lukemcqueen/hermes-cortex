# Pi extension API — the shapes that decide whether a harness works

Pi's extension surface is small and **version-sensitive**, and every mismatch is
SILENT. Read the installed truth; never infer from a doc, an example, or a version
number in a registry.

## Find the installed truth

```bash
V=$(cat ~/.pi/agent/install/current-version)
P="$HOME/.pi/agent/install/releases/$V/node_modules/@earendil-works/pi-coding-agent"

grep -n -A20 'registerTool'                    "$P"/dist/core/extensions/types.d.ts
grep -n -A8  'interface ToolDefinition'        "$P"/dist/core/extensions/types.d.ts
grep -n       'interface TurnEndEvent\|interface BeforeAgentStartEvent\|ToolResultEvent' \
                                               "$P"/dist/core/extensions/types.d.ts
# AgentToolResult lives in the agent core package, NOT pi-coding-agent:
grep -rn -A12 'interface AgentToolResult'      "$P"/../pi-agent-core/dist/types.d.ts
```

## The tool contract (pi 1.0.0)

```ts
// ToolDefinition
{
  name, label, description,
  parameters: TParams,          // a TypeBox / JSON OBJECT schema
  execute(toolCallId, params, signal?, onUpdate?): Promise<AgentToolResult>
}

// AgentToolResult
{ content: (TextContent | ImageContent)[], details: T }
// TextContent = { type: "text", text: string }
```

Two independent ways to break every tool at once, both silent:

| Wrong | Symptom |
|---|---|
| `run: async (input) => …` (the 0.87.1 shape) | `definition.execute is not a function` on every call |
| `parameters: { peer: { type: "string" } }` (bare param map) | the call fails schema validation |

`parameters` must be `{ type: "object", properties, required }`. Build it from the
SAME properties map that drives argument extraction — a second hand-kept key list is
how the schema and the call drift apart.

## Hooks (unchanged across 0.87 → 1.0)

`pi.on("before_agent_start" | "turn_end" | "session_before_compact" | "tool_result"
| "tool_call", handler)`; `ExtensionHandler<E> = (event, ctx) => R | void`.

- The FIRST parameter is the EVENT, not a ctx.
- `before_agent_start` injection is the RETURN value (`{ systemPrompt }`); there is
  no `ctx.addSystemPrompt()`.
- `ToolResultEventBase` carries `input`/`content`/`isError` but NOT `toolName` —
  only the concrete variants declare it, so read it defensively.

## The executable guard recipe

A static grep cannot see a signature or a schema shape, so it cannot catch either
fault above. Execute instead:

1. Load the real extension through pi's own loader (jiti ships in the release
   `node_modules`): `createJiti(import.meta.url).import(<ext>, { default: true })`.
2. Hand the default export a stub `pi`: `{ on: (n, fn) => hooks[n] = fn,
   registerTool: (d) => tools.push(d) }`.
3. Assert, per tool: `typeof t.execute === "function"`, no `t.run`,
   `parameters.type === "object"` with `properties` + `required`, and every
   `required` key declared in `properties`.
4. CALL `await t.execute("call-1", { … })` with `CORTEX_CONTEXT_CLI` pointed at a
   throwaway stub (never the real store) and assert the returned
   `{ content: [{ type: "text", text }], details }` and that the argument reached
   the CLI.
5. Prove it discriminates: run the SAME guard against the pre-fix extension and
   require a non-zero exit. Regenerate committed evidence with hashes of the
   tested files so a reviewer with a truncated diff can still confirm the tested
   file is the committed one.

## Pitfalls that cost the most time

- **A tool that exists on the store contract but is missing from the extension is
  unreachable to the agent** — and the extension's hand-written list drifts as the
  shared contract grows. Prefer a route that DERIVES the surface (an MCP server
  reading the contract) over a hand-maintained registration list; keep the
  extension for the lifecycle triggers an MCP server cannot provide.
- **`mem_*/session_*` inside a block comment closes it** — the `*/` in a glob
  terminates a `/** … */` doc block and the file stops parsing. Write `mem_* /
  session_*` or drop the slash.
- **A `$HERE/../..` depth is off by one more often than you expect.** Print the
  resolved root before using it; a wrong root makes a node script report
  `MODULE_NOT_FOUND` and pytest report `collected 0 items`, which looks like a
  code failure rather than a path failure.
