# MCP DeepSeek Adversarial Review Server

**Pattern**: Standard MCP stdio server wrapping DeepSeek's adversarial review capability via OpenRouter. Agents call it as a tool without ever handling the API key.

> **The tool is named `review`.** It was `review_experimental_plan`, which is narrower than
> what it does — it reviews a memo, a plan, or a results summary. The rename is **automated**
> (see [Keeping the name current](#keeping-the-name-current-automated)); do not hand-edit the
> server, and do not copy its source into `hermes-cortex`.

---

## What it does

Provides three MCP tools:

| Tool | Purpose |
|---|---|
| `review` | Send a memo, plan, or results summary to DeepSeek for harsh-but-constructive adversarial review |
| `ask_deepseek` | Generic research question (math proofs, lit checks, brainstorming) |
| `list_available_models` | List current DeepSeek model slugs on OpenRouter |

The agent never sees the `OPENROUTER_API_KEY`. The server process reads `.env` directly at startup.

---

## Files (in the project repo)

```
.pi/mcp.json                             # Project-level MCP config (overrides user-level)
scripts/util/mcp_deepseek_server.py      # The MCP stdio server
```

**The server lives in a PRODUCT repo, not in `hermes-cortex`.** `ops/install/harnesses/pi/ADDON-deepseek-mcp.md` names the canonical path and forbids copying it here — a second copy of a server is the phantom this tree exists to prevent.

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
mcp__deepseek__review(
    plan_text="<your full memo here>",
    model="deepseek/deepseek-v4-pro",   # the default; see below
    focus_questions="Optional: what to focus on"
)
```

## Default model

**`deepseek/deepseek-v4-pro`.** A cheap judge is a weaker judge, and this server exists to attack a plan before it is built — the review is the whole point, so the default does not trade depth for cost. Pass `model=` explicitly to choose something else for a one-off.

## Keeping the name current (automated)

The rename is **not** a documented hand procedure — it is the Pi MCP manager plus a doctor
check, so a host still on the old name is detected and fixed rather than re-derived by each
agent:

```bash
# Detect only; exit 1 when this host still exposes the old name:
bash ~/hermes-cortex/ops/scripts/install/install-pi-mcp.sh --check-tools

# Do it (copies the server file to <name>.bak first; idempotent, so a second run is a no-op):
bash ~/hermes-cortex/ops/scripts/install/install-pi-mcp.sh --fix-tools

# Then reconnect the client so it picks up the new tool name:
pi mcp list | grep deepseek        # expect the tool named `review`
```

`cortex-doctor.py` reports `DeepSeek MCP tool name`, and its auto-fix runs `--fix-tools`.
`install-pi-mcp.sh` is the ONE file that owns `~/.pi/agent/mcp.json`, so the rename lives
there rather than in a bespoke script — one implementation owns the config, and the check
cannot drift from what a re-install does. Design
notes, so the behaviour is not surprising:

- **The server is resolved from the host's MCP config**, never from a hardcoded path — the path
  differs per host and the config already records the real one.
- **Absence is a PASS.** The entry is host-optional; a host that never registered it is not
  broken, and a check that fails on a healthy host teaches readers to ignore it.
- **Only the exact token is renamed.** A longer identifier that merely starts with the old name
  (`review_experimental_planning`) is left alone, so a substring replace cannot corrupt a
  differently-named tool.
- **Backup first, dry-run by default, idempotent.**

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Missing Authentication header` | Server started before `.env` was readable | `/mcp reconnect deepseek` or `/reload` |
| `429 rate limited` | Upstream provider throttling | Retry with a different model slug (e.g. `deepseek/deepseek-v4-flash`) |
| Server not in `/mcp` list | Project not trusted | Start `pi` from project root and accept trust prompt |
| Timeout after 60s | Default Pi MCP timeout | Add `"timeout": 300` in `~/.pi/agent/mcp.json` server entry |
| Tool called by its old name | Host has not run the rename yet | `bash ~/hermes-cortex/ops/scripts/install/install-pi-mcp.sh --fix-tools` |

## Model slugs

Default: `deepseek/deepseek-v4-pro`.

`deepseek/deepseek-v4-flash` is the cheap tier where a shallow pass is genuinely enough.

**Do not hardcode a slug list here** — it rots. Call `mcp__deepseek__list_available_models` in-session for the slugs OpenRouter is actually serving.

## Rules

- **Never hardcode the key.** Always read from `.env` or a protected env var.
- **Never log the key.** Sanitize before printing any API response.
- **User-level `~/.pi/agent/mcp.json` is the preferred location** for the server definition with the key.
- **Project `.pi/mcp.json` should only contain overrides** (`enabled`, `exposure`) — no secrets.
- **Never copy the server into `hermes-cortex`** — it lives in a product repo and calls a paid API. Moving it is an owner decision.
