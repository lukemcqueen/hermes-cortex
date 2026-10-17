# Runbook — cortex env migration (one canonical `.env`)

> **Audience:** any agent, on Linux or macOS, that maintains a Hermes Cortex host.
> **Status:** current since the 2026-10 single-env refactor (updated 2026-10-17: the back-compat symlink is now `~/.hermes-cortex/.env`; `cortex-bus.conf` retired).
> **Companion:** `docs/env-vars.md` (variable reference) · `docs/design/gateway-envelope-verification.md`.

## The convention

There is exactly **one** cortex env file:

```
~/hermes-cortex/.env          ← the canonical env (gitignored, mode 600)
```

The deploy dir carries a **sanctioned back-compat symlink to it** (so legacy readers that resolve the deploy-dir path keep working). Everything else is **not ours**:

| Path | What it is | Rule |
|---|---|---|
| `~/hermes-cortex/.env` | the canonical cortex env | **edit this** |
| `~/.hermes-cortex/.env` | symlink → the canonical env (back-compat) | never edit; recreate with `consolidate-env.sh` if missing |
| `~/.hermes-cortex/cortex-bus.conf` | **retired 2026-10-17** (was the old legacy symlink name) | must not exist; `consolidate-env.sh` removes it |
| `~/.hermes/.env` | **Hermes-owned** (provider keys, Telegram) | never merge into it |

Per-host values are per-machine and gitignored; the repo ships only
`~/hermes-cortex/.env.example`.

**Why `~/.hermes-cortex/.env` is a symlink and not a real file:** the deploy
dir was once the home of a *stray* `.env` pointing at `~/langfuse/.env`
(removed 2026-10-01). Now the `.env` name is legitimately pinned to the
canonical env — a **real file** at that path (not a symlink to the canonical)
is unowned and must be resolved by hand, never overwritten.

## Applying the migration on a host

**You do not need to do this by hand.** `cortex-update.sh` runs the
consolidation first, every time:

```bash
cd ~/hermes-cortex && git pull --ff-only origin main
bash ops/scripts/cortex-update.sh          # runs consolidate-env.sh, then deploys
```

`consolidate-env.sh` is idempotent and:

1. **seeds** `~/hermes-cortex/.env` from `cortex-bus.conf` if the canonical env
   does not exist yet (hosts installed before the refactor);
2. merges any legacy-only variables into the canonical env (aborts on a *value*
   conflict rather than guessing);
3. creates `~/.hermes-cortex/.env` as a **symlink to the canonical env**;
4. **retires** any leftover `cortex-bus.conf` (backing up a real file first);
5. refuses to touch `~/.hermes/.env` by design.

### Manual run (same thing, explicit)

```bash
bash ~/.hermes-cortex/scripts/consolidate-env.sh            # migrate
bash ~/.hermes-cortex/scripts/consolidate-env.sh --check    # dry check; exit 1 if vars are missing
```

## Verify

The behaviours this runbook documents are pinned by committed tests, runnable in
the repo: `tests/test_doctor_cortex_env.py` drives `check_cortex_env` both ways
(sanctioned symlink PASS, real-file FAIL, missing-symlink FAIL, leftover
`cortex-bus.conf` FAIL) and `tests/test-consolidate-env.sh` drives
`consolidate-env.sh`'s migration / idempotence / real-file refusal / `--check`
against an isolated temp HOME. Run them to reproduce the claims rather than
trusting this prose.

```bash
# 1. the doctor's own check (FAILs on a missing/misplaced env, with the fix)
python3 ~/.hermes-cortex/scripts/cortex-doctor.py 2>&1 | grep -i "cortex env"

# 2. the canonical env exists, is 600, and the deploy-dir .env symlink resolves to it
ls -la ~/hermes-cortex/.env ~/.hermes-cortex/.env
[ ~/hermes-cortex/.env -ef ~/.hermes-cortex/.env ] && echo "one file ✓"

# 3. the retired name is gone
[ ! -e ~/.hermes-cortex/cortex-bus.conf ] && echo "cortex-bus.conf retired ✓"
```

The doctor reports:

- `✅ cortex env — canonical ~/hermes-cortex/.env present (600); ~/.hermes-cortex/.env is the sanctioned symlink; cortex-bus.conf retired`
- `❌ cortex env — <problem>; fix: run cortex-update.sh (it runs consolidate-env.sh)`

## What changed in the refactor (so you can implement it)

1. **All references swept to `.env`.** ~66 `cortex-bus.conf` references across
   code, docs, skills and AGENTS.md now point at the canonical env. The only
   legitimate remaining references are `ops/scripts/manage/consolidate-env.sh`
   (it performs the migration) and the doctor's `check_cortex_env` (it enforces
   the retirement). A `cortex-bus.conf` reference elsewhere is a regression —
   `git grep -n cortex-bus.conf` should show only those two (and genuinely
   different files: `~/.hermes-cortex/conf.d/…`, `~/.hermes/cortex-bus.conf`).
2. **The deploy dir holds the sanctioned `.env` symlink** (was: "no `.env`").
   The stray-langfuse trap is now caught differently — the doctor FAILs on a
   REAL file (not a symlink) at `~/.hermes-cortex/.env`, not on the
   symlink itself. Readers were repointed in the Oct refactor
   (`agent-push-metrics.sh`, `install-soft-session-cap.sh`,
   `cortex_doctor._env_file_value`); `VICTORIA_METRICS_URL` +
   `_FALLBACK_URL` were migrated into the canonical env.
3. **macOS parity.** The gateway service has a launchd counterpart —
   `docs/templates/com.hermes.cortex-gateway.plist` — because systemd does not
   exist on macOS and launchd has no `EnvironmentFile`; the plist wrapper
   sources the same canonical env before exec'ing the daemon.
4. **Enforcement.** `check_cortex_env` in `cortex_doctor/checks.py` FAILs when
   the canonical env is missing, when a REAL file (not a symlink) appears at
   `~/.hermes-cortex/.env`, when the sanctioned symlink is missing or points
   elsewhere, or when a retired `cortex-bus.conf` still exists.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Doctor: `canonical ~/hermes-cortex/.env is MISSING` | fresh or legacy host | `bash ops/scripts/cortex-update.sh` |
| Doctor: `~/.hermes-cortex/.env is a REAL file` | an unowned real `.env` sits at the deploy-symlink path | resolve it by hand (check what it points to / where it came from), then `bash ~/.hermes-cortex/scripts/consolidate-env.sh` |
| Doctor: `~/.hermes-cortex/.env symlink is MISSING` | canonical exists but the sanctioned symlink is gone | `bash ~/.hermes-cortex/scripts/consolidate-env.sh` |
| Doctor: `retired cortex-bus.conf … remains` | old host not yet consolidated | `bash ~/.hermes-cortex/scripts/consolidate-env.sh` |
| A script finds no `CORTEX_BUS_URL` | env resolves to the wrong path | check the script reads `~/hermes-cortex/.env` (grep for `cortex-bus.conf`) |
| `CORTEX_BUS_URL not configured (checked: …/.hermes-cortex/.env)` | a script still hardcodes the old deploy-dir path | repoint it at the canonical env |

## Do not

- Do **not** write cortex variables into `~/.hermes/.env` (Hermes-owned).
- Do **not** replace `~/.hermes-cortex/.env` with a real file — it must stay a symlink to the canonical env.
- Do **not** recreate `cortex-bus.conf` — it is retired.