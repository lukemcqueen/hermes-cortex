# MCP DeepSeek Adversarial Review Server

**Pattern**: Standard MCP stdio server wrapping DeepSeek's adversarial review capability via OpenRouter. Agents call it as a tool without ever handling the API key.

---

## What it does

Provides three MCP tools:

| Tool | Purpose |
|---|---|
| `review_experimental_plan` | Send a memo, plan, or results summary to DeepSeek for harsh-but-constructive adversarial review |
| `ask_deepseek` | Generic research question (math proofs, lit checks, brainstorming) |
| `list_available_models` | List current DeepSeek model slugs on OpenRouter |

The agent never sees the `OPENROUTER_API_KEY`. The server process reads `.env` directly at startup.

---

## Files (in the project repo)

```
.pi/mcp.json                             # Project-level MCP config (overrides user-level)
scripts/mcp_deepseek_server.py           # The MCP stdio server
scripts/get_openrouter_key.sh            # Shell helper: sources .env, emits key
```

## .pi/mcp.json (project override)

Keep this minimal — NO secrets:

```json
{
  "mcpServers": {
    "deepseek": {
      "enabled": true,
      "exposure": "direct"
    }
  }
}
```

The full server definition lives in `~/.pi/agent/mcp.json` (user-level, outside the project). If you want the server scoped to one project only, you can put the full definition in the project `.pi/mcp.json` and accept that the key is visible in the file.

## Server behavior

1. **Startup**: reads `.env` directly (not via env var injection) to get `OPENROUTER_API_KEY`
2. **Request**: builds the OpenRouter payload with the key in-memory
3. **Response**: returns DeepSeek's markdown review as `TextContent`

## Agent usage

```
mcp__deepseek__review_experimental_plan(
    plan_text="<your full memo here>",
    model="deepseek/deepseek-chat",   # or deepseek/deepseek-r1 for reasoning mode
    focus_questions="Optional: what to focus on"
)
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Missing Authentication header` | Server started before `.env` was readable | `/mcp reconnect deepseek` or `/reload` |
| `429 rate limited` | Upstream provider throttling | Retry with a different model slug (e.g., `deepseek-chat-v3.1` instead of `deepseek-chat`) |
| Server not in `/mcp` list | Project not trusted | Start `pi` from project root and accept trust prompt |
| Timeout after 60s | Default Pi MCP timeout | Add `"timeout": 300` in `~/.pi/agent/mcp.json` server entry |

## Model slugs (OpenRouter Oct 2025)

Preferred:
- `deepseek/deepseek-chat` — fast, cheap, good for adversarial reviews
- `deepseek/deepseek-r1` — reasoning mode, slower, better for deep analysis

Avoid:
- `deepseek/deepseek-r1-pro` — not a valid OpenRouter slug (returns 400)

Full list: call `mcp__deepseek__list_available_models` in-session.

## Rules

- **Never hardcode the key.** Always read from `.env` or a protected env var.
- **Never log the key.** Sanitize before printing any API response.
- **User-level `~/.pi/agent/mcp.json` is the preferred location** for the server definition with the key.
- **Project `.pi/mcp.json` should only contain overrides** (`enabled`, `exposure`) — no secrets.
