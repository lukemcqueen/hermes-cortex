# Linux Service Layer (systemd) — fleet service map

Linux counterpart of [`docs/macos-service-layer.md`](macos-service-layer.md). Every Hermes
Cortex service on Linux is a **user unit** in `~/.config/systemd/user/`, managed with
`systemctl --user`. The templates live in `docs/templates/*.service`.

> **Every fleet host except Titus is Linux.** Titus is the only macOS host (hostname `LAM2`,
> the developer machine) and follows [`docs/macos-service-layer.md`](macos-service-layer.md);
> orchestrators, server-agents and every other worker are covered here.

**Referenced by** `CONTRIBUTING.md` ("did you add a service or daemon?") and the pre-commit
docs audit, which both pointed at this file before it existed.

## The map

| Template | Unit | What it runs | Notes |
|---|---|---|---|
| `cortex-gateway.service` | `cortex-gateway.service` | the decoupled messaging gateway daemon (`cortex_gateway/daemon.py`) | No Hermes dependency and no unit dependency on the Hermes gateway — that independence is the point. `ExecStartPre` runs `guard_distinct_token.py`, which fails CLOSED if the config's token resolves to the live bot token. Config `%h/.hermes-cortex/gateway.yaml`; env from `%h/hermes-cortex/.env`. |
| `health-vector.service` | `health-vector.service` | `ops/scripts/health/health-vector.py --serve 8905` | INTERNAL port **8905** — nginx's `health_backend` upstream expects it. Do not change it without patching the nginx upstream too. |

## Rules

1. **USER-LEVEL ONLY.** `~/.config/systemd/user/`, never `/etc/systemd/system/`: a system-level
   copy of the gateway puts a second poller on the same bot token (Telegram **409 Conflict**),
   and a system-level health vector conflicts on port 8905.
2. **`%h` is the home specifier** — that is how these units stay host-independent. Never write
   `/home/<user>/`. systemd expands `%h` inside `ExecStart`/`ExecStartPre` arguments, including
   inside the shell string below.
3. **Interpreter: the fleet venv**, `%h/.hermes-cortex/venv/bin/python3` — the venv
   `cortex-update.sh` registers every MCP server against. **Not `/usr/bin/python3`** (it lacks
   the declared set) and not the Hermes venv.
4. **Source the launcher guard before exec'ing**, so a missing venv or payload is named in the
   journal instead of dying as `No such file or directory`:
   ```ini
   ExecStart=/bin/bash -lc '. %h/.hermes-cortex/scripts/lib/require-fleet-venv.sh; require_fleet_venv <payload>; exec "%h/.hermes-cortex/venv/bin/python3" <payload> <args>'
   ```
   If the venv is absent, `cortex-update.sh` creates and fills it on the host's next update
   (see `docs/troubleshooting.md`).

## `/restart` semantics (the one real difference from macOS)

The gateway's `/restart` exits with the code its supervisor needs:

| Supervisor | Exit | Why |
|---|---|---|
| systemd (`Restart=always`) | **0** | any exit is relaunched |
| launchd (`KeepAlive` `SuccessfulExit=false`) | **75** (EX_TEMPFAIL) | launchd restarts in the *inverse* condition of success — a clean exit(0) would park the job |

Do not "normalise" these: each is correct for its supervisor, and the code paths live together
in the gateway.

## Install / check / remove

```bash
cp docs/templates/cortex-gateway.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now cortex-gateway.service
systemctl --user status cortex-gateway.service        # check
journalctl --user -u cortex-gateway.service -f
systemctl --user disable --now cortex-gateway.service # remove
```

⚠️ **Only one poller per bot token.** Stop the incumbent (`systemctl --user stop
hermes-gateway.service`) before starting `cortex-gateway.service`, or the two 409.

## Enforced, not documented-only

`tests/test_fleet_venv_launchers.py` covers the shared launcher rules and the templates'
portability (no hardcoded user home, `$HOME` only behind a shell, plists parse); the deploy's
venv branches are covered by `tests/test_fleet_venv_check_block.py`. Both run on macOS and
Linux — the map above is checked, not just described.
