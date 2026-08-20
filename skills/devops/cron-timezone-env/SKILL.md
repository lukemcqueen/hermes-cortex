---
name: cron-timezone-env
description: "Cron timestamps follow HERMES_TIMEZONE env, never hardcoded."
version: 1.0.0
category: devops
author: Hermes Cortex (Esther)
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [cron, timezone, env, hermes-tz, kst, audit]
    related_skills: [cron-job-management, cron-format-standard, shell-scripting]
---

# Cron Timezone — Env-Driven Discipline

Every cron output timestamp (headers, log lines, delivered messages) must
derive from the host's configured timezone via the `HERMES_TIMEZONE` env var
(IANA name, e.g. `Asia/Seoul`) — **never** hardcode `KST`, `Asia/Seoul`, or
`timedelta(hours=9)` in a script or LLM prompt template. The env var is the
single source of truth; system local time is the fallback when unset.

## When to Use

- Writing or auditing any cron script (Python or bash) that prints a timestamp
- Editing an LLM cron prompt that contains an output-format example with a timezone label
- Investigating "why does this cron show the wrong time/zone"
- Setting up a new host and wiring its timezone for the fleet

## Canonical resolution chain

`HERMES_TIMEZONE` env → (upstream `hermes_time.py` also checks `config.yaml` `timezone` key) → system local time (`datetime.now().astimezone()` / `date`). Both the upstream `hermes_time.py` and the cortex `hermes_tz.py` implement this; scripts should call `hermes_tz` directly.

## Correct patterns

### Python (use `hermes_tz.py`, deployed alongside scripts)

```python
from hermes_tz import format_timestamp, get_timezone

ts = format_timestamp("%Y-%m-%d %H:%M %Z")          # → "2026-08-20 10:36 KST"
ts = format_timestamp("[%Y-%m-%d %H:%M %Z]")        # cron prefix form
KST = get_timezone()                                 # replaces timezone(timedelta(hours=9))
now = datetime.now(get_timezone())
```

Key rules:
- `format_timestamp("%...%Z")` — the `%Z` renders the correct abbreviation (KST, UTC, …) from the resolved tz. Never hardcode the label string.
- Existing `KST = timezone(timedelta(hours=9))` module constants become `KST = get_timezone()` — every downstream `datetime.now(KST)` / `fromtimestamp(ts, tz=KST)` follows automatically.
- Converting a UTC timestamp for display: `dt.astimezone(get_timezone()).strftime("%H:%M:%S %Z")` — never `dt + timedelta(hours=9)`.
- `hermes_tz.get_timezone()` returns a `tzinfo` (ZoneInfo for IANA names) — annotate return as `-> "Any"` not `-> timezone` (ZoneInfo is not a timezone subclass; Pyright flags it).

### Bash (env-driven `ts()` helper)

```bash
# Timezone-aware timestamp: honors HERMES_TIMEZONE (IANA), else system TZ.
ts() {
  if [[ -n "${HERMES_TIMEZONE:-}" ]]; then
    TZ="${HERMES_TIMEZONE}" date '+%Y-%m-%d %H:%M %Z'
  else
    date '+%Y-%m-%d %H:%M %Z'
  fi
}
```

Replace `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST'` with `$(ts)` everywhere.

### LLM cron prompts

Add a `## TIMEZONE — READ FIRST` section before the OUTPUT FORMAT template:

```
## TIMEZONE — READ FIRST
The header timestamp must use the host configured timezone, NOT a hardcoded label. Run `date '+%Y-%m-%d %H:%M %Z'` (or `date '+%H:%M %Z'` for time-only) and use its exact output — the timezone comes from HERMES_TIMEZONE / system local time. The KST in the example below is illustrative; substitute whatever %Z returns.
```

The KST in the example header stays (LLMs mimic concrete text) — the rule above it overrides the label.

## Wiring the env var (one-time per host)

1. `HERMES_TIMEZONE=Asia/Seoul` in `~/hermes-cortex/.env` (canonical, gitignored) + documented in `.env.example`
2. `install-gateway-timezone.sh` (ops/scripts/install/) — systemd user drop-in `11-timezone.conf` on Linux, `~/.hermes/.env` append on macOS; registered + invoked from `cortex-update.sh`
3. Activation needs a gateway restart (drop-ins read at process exec); until then `hermes_tz` falls back to system local — identical output on Asia/Seoul hosts

## Audit checklist (how to verify a fleet)

- `grep -rn "timedelta(hours=9)\|TZ=Asia/Seoul date\|%H:%M KST" ops/scripts/ --include="*.py" --include="*.sh"` — must be empty (excluding comments/docstrings)
- `grep -rn "HERMES_TIMEZONE" ~/hermes-cortex/.env ~/hermes-cortex/.env.example` — var present
- `grep -rn "JOB_ID) \[YYYY-MM-DD HH:MM KST\]" ops/scripts/ skills/` — remaining template headers must each have a TIMEZONE rule above them
- LLM prompt sources: patch BOTH live `jobs.json` (via cronjob update) AND the installer `create_cron` blocks (install-crons.sh / install-dream-crons.sh) — a live-only edit gets reverted by the next reinstall
- Runtime proof: `HERMES_TIMEZONE=UTC bash script.sh --report` must show UTC-converted time; unset → system local

## Pitfalls

- **`cron_format.py` had a real TZ bug** — its `_timestamp()` did `now = datetime.now(timezone.utc).astimezone()` then conditionally "converted" — always labeling local time as KST. Any helper that labels local time as a fixed zone is wrong; delegate to `hermes_tz`.
- **`cron_format.sh` / `cron_format.py` were repo-only, never deployed** — check `~/.hermes-cortex/scripts/` before assuming a shared helper is live.
- **execute_code `hermes_tools.write_file` can return `verified: None` and NOT persist** (observed 2026-08-20: bulk bash migration silently didn't land). After any execute_code write batch, verify with `git diff --stat` / grep before proceeding; use the `patch` tool for repo edits.
- **Deployed copies lag repo** — after editing `ops/scripts/*`, the `~/.hermes-cortex/scripts/` copy is stale until `cortex-update.sh` runs. Test the repo source path, not the deployed one, mid-migration.
- **Bible/other scripts with dead TZ constants** — `KST = timezone.utc` commented "we'll note KST in output" is a landmine; the actual dates used system-local `datetime.now()`. Mark deprecated or fix to `get_timezone()`.

## Verification

- All changed `.py` compile: `python3 -m py_compile <file>`
- All changed `.sh` pass: `bash -n <file>`
- Behavior: run one migrated script with `HERMES_TIMEZONE=UTC` and confirm UTC output; run unset and confirm system-local (KST) output
- `hermes_tz.py` self-test: `HERMES_TIMEZONE=Asia/Seoul python3 hermes_tz.py` → "Timestamp: ... KST"

See `references/timezone-audit-2026-08-20.md` for the full fleet audit findings and file-by-file migration record.
