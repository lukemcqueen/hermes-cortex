---
name: hermes-gateway-operations
version: 1.0.0
description: >-
  Diagnose, configure, and maintain Hermes messaging gateway platforms
  (Telegram, Discord, WhatsApp, etc.). Covers connectivity troubleshooting,
  secret/token setup, gateway state inspection, and common failure patterns.
---

# Hermes Gateway Operations

Diagnostic and maintenance procedures for the Hermes messaging gateway.

## When to load

- User reports "messages not sending" on any platform
- Gateway is disconnected or repeatedly reconnecting
- Need to set up a new platform (Telegram bot token, Discord token, etc.)
- Debugging `.env` configuration for gateway platforms

## Diagnostic Path (Telegram example)

Always follow this sequence — each step feeds the next:

```
1. gateway_state.json    → platform state ("disconnected" / "connected")
2. gateway.log           → error message ("No bot token configured")
3. .env                  → check TELEGRAM_BOT_TOKEN exists
4. config.yaml           → check platform_plugins and telegram
```

### Step 1 — Inspect gateway state

```bash
cat ~/.hermes/state/gateway_state.json 2>/dev/null
# {"platforms": {"telegram": {"status": "connected", "last_seen": "..."}}}
```

`"disconnected"` + a `last_seen` far in the past = the platform dropped and
isn't reconnecting. `"connected"` but messages not arriving = delivery-side
problem (see Step 5).

### Step 2 — Read the gateway log

```bash
tail -50 ~/.hermes/logs/gateway.log
```

Typical failure lines:
- `No bot token configured for platform telegram` → token missing
- `401 Unauthorized from Telegram API` → token wrong/revoked
- `Connection reset by peer` → transient network; check reconnect behavior

### Step 3 — Verify the token

```bash
# Does the var exist?
grep -c "TELEGRAM_BOT_TOKEN" ~/.hermes/.env

# Is it set in the environment?
printenv TELEGRAM_BOT_TOKEN >/dev/null && echo "set" || echo "UNSET"

# Is the token VALID? (never print it)
curl -s "https://api.telegram.org/bot$(cat ~/.hermes/.env | grep TELEGRAM_BOT_TOKEN | cut -d= -f2)/getMe" | head -c 200
```

> **Never print secrets.** Read tokens via `$(cat <file>)` or `grep | cut`
> inside the command — never pass them as literal strings.

### Step 4 — Check config.yaml

```bash
grep -A5 "telegram:" ~/.hermes/config.yaml
```

Confirm the platform is enabled in `platform_plugins` and no stale config
(e.g. old bot name, wrong chat ID).

### Step 5 — Delivery-side check (connected but nothing arrives)

If the gateway is connected but messages don't reach the user:
- Confirm the destination chat ID is correct
- Check `deliver` targets on the failing cron/job
- Verify the platform session didn't expire (re-auth if needed)

## Restarting to load new code — and verifying it actually happened

The gateway **holds the MCP servers it spawned**, so new governance/enforcer code
is not loaded until the gateway restarts. Two independent failure modes:

1. **Restarting from inside the gateway is blocked by design — and the block matches the COMMAND,
   so deferring it is not an escape.** A restart issued from inside a Hermes session (a tool call) is
   refused because the gateway would SIGTERM the command before it completed. Wrapping it to run
   later (`systemd-run --on-active`, `nohup … &`, `at`) is refused as well: the guard inspects the
   command and the script it references, not merely the timing, and attempting the workaround IS the
   violation. Restart from a **separate shell**, or hand the operator the gateway's own `/restart`
   command — which exits with the code its supervisor relaunches on, so the service comes back by
   design and announces itself. Name which one you are asking for, and hand it over once; do not
   loop-retry.
2. **A restart can report success and still not land.** Verify; do not assume:

```bash
systemctl --user show hermes-gateway.service -p MainPID -p ExecMainStartTimestamp -p NRestarts
```

`MainPID` and `ExecMainStartTimestamp` **must change**. Observed failure: an
attempt that left both unchanged at the previous start time — the unit never
re-activated, so the MCP child still held pre-change code while everything
*looked* restarted.

Then confirm the child post-dates the deploy:

```bash
ps -o lstart= -p $(pgrep -f loop-governance/loop-gov-mcp.py)
date -r ~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py '+%e %H:%M:%S'
```

An older child start is a HINT that the old code is live — but mtime alone cannot settle it: the
restart command's own machinery (a dogfood/doctor pass) RE-DEPLOYS, and a deploy rewrites files
whose bytes did not change, so the mtime moves while a current process reads as stale. Settle it by
CONTENT — a startup hash stamp the process writes, or a witness only the new revision can produce —
and never chase the resulting warning with another restart. Rule and mechanism:
`deploy-load-verification`.

Note: a config value in `~/hermes-cortex/.env` does **not** need a restart once
the gate's own resolver is deployed (it re-reads per call); only the code does.

### A restart that preserves sessions is INVISIBLE — announce it, and tell the agent

The only message about a restart is sent by the process that then exits; nothing
follows it. So a human in the chat cannot tell the restart happened, and the agent
cannot tell them either: sessions survive a gateway restart (starting fresh is
`/new`), so an agent asked "did you restart?" answers from its own memory —
"no, I still have our context" — which is true of the SESSION, false about the
gateway, and the only answer available. Three things fix that, and the third is
the one usually missed:

1. **The restart command's reply states what happens to the CONVERSATION.**
   "restart" reads like "fresh start"; a session that carries over otherwise looks
   like nothing happened.
2. **The NEW process announces itself at startup, before it serves anything**, in the
   operator's wording, verbatim: `♻ Gateway restarted successfully. Your session
   continues.` Keep that phrasing — it answers both questions a restart raises (did it
   work, did I lose the conversation) in one line, and a longer invented variant is not
   what the operator wants here. Persist a per-chat marker BEFORE sending the restart
   reply — the process that writes the marker is the one that exits, so in-memory state
   cannot carry it. Consume the marker on the first turn, so the human is told once and
   not on every later reply. If the startup send fails, LEAVE the marker and let the
   first reply carry the confirmation: a transient send failure must not lose the news.
3. **Hand the AGENT the same fact on its first prompt after the restart** (a
   `[system]` note prepended to the turn). Announcing to the human alone leaves the
   agent still answering "no" — the contradiction the human will notice.

Prove a restart with the unit, not with the chat:

```bash
systemctl --user show <unit>.service -p NRestarts -p MainPID -p ExecMainStartTimestamp
```

A NEW `MainPID` plus start timestamp is the proof. `NRestarts` increments only for a
**policy** restart (`Restart=` firing) — an operator-issued `systemctl restart` does
not increment it, so a changing `NRestarts` is evidence the unit restarted ITSELF.

- **`Restart=always` is required for restart-on-clean-exit**, the pattern where a
  service asks systemd to bring it back by exiting on purpose: `Restart=on-failure`
  does NOT start the unit again after `exit(0)`, so the exit is a plain stop and the
  bot stays down. Check the policy before trusting the mechanism.
- **The exit code is the SUPERVISOR's, never a constant — derive it, and refuse when
  nothing would bring the process back.** systemd (`Restart=always`) relaunches on any
  exit, so `os._exit(0)` is right; a launchd job whose plist says `SuccessfulExit=false`
  is relaunched only after a NON-zero exit, so the same handler must exit `75`
  (EX_TEMPFAIL) on macOS or it PARKS the service silently. Prove who owns the process
  first — `launchctl list`'s PID column showing OUR pid is the test, because
  `XPC_SERVICE_NAME` is inherited by children exactly as systemd's `INVOCATION_ID` is —
  then read the job's own plist for the relaunch condition and exit with the code it
  wants. When no recognised condition covers a deliberate exit, refuse and name the
  plist fix instead of exiting into silence. Conditions and the full exit-code table:
  `macos-service-management`.
- **Probing this with a throwaway unit: end the probe with
  `systemctl --user stop <unit>` and exit 0.** Under `Restart=always`, a probe that
  exits non-zero restarts itself in a loop — it floods the journal and, if it also
  touches live state, does so repeatedly. Confirm the unit is gone afterwards
  (`systemctl --user list-units --all | grep <name>`).

## A non-Hermes backend is a SEPARATE runtime, not a Hermes session

A backend of `kind: command` (a CLI coding agent) is a distinct process with its
own tooling: it inherits **none** of a Hermes session's memory, skills, or
governance. "Agent X has no memory" is therefore a property of that backend's
OWN integration layer, never of the host — establish where its memory comes from
before touching anything shared:

| Backend | Memory comes from |
|---|---|
| Hermes session | the `mycortex-mem` memory-provider plugin, in-process |
| command/CLI agent | its own MCP server or extension, spawned by the agent CLI |

`hermes mcp list` does not list plugin-provided stores, so its absence proves
nothing about a Hermes session; a CLI agent's tools appear in ITS agent config
(its own `mcp.json`/settings), not in `config.yaml`.

### One service-hosted agent reports a store unreachable, a sibling works

Compare the two SERVING UNITS' sandbox flags before blaming the store —
hardening is invisible in the agent's own output, and the store's availability
check often swallows the real exception:

```bash
systemctl --user show <failing>.service -p NoNewPrivileges -p PrivateTmp
systemctl --user show <working>.service -p NoNewPrivileges -p PrivateTmp
```

`NoNewPrivileges=true` refuses `sg`/`newgrp` setgid **even when the process
already holds the target group**, which breaks any store whose only access path
is `sg docker -c "docker exec …"`. Reproduce faithfully with
`setpriv --no-new-privs -- <cmd>` — it keeps the real supplementary groups,
whereas `systemd-run` drops them and fails for the wrong reason. Fix by giving
the store a direct `docker exec` path when the group is already held; never by
dropping the hardening flag. Mechanism and store-specific fix: `psql-automation`.

### Slash commands are the GATEWAY's, never the agent's

When a `kind: command` backend (a CLI coding agent) serves a chat, the built-in slash
commands belong to the GATEWAY: such a backend handles `/new`, `/model`, `/compact`,
`/restart` only in its interactive/RPC surface, so forwarded as prompt prose they become
ordinary conversation — a `/new` is answered politely while every bit of context stays.
Intercept them in the gateway's command dispatcher and never pass them through
(backend mechanics: `pi-coding-agent`).

- **Each command needs a defined contract, not just a route.** `/new` starts a fresh
  session; `/model` persists the override per chat — a stateless prompt wrapper has
  nowhere to keep it, so the GATEWAY owns a small chat→model store, mode 0600 (a chat id
  is personal data); `/compact` reports what it reclaimed, and "nothing to compact" for a
  session too small; `/restart` exits WITH THE CODE ITS SUPERVISOR RELAUNCHES ON (`0`
  under `Restart=always`, `75` under launchd's `SuccessfulExit=false`) so the service
  comes back by design, and the new process announces itself (above). A refusal must name
  the half that is missing — "not running under systemd" is a dead end on a host that IS
  supervised, by launchd.
- **Design for the EMPTY chat.** Commands run on chats with no conversation yet, where a
  backend's session operations hang or refuse (compact on a transcript that does not exist
  never answers). Probe state first and answer with the specific condition — "this chat has
  no conversation yet" — never a generic failure.
- **A control timeout must cover a real turn plus the operation.** Compacting a large
  session measured ~1m46s; a 30s deadline reports a healthy backend as broken.
- **Test parity with a STUB transport and an echoing backend** (`/bin/echo` so the reply
  body IS the argv). A probe that polls with the real bot token starts a second poller and
  steals the live channel's messages (409); echoing is what lets the assertion check the
  ARGV the gateway produced — model declared exactly once, no duplicate `--model`.

### Inline menus (buttons) for gateway commands

A slash command that picks a VALUE (a model, a voice, a page) is better served by a menu than a
free-text argument — but build it on the gateway's plumbing, not beside it:

- **Read the transport before building the UI.** The button markup, edit-in-place and callback
  routing may already exist. Feature-detect each and degrade to the text form when a platform
  lacks it, rather than erroring — the command stays usable without buttons.
- **Carry an INDEX in the callback, never the value.** `callback_data` is capped (64 bytes on
  Telegram) while a real id runs 40+; re-render the menu from CURRENT state on every press, so a
  stale button can only ever be out of range. Answer it — never apply a value the menu did not
  show.
- **Tick the value IN FORCE, not just an override** — the backend default is what most chats are
  running, so ticking only overrides leaves every menu unticked; offer the reset entry only when
  an override exists.
- **Edit in place** — one message per menu, not one per press — and ANSWER every callback so the
  client's spinner clears. Consume your own callbacks so a press never reaches the backend as
  prompt prose.
- **The list is gateway-owned config.** A backend's raw catalogue is hundreds of entries and a
  menu of hundreds is worse than a command: curate it in the gateway config so the operator can
  edit it. Warn on stderr for unusable entries ("N blank entries ignored (M usable)") instead of
  silently serving a shorter menu.
- **Enabling the menu is PER-HOST work — ship a deployable enabler, not a procedure.** The
  list lives in each host's own gateway config, so every host needs a config step and a
  restart before its menu appears. Make that a script (portable: stdlib only, no YAML
  dependency, since the gateway reads its config with `json.loads`) that derives the list from
  that host's own backend catalogue, MERGES only the list key — every other key preserved,
  idempotent — and offers a `--check` sweep. Then REGISTER it in the deploy map: a helper meant
  for every host that is not registered exists only in the repo, and tests that load it by repo
  path stay green while hosts never receive it. Give "cannot derive the list here" its own exit
  code rather than reporting an empty catalogue, and read the written config back to confirm
  the other keys survived (a shape mismatch between the producer and the writer silently
  writes an empty list and reports success).
- **Warn when the backend cannot TAKE the value at all.** A shim-style backend declares no
  value flag, so a selection is stored and never applied: the menu looks live and does nothing.
  At startup, check whether any backend declares the placeholder that consumes the selection
  and say so on stderr instead of serving a dead menu — the host's operator cannot otherwise
  tell a working menu from a decorative one.
- **Test the menu through the stub transport**: a callback arrives as its own KIND with the data
  in the body. Assert the first page, the tick, a page step, a stale out-of-range press, and that
  a chat with no configured list still gets the text form.

Concrete shapes — paths, the callback envelope, callback-data encoding, and the test cases:
`references/inline-menus.md`.

## Adding a New Platform

1. Obtain the token/secret for the platform (Telegram bot token from
   @BotFather, Discord bot token, etc.)
2. Add to `~/.hermes/.env` (never commit the file)
3. Enable in `config.yaml` → `platform_plugins`
4. Restart the gateway
5. Verify `gateway_state.json` shows `"connected"` and send a test message

## Enabling the decoupled cortex-gateway (a CLI-agent backend)

The repo ships a standalone `cortex-gateway` unit (`docs/templates/cortex-gateway.service`)
that answers a messaging bot with a pluggable backend, including a `kind: command` CLI
coding agent (pi, Codex, Claude Code). It is deliberately INDEPENDENT of
`hermes-gateway.service` — own unit, own config, no `After=`/`Wants=` on the incumbent.
Enablement is a concrete sequence; books/detail: `pi-coding-agent`, `hermes-cortex`.

1. **Config**: copy `ops/scripts/gateway.yaml.example` (or `gateway-pi.example.yaml` for a
   CLI backend) to `~/.hermes-cortex/gateway.yaml` — OUTSIDE the repo. A CLI backend entry
   is `kind: command` with an ABSOLUTE launcher path: `command` is an argv list, so `~`/`$HOME`
   are NOT expanded and the launcher is often a symlink into a dir not on a service PATH — a
   relative or guessed path is a silent per-message no-op.
2. **Env** in the cortex env (`~/hermes-cortex/.env`): the bot's `token_ref` var,
   `TELEGRAM_ALLOWED_USERS` (sender allowlist — REQUIRED; without it any Telegram user reaches
   a bot that RUNS CODE), `TELEGRAM_HOME_CHANNEL`, `GATEWAY_SECRET` (HMAC; the daemon refuses to
   start without it), `TELEGRAM_API_BASE` (the transport fails CLOSED without it — the standard
   value is `https://api.telegram.org`; a missing base would otherwise build `/bot<token>/method`),
   plus the bus URL/auth.
3. **Unit**: copy the template into `~/.config/systemd/user/`, `daemon-reload`, `enable --now`.
4. **Provider key** for the CLI backend via the `!command` pattern pointing at
   `env-value.sh <VAR>` — it supplies exactly the one var, so the agent never inherits the whole
   env file.

Pitfalls that cost a cycle here:

- **One poller per bot token — Telegram 409.** The unit's `ExecStartPre` guard
  (`guard_distinct_token.py`) REFUSES a config whose `token_ref` IS (or resolves to) the live
  `TELEGRAM_BOT_TOKEN`. Give the second gateway its OWN bot and its OWN token var
  (e.g. `MOSESPI_BOT_TOKEN`); two pollers on one token drop the live channel. This is the guard
  working, not a bug to bypass.
- **The unit's `ExecStart` interpreter must actually have the deps.** The template defaults to
  `/usr/bin/python3`; the cortex deps live in the fleet venv `~/.hermes-cortex/venv/bin/python3`.
  Point BOTH `ExecStartPre` and `ExecStart` at the venv python, and when a dep is missing install
  it INTO that venv (age-gated) rather than routing around it — a bot-lock
  `ImportError: psycopg package required` is the daemon's Postgres bus dependency surfacing, not a
  bad config; and a unit that crash-loops with that traceback is otherwise indistinguishable from
  a broken install.
- **`~/.hermes/config.yaml` is Hermes-owned and the patch/write tools REFUSE it** ("Agent cannot
  modify security-sensitive configuration"). Edit it only through the CLI: `hermes mcp add <name>
  --command … --args …` / `hermes mcp remove <name>`, or `hermes config`. The `add` flow prompts
  `Enable all N tools?` and CANCELS with no TTY — pipe `printf 'y\n' |` to accept. Read back with
  `hermes mcp list`. A doctor FAIL naming an MCP server that is present under a different key is a
  NAME drift (the fleet-canonical name is what the doctor expects, e.g. `agent-bus` and not a
  legacy alias) — add the canonical key and remove the legacy one, one server for the script.

## A gateway that serves the default profile ONLY — duplicate credential across profiles

`gateway.multiplex_profiles` unset means ON, but not unconditionally: at every boot
the default gateway runs the same preflight as `hermes gateway migrate --multiplex`
and multiplexes only when the fold would be safe. A **duplicate bot credential
between two profiles is a hard blocker** — so the gateway comes up serving the
default profile only, parks the other profile's adapter, and says so loudly (a
boxed warning at start; the same text in the `hermes update` summary, in
`hermes gateway status`, and in the dashboard's `/api/status` as
`multiplex_standalone_reason`). Log form:

```
hermes_cli.gateway_multiplex_mode: gateway.multiplex_profiles is unset (default: on)
but this gateway stays standalone: Profiles 'default' and 'personal' both configure
<platform> with the same credential ... It serves the default profile only
```

One token is one poller, so nothing is written on a refusal and neither a restart
nor `--force` clears it. Diagnose with counts only — never print a token:

```bash
ls ~/.hermes/profiles/                                     # default profile IS ~/.hermes
ls -la ~/.hermes/.env ~/.hermes/profiles/<name>/.env       # size/mtime, no content
grep -c TELEGRAM_BOT_TOKEN ~/.hermes/profiles/<name>/.env  # count, never the value
```

Before acting, decide whether the OTHER profile is real or vestigial — a profile
that never served a turn still blocks the fold (structural survey:
`hermes-home-cleanup`). Then pick one fix:

- **delete it** — `hermes profile delete -y <name>`. Ask the owner first: it prints the
  skill count it destroys and leaves a `.deleted/` tombstone. Prove nothing is lost
  BEFORE deleting — a name-only diff of both `.env` files plus a hash of the shared var
  (exact commands: `hermes-home-cleanup`) — because a strict subset with an identical
  hash means no backup copy of the credential is needed, and making one only spreads it.
- **keep the profile, strip just that platform's var** from its `.env` — smallest change.
- **give it its own bot** and route its chats from the default profile's
  `config.yaml` (`gateway.profile_routes`).

Then `hermes gateway migrate --multiplex`. **Expect it to be a NO-OP once the duplicate is
gone, and never read its rc=0 as "the state is fixed":** with one profile left it prints
"Only one profile exists: nothing to multiplex" and does NOT restart, so the boot-time
`multiplex_standalone_reason` in `gateway_state.json` keeps naming the deleted profile and
the dashboard keeps showing it. A restart is what re-runs the preflight:
`systemctl --user restart hermes-gateway.service`, then verify it LANDED (`MainPID` AND
`ExecMainStartTimestamp` both change) and read the post-state — the reason becomes
`only one profile exists (nothing to multiplex)`, `hermes profile list` stops printing the
warning, and the boot log reads `Cron scheduler will tick N profile(s)` with the stale
profile absent. Before restarting from inside a session, check your own ancestry: a CLI
session (`sshd → shell → hermes`) survives it, a session hosted BY the gateway does not
(`ps -o pid=,cmd= --ppid <gateway-pid>`).

- **Never identify the active profile by listing `profiles/*/`.** Resolve
  `HERMES_PROFILE` → `AGENT_NAME` (never hostname). A directory under `profiles/`
  is a second Hermes HOME, not a routing entry, and the alphabetically-first entry
  is not the active one — every fleet script carries that warning because it bites.
- **A profile is not "unused" because it is small.** Its `.env` alone is enough to
  block the whole host's multiplexing; the blocker outlives any single session.

## Common Failure Patterns

| Symptom | Root cause | Fix |
|---------|-----------|-----|
| `No bot token configured` | Token missing from .env | Add token, restart gateway |
| `401 Unauthorized` | Token revoked or wrong | Generate new token, update .env |
| Repeated reconnecting | Network / API instability | Check outbound connectivity; verify with `curl` |
| Connected but no delivery | Wrong chat ID / deliver target | Verify destination chat ID and `deliver` config |
| Gateway up, platform down | Platform-side outage | Wait + monitor; check platform status page |
| Serves default only; boxed "stays standalone" warning naming two profiles | Two profiles configure the same platform credential | Strip the credential from the redundant profile (or delete it), then `hermes gateway migrate --multiplex` |

## Verification

```bash
# End-to-end test after any fix: send a test message to the home channel
# via a cron or direct invocation, then confirm it arrived.
```

## Related
- `hermes-agent` — general Hermes configuration
- `telegram-delivery-diagnostics` — Telegram-specific delivery debugging
- `cortex-bus-messaging` — inter-agent messaging (separate from the user gateway)
- `psql-automation` — the `sg`/`NoNewPrivileges` store-access mechanism behind a
  "store unreachable" report from a hardened service
