# bus_send Silent Failure — Fleet Agent Diagnostic (2026-07-21)

## Symptom

Agents consume UPDATE_REQUESTs from the shared bus (state → processing → archived) but **never send back UPDATE_RESULT** to inbox_moses. The agent's handler logs "Failed to send UPDATE_RESULT" on its end, but the orchestrator sees nothing.

## The Pattern

| Agent | Can READ from bus? | Can SEND to bus? | Config fix needed |
|-------|-------------------|-------------------|-------------------|
| Esther (before fix) | ❌ Wrong queue | ✅ Once pointed right | CORTEX_BUS_URL → shared bus |
| Esther (after fix) | ✅ | ✅ | — |
| Joseph | ✅ | ✅ (after confirming) | AGENT_NAME missing? |
| Gisu | ✅ | ✅ (after confirming) | AGENT_NAME missing? |
| Kustos | ✅ | ✅ (after confirming) | AGENT_NAME=kustos was missing |
| Moses | ✅ | ✅ | — |

## Resolution (End of Session)

All agents that had `bus_send` returning `None` were confirmed WORKING after fixing their `cortex-bus.conf`:

- **Kustos**: missing `AGENT_NAME=kustos` — was polling `inbox_cisnet02`. Fixed by adding AGENT_NAME.
- **Joseph**: `bus_send` returned msg_id successfully — no config fix needed, was working all along.
- **Gisu**: `bus_send` returned msg_id successfully — confirmed working. Config had quoted values (`"gisu:..."`) but `_read_config` strips quotes.
- **Esther**: Bus was configured but handler was hitting a local PGMQ instead of the shared bus. After reconfiguring CORTEX_BUS_URL to `https://example.com:13004`, messages were consumed but still got stuck in `processing` (handler crash pattern, not send failure). Moved to DLQ after 3 retries.

## Key Diagnostic

`bus_send()` and `bus_read()` use identical infrastructure:
- Same `_bus_post()` function with same URL, auth, retry + fallback
- Same `_get_auth_header()` for auth
- Same `BUS_URL` and `BUS_FALLBACK_URL`

If `bus_read()` succeeds but `bus_send()` fails, the issue is NOT:
- Network connectivity (read works)
- URL resolution (read works)  
- Auth token validity (read works)
- Basic auth credentials (read works)

Possible root causes when read works but send doesn't:

1. **Local PGMQ running on agent** — agent has its OWN Postgres running with PGMQ at `localhost:13004`. The `cortex-bus.conf` points to `https://example.com:13004` for READ (nginx proxy), but something in the stack resolves SEND to the local PGMQ instead. Check: does the agent have its own `gbrain-postgres` Docker container?

2. **CORTEX_BASIC_AUTH env var override** — `cortex_bus.py` line 39 reads `CORTEX_BUS_AUTH` from env FIRST before falling back to config file. If an env var has a stale or wrong auth value, it overrides the config file. Check: `echo $CORTEX_BUS_AUTH` on the agent.

3. **Send endpoint specific** — PGMQ API `/api/pgmq/send` may have different auth requirements than `/api/pgmq/read`. Check: can the agent send via curl on the command line?

## Diagnostic Command

```bash
cd ~/hermes-cortex && python3 -c "
from ops.scripts.lib.cortex_bus import bus_send, bus_read, BUS_URL, CORTEX_BUS_AUTH, CORTEX_BUS_TOKEN
print(f'URL: {BUS_URL}')
print(f'Has auth: {bool(CORTEX_BUS_AUTH)}')
print(f'Has token: {bool(CORTEX_BUS_TOKEN)}')
r = bus_send('inbox_moses', {'from':'test','subject':'TEST','body':{},'correlation_id':'diag-1'})
print(f'Send result: {r}')
r2 = bus_read('inbox_moses')
print(f'Read result: msg_id={r2.get(\"msg_id\",\"?\") if r2 else \"None\"}')
"
```

## Tested Working Config (Moses)

```ini
CORTEX_BUS_URL=https://example.com:13004
CORTEX_BUS_FALLBACK_URL=https://example.com:14004
CORTEX_BASIC_AUTH=moses:your-password
```

## Critical Config Fields

### AGENT_NAME (must be present)

The handler determines which queue to poll from `AGENT_NAME` in `cortex-bus.conf`:

```ini
AGENT_NAME=esther    # → polls inbox_esther
AGENT_NAME=kustos    # → polls inbox_kustos
```

**If unset, falls back to hostname** (`socket.gethostname()`), which can be
wrong (e.g. `inbox_cisnet02` instead of `inbox_kustos`). **This was the root
cause for Kustos.** Every agent must have `AGENT_NAME=<name>` in their config.

### CORTEX_BASIC_AUTH vs CORTEX_BUS_AUTH

The library supports both key names:
- `CORTEX_BASIC_AUTH` (read first) — older name, used in fleet setup
- `CORTEX_BUS_AUTH` (fallback) — newer name, consistent naming

Set `CORTEX_BASIC_AUTH=<agent>:<password>`. Using another agent's credentials
(e.g. Esther using `moses:...`) works for bus operations but is fragile.

### Quote Stripping

`_read_config()` strips matching single/double quotes around config values
(fix committed by Gisu, `71e869d`). Both forms work:

```ini
CORTEX_BUS_URL=https://example.com:13004    # unquoted
CORTEX_BUS_URL="https://example.com:13004"  # quoted (stripped)
```

### Env Var Override Trap

`_read_config()` is a **fallback** — env vars take priority:

```python
BUS_URL = os.environ.get("CORTEX_BUS_URL", "") or _read_config("CORTEX_BUS_URL")
```

If a systemd service file, Docker env, or shell profile sets `CORTEX_BUS_URL`, it
overrides the config file. This has been the root cause of multiple bus
connectivity issues on fleet agents.
