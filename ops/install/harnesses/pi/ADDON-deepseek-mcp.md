# Optional add-on: a host-local DeepSeek review MCP server (Pi)

**Audience: a Pi agent (or any MCP client) that sees a `deepseek` entry in
`~/.pi/agent/mcp.json` and wonders whether it is a cortex server.** It is not.

Kept in its own file on purpose: `../pi/IMPLEMENT.md` is the cortex wiring guide, and
this is the opposite thing — a server the fleet neither installs nor audits, which an
agent must be able to recognise as *not ours* rather than try to "repair" with
`install-pi-mcp.sh`. Related: [`../../../docs/external/external-services.md`](../../../docs/external/external-services.md).

---

## What it is

| | |
|---|---|
| **Tools** | `review_experimental_plan`, `ask_deepseek`, `list_available_models` |
| **What it does** | asks DeepSeek to attack a plan before it is built (adversarial review), over OpenRouter |
| **Where its source lives** | a PRODUCT repo, not this one: `~/Developer/AI/steadfaste-s1-model/scripts/util/mcp_deepseek_server.py` |
| **Credential** | `OPENROUTER_API_KEY` — from the env, or a `./.env` beside the server |
| **Registered in** | `~/.pi/agent/mcp.json`, one entry named `deepseek`, next to the five cortex entries |
| **Default model** | `deepseek/deepseek-chat-v3` (OpenRouter) |

**NOT part of the cortex suite, and NOT installed by `install-pi-mcp.sh`.** Some hosts
register it by hand; others do not. Neither state is a fault.

## Registration shape

The same file the cortex servers use (Pi reads MCP servers from its own config):

```json
{
  "mcpServers": {
    "deepseek": {
      "command": "<an interpreter that can `import mcp`>",
      "args": ["~/Developer/AI/steadfaste-s1-model/scripts/util/mcp_deepseek_server.py"],
      "timeout": 300,
      "description": "DeepSeek adversarial review via OpenRouter",
      "exposure": "direct"
    }
  }
}
```

**The interpreter is the failure mode, not the entry.** A config naming an interpreter
without the `mcp` package starts the server DEAD while the file still looks complete —
the same trap `install-pi-mcp.sh` guards against. Resolve it by CAPABILITY, never by a
path you happen to have:

```bash
bash ~/hermes-cortex/ops/scripts/lib/python-with-module.sh --print mcp
# exit 3 = no interpreter on this host can import it; install it and re-run
```

## Verify, then leave it alone

```bash
pi mcp list | grep deepseek      # expected: connected, with its 3 tools
```

- `install-pi-mcp.sh --remove` strips the **cortex** servers only: run against a
  scratch config holding a `deepseek` entry, the surviving set was
  `['deepseek', 'user-owned']` (measured 2026-10-12, rc=0). A host keeps it across
  re-runs of the installer.
- `audit-pi-integration.sh` requires the five **cortex** servers by name and applies
  its `AGENT_NAME` identity rule **only to those**. A host-local entry like this one is
  reported as *present, NOT audited here*; its command and script are still checked
  (a broken path is a real defect). So a host WITHOUT it is a PASS, and a host WITH it
  is a PASS too.
- **Do not "fix" it by copying its source into `hermes-cortex/`.** Moving it here is an
  owner decision (it lives in a product repo and calls a paid API), and a second copy of
  a server is exactly the phantom this tree exists to prevent.

Evidence for both claims: `docs/evidence/pi-audit-foreign-server-2026-10-12.txt`,
whose commands (`tests/test_pi_integration_foreign_server.py`, the installer scratch
run, the A4 gates) are re-runnable as shown.
