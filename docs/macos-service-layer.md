# macOS Service Layer (launchd) — fleet service map

macOS counterpart of [`docs/linux-service-layer.md`](linux-service-layer.md). Every Hermes
Cortex service on a Mac is a **user LaunchAgent** in `~/Library/LaunchAgents/`, loaded with
`launchctl`. There is no systemd on macOS; the templates live in `docs/templates/*.plist`.

> **Titus is the fleet's only macOS host** (hostname `LAM2`, the developer machine — client
> only, push-only bus). This map therefore describes HIS Mac and any future Mac; every other
> host in the fleet is Linux and belongs to [`docs/linux-service-layer.md`](linux-service-layer.md).
> Templates here are still written portably on purpose: a second Mac must work without edits.

**Referenced by** `CONTRIBUTING.md` ("did you add a service or daemon?") and the pre-commit
docs audit, which both pointed at this file before it existed.

## The map

| Template | Label | What it runs | Notes |
|---|---|---|---|
| `com.hermes.cortex-gateway.plist` | `com.hermes.cortex-gateway` | the decoupled messaging gateway daemon (`cortex_gateway/daemon.py`) | No Hermes dependency. Sources `~/hermes-cortex/.env`, runs the launcher guard, execs the **fleet venv**. Exits **75** for `/restart` on macOS. |
| `com.hermes.gateway.plist` | `com.hermes.gateway` | the **Hermes** runtime gateway (`hermes_agent.gateway.run`) | The one service that legitimately uses the Hermes venv (the module lives there). Candidates for decommission as hosts migrate. |
| `com.hermes.cortex-dashboard.plist` | `com.hermes.cortex-dashboard` | the cortex dashboard (`dashboard/server.py`) | Dedicated dashboard venv, or the fleet venv as Option B. |
| `com.hermes.health-push.plist` | `com.hermes.health-push` | `ops/scripts/health/health-vector-push.sh` every 10 min | **Client-only agents (Titus, Gisu, Joseph) install this.** Set `AGENT_NAME` per host. |
| `com.docker.docker.plist` | `com.docker.docker` | Docker Desktop, unattended | So containers with `restart:` policy come back after login. |

## The three launchd rules (each one cost a broken service)

> **Reference:** `launchd.plist(5)` — `ProgramArguments` is "an array of strings … passed to
> `execvp(3)`". There is no shell in that path and therefore no variable expansion: a `$HOME`
> or `CORTEX_HOME` written literally is passed as a literal filename. Apple's TN2083
> ("Creating Launch Daemons and Agents") describes the same execution model. Expansion
> requires an interpreter, which is why every rule below uses `/bin/bash -lc`.

1. **launchd expands NOTHING inside plist strings.** `$HOME/...` or `CORTEX_HOME/...` written
   literally is a path that does not exist, and the job simply never starts. Every
   `ProgramArguments` that needs a home path goes through a shell:
   `/bin/bash -lc '…exec "$HOME/…"'`.
2. **`StandardOutPath` / `StandardErrorPath` must be literal paths** — so log files that live
   under a home directory are created and appended *inside* the shell command instead
   (`… >>"$HOME/.hermes-cortex/logs/x.log" 2>&1`), not via those keys.
3. **An XML comment may not contain a double hyphen.** `--unattended` in a comment makes the
   plist unparseable and `launchctl` rejects the file without explaining why.

## Interpreter convention

- Cortex-side services run the **fleet venv** (`~/.hermes-cortex/venv/bin/python3`), the
  interpreter `cortex-update.sh` registers every MCP server against. **Never `/usr/bin/python3`**
  for a cortex service, and never the Hermes venv.
- A service that needs the fleet venv sources the shared launcher guard first, so a missing
  venv/daemon lands in its log as `NO INTERPRETER at <path> …` with the fix (rc 78) instead of
  an unexplained exec failure:
  ```bash
  . "$HOME/.hermes-cortex/scripts/lib/require-fleet-venv.sh"
  require_fleet_venv "$HOME/.hermes-cortex/scripts/cortex_gateway/daemon.py"
  ```
  If the venv is missing, `cortex-update.sh` now creates and fills it on the host's next
  update. See `docs/troubleshooting.md` ("The fleet venv: a launcher dies with …").

## Install / check / remove

```bash
cp docs/templates/com.hermes.cortex-gateway.plist ~/Library/LaunchAgents/
launchctl load  ~/Library/LaunchAgents/com.hermes.cortex-gateway.plist
launchctl list com.hermes.cortex-gateway            # check
tail -f ~/Library/Logs/com.hermes.cortex-gateway.log
launchctl unload ~/Library/LaunchAgents/com.hermes.cortex-gateway.plist   # remove
rm ~/Library/LaunchAgents/com.hermes.cortex-gateway.plist
```

⚠️ **Only one poller per bot token.** Stop the incumbent (`com.hermes.gateway`) before loading
`com.hermes.cortex-gateway`, or the two 409 against each other.

## Enforced, not documented-only

`tests/test_fleet_venv_launchers.py` fails the suite when a template hardcodes
`/Users/<name>/` or `/home/<name>/`, when `$HOME` appears in `ProgramArguments` without a
leading `/bin/bash -lc`, or when a plist does not parse (Label + ProgramArguments present).
`tests/test_fleet_venv_check_block.py` covers the deploy's venv branches on both platforms.

## Linux

See [`docs/linux-service-layer.md`](linux-service-layer.md) for the systemd map. The two layers
are deliberately parallel: same env file (`~/hermes-cortex/.env`), same guard, same fleet venv,
different supervisor — and `/restart` returns **exit 75 (EX_TEMPFAIL)** under launchd's
`SuccessfulExit=false` policy where systemd's `Restart=always` relaunches on any exit.
