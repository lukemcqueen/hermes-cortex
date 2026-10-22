# Optional add-on: Telegram gateway for Pi (hc / steadfaste)

**Audience:** an agent setting up a Pi backend on the cortex-gateway daemon,
answering a Telegram bot distinct from the Hermes bot. This is the macOS
(launchd) walkthrough; Linux/systemd uses the same `gateway.yaml` and env vars
with `docs/templates/cortex-gateway.service` instead.

Kept in its own file on purpose: `../pi/IMPLEMENT.md` §7 covers the adapter
contract; this doc covers the **host-specific wiring** (bot token, env, plist,
launchd pitfalls) that is not part of the generic contract.

---

## What it is

| | |
|---|---|
| **Daemon** | `cortex_gateway/daemon.py` (standalone, zero Hermes import) |
| **Transport** | Telegram long-poll (`getUpdates`) |
| **Backend** | Pi (`kind: command` — one `pi` invocation per turn) |
| **Bot** | `@TitusPiBot` (distinct from the Hermes bot) |
| **Service name** | `com.steadfaste.gateway` |
| **Config** | `~/.hermes-cortex/gateway.yaml` |
| **Env** | `~/hermes-cortex/.env` (same canonical file as everything else) |

Both gateways run in parallel: Hermes (`ai.hermes.gateway`) owns one bot token,
steadfaste (`com.steadfaste.gateway`) owns another. Telegram allows one poller
per bot, so there is no 409 conflict.

---

## 1. Prerequisites

- Pi installed (`~/.pi/agent/bin/pi` exists and answers)
- `psycopg` installed for the Python that runs the daemon:
  ```bash
  /usr/bin/python3 -m pip install psycopg[binary]
  ```
- Postgres running locally (mycortex on `127.0.0.1:15432`) — the advisory lock
  lives there, and the gateway needs `CORTEX_BUS_PG_*` creds to reach it

---

## 2. Env vars to add to `~/hermes-cortex/.env`

```bash
# Bot token — NEVER this repo; keep it outside
PI_TELEGRAM_BOT_TOKEN=<read from ~/.titus_pi_bot_telegram.txt>

# Same allowlist / home channel names Hermes uses
TELEGRAM_ALLOWED_USERS=1270130526
TELEGRAM_HOME_CHANNEL=1270130526

# HMAC signing secret for bus envelopes
GATEWAY_SECRET=$(openssl rand -hex 32)

# Telegram API base
TELEGRAM_API_BASE=https://api.telegram.org

# Postgres for advisory locks (same instance as mycortex)
CORTEX_BUS_PG_HOST=127.0.0.1
CORTEX_BUS_PG_PORT=15432
CORTEX_BUS_PG_DB=mycortex
CORTEX_BUS_PG_USER=mycortex
CORTEX_BUS_PG_PASS=<same as MYCORTEX_PG_PASSWORD>
```

The daemon reads `PI_TELEGRAM_BOT_TOKEN` because `gateway.yaml` names it in
`bots[].token_ref` — this keeps the Hermes token (`TELEGRAM_BOT_TOKEN`) untouched.

---

## 3. `gateway.yaml`

```json
{
  "bus_url": "https://realgospelmessage.com:13004",
  "backends": [
    {
      "name": "pi",
      "kind": "command",
      "command": ["/Users/luke/.pi/agent/bin/pi"],
      "output": "raw",
      "timeout_s": 300,
      "reply_mode": "sync",
      "stream": true,
      "model": "openrouter/deepseek/deepseek-flash-latest",
      "model_args": ["--model", "{model}"],
      "session": "per_chat",
      "session_args": ["--session-id", "{session_id}"],
      "env": {
        "CORTEX_SESSION_HARNESS": "pi",
        "CORTEX_SESSION_KEY": "{session_id}"
      },
      "commands": {
        "compact": {
          "argv": ["/usr/bin/python3", "/Users/luke/.hermes-cortex/scripts/cortex_gateway/pi_control.py",
                   "compact", "--session-id", "{session_id}", "--model", "{model}"],
          "timeout_s": 420
        },
        "check_model": {
          "argv": ["/usr/bin/python3", "/Users/luke/.hermes-cortex/scripts/cortex_gateway/pi_control.py",
                   "check-model", "{model}"],
          "timeout_s": 30
        }
      },
      "capabilities": ["code", "review"]
    }
  ],
  "bots": [
    {
      "token_ref": "PI_TELEGRAM_BOT_TOKEN",
      "channel": "telegram",
      "initial_offset": 0,
      "routing": {
        "default": "pi",
        "overrides": {}
      }
    }
  ],
  "routing": {
    "default": "pi",
    "overrides": {}
  }
}
```

Place at `~/.hermes-cortex/gateway.yaml` (outside the repo).

`stream: true` turns on **live streaming**: while the agent works, Telegram shows a
"typing…" indicator and the single reply message is edited in place as output
arrives (throttled — never a message per token). It is the standard for every
`kind: command` coding agent (pi, codex, claude-code, opencode, grok): the flag is
read generically by the command backend, so any CLI agent with the same one field
gets the same behavior. Any plain command agent that does **not** stream to stdout
progressively should leave it off (`false`/omitted) to avoid a stream that never
advances until the process exits.

---

## 4. Launchd plist (`com.steadfaste.gateway`)

Copy and edit `docs/templates/com.hermes.cortex-gateway.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist ...>
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.steadfaste.gateway</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-lc</string>
        <string>set -a; . "$HOME/hermes-cortex/.env"; set +a; exec /usr/bin/python3 "$HOME/.hermes-cortex/scripts/cortex_gateway/daemon.py" --config "$HOME/.hermes-cortex/gateway.yaml"</string>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>WorkingDirectory</key>
    <string>/Users/luke/.hermes-cortex/scripts</string>

    <key>RunAtLoad</key>
    <true/>

    <!-- CRITICAL: SuccessfulExit=false so /restart works.
         The daemon exits 75 (EX_TEMPFAIL) on /restart; launchd
         relaunches only after a NON-zero exit with this key. -->
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>15</integer>

    <key>StandardOutPath</key>
    <string>/Users/luke/Library/Logs/com.steadfaste.gateway.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/luke/Library/Logs/com.steadfaste.gateway.log</string>
</dict>
</plist>
```

Install:
```bash
cp com.steadfaste.gateway.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.steadfaste.gateway.plist
```

---

## 5. The `/restart` launchd pitfall

**Wrong:** `CrashedOrAbnormalExit` — this is not a real launchd key. A dict of
unrecognised keys gives launchd no restart condition at all, so `/restart` exits
the process and it stays down.

**Right:** `SuccessfulExit=false` — launchd relaunches after a non-zero exit.
The daemon detects launchd supervision (`launchctl list` contains our PID), then
uses exit code 75 (`EX_TEMPFAIL`) for `/restart` instead of the exit-0 that
systemd's `Restart=always` expects.

If `/restart` replies `"⚠️ This gateway is not running under systemd..."`, the
plist's `KeepAlive` is wrong. Fix it, `launchctl unload`, `launchctl load`, retry.

---

## 6. Verify

```bash
# Service running?
launchctl list com.steadfaste.gateway | grep PID

# Bot reachable?
curl -s "https://api.telegram.org/bot<PI_TELEGRAM_BOT_TOKEN>/getMe"

# Config valid? (dry-run: builds gateway, does not poll)
cd ~/.hermes-cortex/scripts && \
  set -a && source ~/hermes-cortex/.env && set +a && \
  python3 -c "from cortex_gateway.daemon import build_gateway; \
              gw = build_gateway(Path('~/.hermes-cortex/gateway.yaml')); \
              print('OK:', list(gw.backends.keys()))"

# Send /status then /restart to the bot on Telegram
```

---

## 7. Related docs

- `IMPLEMENT.md` §7 — adapter contract (how the gateway drives pi)
- `ADDON-deepseek-mcp.md` — optional adversarial-review MCP server
- `docs/design/cortex-gateway.md` — architecture and build slices
- `docs/templates/com.hermes.cortex-gateway.plist` — upstream template (check for drift)
