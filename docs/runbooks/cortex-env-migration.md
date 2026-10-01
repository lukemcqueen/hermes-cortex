# Runbook — cortex env migration (one canonical `.env`)

> **Audience:** any agent, on Linux or macOS, that maintains a Hermes Cortex host.
> **Status:** current since the 2026-10 single-env refactor.
> **Companion:** `docs/env-vars.md` (variable reference) · `docs/design/gateway-envelope-verification.md`.

## The convention

There is exactly **one** cortex env file:

```
~/hermes-cortex/.env          ← the canonical env (gitignored, mode 600)
```

Everything else is either a **symlink to it** or **not ours**:

| Path | What it is | Rule |
|---|---|---|
| `~/hermes-cortex/.env` | the canonical cortex env | **edit this** |
| `~/.hermes-cortex/cortex-bus.conf` | symlink → the canonical env (legacy name) | never edit; kept for back-compat |
| `~/.hermes-cortex/.env` | **removed 2026-10-01** — it was a stray symlink to `~/langfuse/.env` | must not exist |
| `~/.hermes/.env` | **Hermes-owned** (provider keys, Telegram) | never merge into it |

Per-host values are per-machine and gitignored; the repo ships only
`~/hermes-cortex/.env.example`.

## Applying the migration on a host

**You do not need to do this by hand.** `cortex-update.sh` runs the
consolidation first, every time:

```bash
cd ~/hermes-cortex && git pull --rebase origin main
bash ops/scripts/cortex-update.sh          # runs consolidate-env.sh, then deploys
```

`consolidate-env.sh` is idempotent and:

1. **seeds** `~/hermes-cortex/.env` from `~/.hermes-cortex/cortex-bus.conf` if the
   canonical env does not exist yet (hosts installed before the refactor);
2. merges any conf-only variables into the canonical env (aborts on a *value*
   conflict rather than guessing);
3. replaces `cortex-bus.conf` with a **symlink to the canonical env**;
4. refuses to touch `~/.hermes/.env` by design.

### Manual run (same thing, explicit)

```bash
bash ~/.hermes-cortex/scripts/consolidate-env.sh            # migrate
bash ~/.hermes-cortex/scripts/consolidate-env.sh --check    # dry check; exit 1 if vars are missing
```

## Verify

```bash
# 1. the doctor's own check (FAILs on a missing/misplaced env, with the fix)
python3 ~/.hermes-cortex/scripts/cortex-doctor.py 2>&1 | grep -i "cortex env"

# 2. the canonical env exists, is 600, and the symlink resolves to it
ls -la ~/hermes-cortex/.env ~/.hermes-cortex/cortex-bus.conf
[ ~/hermes-cortex/.env -ef ~/.hermes-cortex/cortex-bus.conf ] && echo "one file ✓"

# 3. no stray deploy-dir .env
[ ! -e ~/.hermes-cortex/.env ] && echo "no stray .env ✓"
```

The doctor reports:

- `✅ cortex env — canonical ~/hermes-cortex/.env present (600); cortex-bus.conf is the sanctioned symlink; no deploy-dir .env`
- `❌ cortex env — <problem>; fix: run cortex-update.sh (it runs consolidate-env.sh)`

## What changed in the refactor (so you can implement it)

1. **All references swept to `.env`.** ~66 `cortex-bus.conf` references across
   code, docs, skills and AGENTS.md now point at the canonical env. The only
   legitimate remaining reference is `ops/scripts/manage/consolidate-env.sh`
   (it performs the merge). A `cortex-bus.conf` reference elsewhere is a
   regression — `git grep -n cortex-bus.conf` should show only that script (and
   genuinely different files: `~/.hermes-cortex/conf.d/…`, `~/.hermes/cortex-bus.conf`).
2. **The deploy dir holds no `.env`.** Readers that used it were repointed
   (`agent-push-metrics.sh`, `install-soft-session-cap.sh`,
   `cortex_doctor._env_file_value`); `VICTORIA_METRICS_URL` +
   `_FALLBACK_URL` were migrated into the canonical env.
3. **macOS parity.** The gateway service has a launchd counterpart —
   `docs/templates/com.hermes.cortex-gateway.plist` — because systemd does not
   exist on macOS and launchd has no `EnvironmentFile`; the plist wrapper
   sources the same canonical env before exec'ing the daemon.
4. **Enforcement.** `check_cortex_env` in `cortex_doctor/checks.py` FAILs when
   the canonical env is missing, when a stray deploy-dir `.env` reappears, or
   when `cortex-bus.conf` is not the sanctioned symlink.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Doctor: `canonical ~/hermes-cortex/.env is MISSING` | fresh or legacy host | `bash ops/scripts/cortex-update.sh` |
| Doctor: `stray ~/.hermes-cortex/.env` | an old setup recreated it | `rm ~/.hermes-cortex/.env` — the canonical env is in the repo dir |
| Doctor: `cortex-bus.conf is a real file` | host predates consolidation | `bash ~/.hermes-cortex/scripts/consolidate-env.sh` |
| A script finds no `CORTEX_BUS_URL` | env resolves to the wrong path | check the script reads `~/hermes-cortex/.env` (grep for `cortex-bus.conf`) |
| `CORTEX_BUS_URL not configured (checked: …/.hermes-cortex/.env)` | a script still hardcodes the removed deploy-dir path | repoint it at the canonical env |

## Do not

- Do **not** write cortex variables into `~/.hermes/.env` (Hermes-owned).
- Do **not** recreate `~/.hermes-cortex/.env`.
- Do **not** edit `cortex-bus.conf` as a file — it is a symlink.
