# Interop Standards — Agent Ecosystem Taxonomy

Protocols that let agents and frameworks talk to each other. Use this to identify
which wire-level surfaces a third-party framework actually exposes.

## MCP — Model Context Protocol

Tools and connections. A server exposes tools/resources; a client consumes them.
Framework-agnostic, over stdio or HTTP. **Hermes Cortex status: supported**
(cortex-bus-mcp, executor-mcp, loop-gov-mcp, task-mcp; Hermes also acts as MCP client).

## ACP — Agent Client Protocol

Agent ↔ *client/editor* launch. A client (e.g. Zed, `acpx`) launches an agent as a
local subprocess and drives it over newline-delimited JSON-RPC on stdio (v1 is stable).
Covers streamed text/reasoning, tool-call requests + results, one-time approvals,
form elicitation, cooperative turn cancellation, concurrent sessions, session close.
Security note: ACP does *not* mount the editor's filesystem/terminal into the agent;
`session/new.cwd` only identifies the app to launch.

**Hermes Cortex status: NOT supported** (no `agentclient`/`acpx`/"agent client
protocol" anywhere in the repo). Adding it means a small JSON-RPC-over-stdio shim in
either direction:
- **server** — expose a Hermes agent so Zed/`acpx`/other frameworks can drive it;
- **client** — let Hermes launch and drive an ACP agent (e.g. an `eve acp` subprocess).

## UCP — Universal Commerce Protocol

Agentic commerce. A business declares support by serving a JSON profile at
`/.well-known/ucp` (spec versions, services, payment handlers, signing keys).
Signed request/response verification via EC P-256 public keys. Requires HTTPS,
`cache-control: public, max-age>=60`, no 3xx on the profile endpoint.
**Hermes Cortex status: NOT supported** — only relevant if agentic commerce/payments
enter scope; usually out of scope for this fleet.

## Common transport / discovery notes

- ACP and MCP are both JSON-RPC over stdio by default; ACP reserves stdout for the
  protocol stream and sends logs to stderr so they can't corrupt it.
- Frameworks increasingly add `llms.txt` / typed SDKs / MCP servers purely for agent
  *discoverability* — a docs artifact, not core runtime code. Worth a quick check that
  our own docs publish `llms.txt`, but not a core gap.
