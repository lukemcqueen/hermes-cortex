# Adapter Layer — how foreign coding agents hook in (grounded, 2026-09-11)

Topical depth for the harness 'add hooks for other harnesses/coding agents'
class of work. Grounded against the real codebases of the then-top coding
agents; re-verify surfaces before building any given adapter — the seams below
are the *shape*, not a promise that a specific CLI flag is still current.

## The core finding: every serious agent is the SAME shape

Research across ~17 harnesses collapsed to one pattern:

| Shape | The agent is… | The hook | Examples |
|-------|--------------|----------|----------|
| **(a) Delegated CLI** | self-contained agent with its OWN tool loop | run the CLI in a sandbox; govern JOB + RESULTS, not internals | Claude `-p` · Pi CLI · Codex `exec` · Cursor `agent -p` · Copilot `-p` · Aider `-m` · Gemini `-p` · Goose `run` · OpenHands `--headless` · OpenCode `run` · Qwen `-p` · Crush `run` · Cline `--json` · Devin `--` |
| **(b) Native provider** | a model/API we call through an LLM adapter — WE run the loop | an LLM adapter; *we* own tool-calling, state, governance | Claude API · OpenRouter · local (Ollama/llama.cpp) |

**The anti-bloat punchline:** because ~all agents are shape (a), the whole
catalog collapses to **TWO reusable seams** — (1) a generic *sandboxed
delegated-CLI adapter* (shell out with `-p`/`exec`/`run`, read JSON/NDJSON out)
and (2) an *MCP seam* (hand any of them our governed tools). Do NOT write a
bespoke adapter per harness; the generic pair covers the market, and a provider
change or better third-party surface never touches the core.

## Two reinforcing evidence points

- **MCP is the cross-harness agent-tools dialect** — every one of the ~17
  supported MCP. Adopt MCP as the extension seam; it validates itself by
  market consensus. Capability negotiation (buttons vs reply-words, webhook vs
  long-poll, text length) belongs in the TRANSPORT/ADAPTER layer, never the core.
- **bubblewrap-style `--sandbox` is the common isolation answer** (Codex,
  Cursor, Devin) — reinforces an OS-level sandbox with egress revocation as
  *borrowed, not invented*.

## Grounded per-family reference (session snapshot)

Per-family provider adapters + a config file that swaps providers is the
recurring provider seam. Standouts to borrow as PATTERNS (never as
dependencies): **Pi `pi-ai`** — a unified multi-provider LLM adapter (~60
providers); **Pi CLI session semantics** (`/session` `/fork` `/tree`);
**OpenSwarm `adapter:` system** — per-family adapter value + live provider
switch + role-scoped tool grants; **OpenSwarm compose/`bwrap` executor** for
sandboxing a delegated CLI.

## Market-reality note (the landscape moves — don't design to a fossil)

Windsurf was acquired by Cognition and rebranded **Devin Desktop** (its agent
is now the Devin CLI/Cascade). Roo Code shut down (community forks live on).
Continue froze at v2.0.0. The live heavyweight set at snapshot was roughly:
Claude Code, Codex, Cursor, Copilot CLI, Aider, Gemini CLI, Goose, OpenHands,
OpenCode, Qwen Code, Crush, Cline, Devin + orchestrators (OpenSwarm). Always
re-verify a harness is still maintained before building its adapter.

## The Wire is the single seam for both shapes

The adapter translates between the agent's face (CLI stdin/stdout or an LLM
API) and the Wire (`{version,kind,job_id,seq,ts,type,trust,data}`). The core
NEVER talks to Claude/Pi/OpenSwarm directly — only to the Wire. Keep
DELEGATED-CLI (shape a, cheapest: already governed from outside) and NATIVE-
PROVIDER (shape b, tightest: core owns the loop) as two entry points to the
SAME Wire, so 'the interface' vs 'the wire' stay distinct contracts.
