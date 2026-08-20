# Timezone Fleet Audit — 2026-08-20 (Esther)

Full record of the fleet-wide timezone audit that produced this skill. Numbers
and file lists are from that session; use as a migration reference, not a
live inventory (repo state moves).

## Finding

`HERMES_TIMEZONE` is the canonical timezone env var (upstream
`hermes_time.py` + cortex `hermes_tz.py` both read it), but it was set
**nowhere**: not in `~/hermes-cortex/.env`, `.env.example`, `agent.env`,
`config.yaml`, systemd user env, `/etc/environment`, or the gateway process
environ. The gateway systemd unit has no TZ env at all. All fleet hosts are
`Asia/Seoul`, so outputs happened to be right by system-clock coincidence —
not by contract.

- ~31 deployed scripts hardcoded KST in 3 patterns
- 5 LLM cron prompts hardcoded `[YYYY-MM-DD HH:MM KST]` output templates
- Only 3 scripts used `hermes_tz` (agent-service-recovery, agent-system-alert-watchdog, orch-fleet-watchdog)
- moses (SSH) identical: 30 KST refs, no HERMES_TIMEZONE

## Hardcode patterns found and fixes

| Pattern | Count | Fix |
|---|---|---|
| Python `datetime.now(timezone(timedelta(hours=9))).strftime("...KST")` | ~15 files | `format_timestamp("%...%Z")` |
| Python `KST = timezone(timedelta(hours=9))` module constant | 5 files | `KST = get_timezone()` |
| Bash `TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST'` | ~30 occurrences / 8 files | `$(ts)` helper |
| Python `datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=9)))` | few | `get_timezone()` |
| Bash `date -u ... UTC` (send-agent-learning.sh) | 1 | `$(ts)` |
| LLM prompt `[YYYY-MM-DD HH:MM KST]` | 5 jobs | TIMEZONE-READ-FIRST rule |

## Files migrated (repo source)

Python (ops/scripts/): health/agent-cron-quality-watchdog.py,
health/agent-scoring-activity-watchdog.py, health/agent-mcp-health-watchdog.py,
health/agent-model-health-watchdog.py, health/agent-system-alert-watchdog.py,
health/agent-service-recovery.py, manage/agent-budget-enforcer.py,
manage/agent-governance-auditor.py, manage/agent-auto-save-sessions.py,
manage/agent-memory-to-brain-sync.py, manage/ek-session-snapshot.py,
manage/analyze-briefings.py, agent/orch-health-report.py,
agent/orch-fleet-watchdog.py (fallback path), agent/agent-remediate-apply.py,
agent/agent-cron-failure-scanner.py, orch-bus/orch-bus-watch.py,
orch-bus/orch-bus-forwarder.py, orch-bus/orch-bus-audit-watchdog.py,
bus/workflow-inspector.py, cron_format.py, hermes_tz.py.

Bash: manage/agent-hermes-cortex-sync.sh, manage/agent-nginx-threat-pipeline.sh,
manage/agent-hermes-update.sh, manage/deploy-blocked-ips.sh,
health/check-memory-budget.sh, agent/agent-ip-submission.sh,
manage/update-session-state.sh, manage/send-agent-learning.sh, cron_format.sh.

LLM prompt jobs updated live (cronjob update) + installer sources:
agent-memory-pruning (80858f2b1edb), agent-agents-md-prune-apply (550d7c044315),
agent-mycortex-dream-nightly (6cb3c26a2ac9), -weekly (169ac3b60e36),
-monthly (c28568cc4f05). Installer sources: install-crons.sh,
install/install-dream-crons.sh.

## Wiring added

- `HERMES_TIMEZONE=Asia/Seoul` → `~/hermes-cortex/.env` + `.env.example`
- `ops/scripts/install/install-gateway-timezone.sh` (new) — systemd user
  drop-in `11-timezone.conf` on Linux; `~/.hermes/.env` append on macOS.
  Mirrors install-gateway-cron-timeout.sh contract (no self-restart; prints
  RESTART PENDING). Registered + invoked from cortex-update.sh.

## Notable sub-findings

- **cron_format.py `_timestamp()` bug**: `now = datetime.now(timezone.utc).astimezone()` → local; then `kst = now.astimezone(...) if not now.tzinfo else now` — since `now` always has tzinfo after astimezone(), the branch never fired; it always labeled local time "KST". Replaced with `hermes_tz.format_timestamp("%Y-%m-%d %H:%M %Z")`. Duplicate `from typing import Optional` at bottom of file cleaned.
- **cron_format.py/.sh were repo-only, never deployed** (absent from ~/.hermes-cortex/scripts/). Nothing sourced cron_format.sh.
- **agent-daily-bible-reading.py** (source at hermes-cortex/.hermes-cortex/scripts/): `KST = timezone.utc` dead constant, never referenced; dates use system-local `datetime.now()`. Marked DEPRECATED in comment. File lives outside ops/scripts (registered from `.hermes-cortex/scripts/`).
- **hermes_tz.py IANA branch** rendered `%Z` as "Asia/Seoul" (fixed-offset tz named after IANA). Fixed: `ZoneInfo(tz_spec)` when available → `%Z` = "KST". Return annotation widened `-> "Any"` (ZoneInfo is tzinfo, not timezone — Pyright error otherwise).
- **execute_code hermes_tools.write_file returned `verified: None` and did NOT persist** — a bulk bash migration (8 files, ts() helper insertion) silently didn't land; caught via `grep -c "ts() {"` = 0. Redone with the `patch` tool per file. Lesson: after any execute_code write batch, verify with git diff/grep; prefer `patch` for repo edits.
- **Deployed copies lag repo**: tested the deployed hermes_tz.py first and got stale behavior ("Asia/Seoul" output); the repo source was already fixed. Test repo source during migration.
- **send-agent-learning.sh** needed the `ts()` helper added (used `$(ts)` before defining it) — check every bash file that references the helper has it defined.

## Verification performed

- `python3 -m py_compile` all changed .py — clean
- `bash -n` all changed .sh — clean
- `HERMES_TIMEZONE=UTC bash check-memory-budget.sh --report` → `[2026-08-20 01:43 UTC]` (correct UTC conversion of 10:43 KST)
- unset → KST; `HERMES_TIMEZONE=Asia/Seoul python3 hermes_tz.py` → "Timestamp: ... KST"
- Final grep: zero executable-line `timedelta(hours=9)` / `TZ=Asia/Seoul date` / `%H:%M KST` in ops/scripts

## Left as follow-up (session hit iteration cap)

- Deploy (`cortex-update.sh`) + gateway restart for the drop-in to activate
- Commit/push repo changes; notify fleet (moses etc.)
- `orch-skill-lifecycle/SKILL.md` example header still shows KST (cosmetic; live prompt has no KST template)
