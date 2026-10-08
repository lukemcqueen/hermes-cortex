# Memory-Provider Tool Registration (advertised ≠ routed)

A memory provider can list its tools in the system prompt while every call of them
fails with `{"error": "Unknown tool: mem_profile"}`. The gateway log tells the
story in one line: `Memory provider 'mycortex-mem' registered (0 tools)` while the
prompt advertises five.

## Why: two passes, different timing

MemoryProvider tools register in TWO passes, and they run on opposite sides of
`initialize()`:

- **Routing table** — `add_provider` → `get_tool_schemas()` runs BEFORE
  `initialize()` in `agent_init.py`. If `get_tool_schemas()` gates on runtime
  state (e.g. `self._pg`), it returns `[]` at registration time, so the
  executor's routing table stays empty.
- **System prompt** — `inject_memory_provider_tools` → `get_all_tool_schemas`
  runs AFTER `initialize()`. By then `_pg` exists, so the schemas ARE advertised
  in the prompt.

Result: advertised by the prompt, unroutable by the executor. The contradiction
is between two passes of the SAME provider, which is why reading either one alone
looks correct.

## Fix

`get_tool_schemas()` must return static schemas **unconditionally** — only
`_cron_skipped` / context-only recall mode may suppress them. Never gate the
schema list on connection state that exists only after `initialize()`.

## Regression test (RED → GREEN)

Instantiate the provider, call `get_tool_schemas()` BEFORE `initialize()`, and
assert the full tool set. Written against the unfixed code it must fail, or you
have not shown the hole existed.

## Generalisable rule

When a component is initialised in stages, any capability list it exposes must be
answerable in the EARLIEST stage a consumer asks in — otherwise the consumer that
asks early (routing) and the consumer that asks late (prompt) disagree, and the
user-visible symptom points at the tool rather than at the ordering.
