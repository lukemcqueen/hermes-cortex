# Cron Schedules — Hermes Cortex

> **Canonical schedule reference.** Every cron job in the fleet, its schedule, type, script/prompt, and delivery.
>
> **Naming convention:** All crons MUST use group prefixes. No bare names.
>
> **⏱️ LLM-cron stagger (2026-08-07):** LLM-driven crons (Type=LLM) show their
> **base** schedule here. At install time, `create_cron()` in the installers
> rewrites the minute field to a deterministic per-host value
> (`cksum(hostname:cron-name) % 60`) so fleet hosts don't all hit the model at
> the same minute. Live schedules may therefore differ in the minute from this
> table — the hour is always preserved. `no_agent` crons keep exact schedules.

| Column | Meaning |
|--------|---------|
| **Name** | Cron job name (matches `cronjob action='list'`) |
| **Schedule** | Crontab expression or human-friendly interval |
| **Type** | `LLM` (uses tokens) or `no_agent` (script-only, $0) |
| **Script / Skill** | Script file (relative to `~/.hermes/scripts/`) or skill name |
| **Deliver** | Where output is sent |
| Scope | `orch` = orchestrator-only, `agent` = all agents, `local` = this machine |

## Delivery Policy — LLM crons (issues only, never status)

> Applies to every LLM cron that delivers to `origin` (fixer / inbox / bus families).
> Enforced in the prompts — see `ops/scripts/install-crons.sh` create_cron blocks.
> Added 2026-08-06 per Luke directive ("I want to see any issue; I don't want to
> see 'no issue' / 'idle' / 'skipped' / no ops").

- **Deliver ONLY when there is a REAL issue** — a failure, a blocked/failed workflow, a critical alert, or something actually fixed/restored.
- **NEVER deliver status or ops narration** — "no issues", "all clear", "system healthy", "nothing to report", idle/skipped notices, scan/assessment summaries, governance/cycle/cleanup reports, "here's my report".
- **Nothing actionable → reply EXACTLY `[SILENT]`** (suppresses delivery).
- **Guard crons (workday):** when the session guard says ACTIVE → `[SILENT]` (skip; the user is active — never deliver a "skipped" notice).

## Orchestrator-only (`orch-*` prefix)

| Name | Schedule | Type | Script / Skill | Deliver |
|------|----------|------|----------------|---------|
| `orch-bus-audit-watchdog` | `*/1 * * * *` | no_agent | `orch-bus-audit-watchdog.py` | Telegram |
| `orch-bus-recover-timeouts` | `*/5 * * * *` | no_agent | `orch-bus-recover-timeouts.sh` | origin |
| `orch-bus-confirmation-poller` | `every 10m` | no_agent | `orch-bus-confirmation-poller.py` | local |
| `orch-bus-confirmation-alert` | `every 60m` | no_agent | `orch-bus-confirmation-alert.sh` | Telegram |
| `orch-bus-forwarder-sync` | `*/2 * * * *` | no_agent | `orch-bus-forwarder.py` | origin |
| `orch-clean-health-queue` | `*/10 * * * *` | no_agent | `orch-clean-health-queue.py` | origin |
| `orch-fleet-watchdog` | `*/5 * * * *` | no_agent | `orch-fleet-watchdog.py` | Telegram |
| `orch-health-report-weekday` | `0 9-18 * * 1-5` | no_agent | `orch-health-report.py` | origin |
| `orch-health-report-saturday` | `0 11,17 * * 6` | no_agent | `orch-health-report.py` | origin |
| `orch-skill-lifecycle` | `0 4 * * *` | LLM | (orch-skill-lifecycle skill) | origin |
| `orch-skill-report-request` | `0 2 * * 1` | no_agent | `orch-skill-report-request.sh` | origin |
| `orch-skill-evaluate` | `0 9 * * 2` | LLM | (prompt) | origin |

## All-agent (`agent-*` prefix)

| Name | Schedule | Type | Script / Skill | Deliver |
|------|----------|------|----------------|---------|
| `agent-fixer-workday` | `0 9-17 * * 1-5` | LLM | auto-remediation skill + session-active-guard.py | origin |
| `agent-fixer-evening` | `0 18,20,22 * * 1-5` | LLM | auto-remediation skill | origin |
| `agent-fixer-overnight` | `0 3 * * 1-5` | LLM | auto-remediation skill | origin |
| `agent-remediation-sensor` | `*/5 * * * *` | no_agent | `agent-remediation-sensor.py` | local (runs only where IS_SERVER=true) |
| `agent-remediate-apply` | `*/10 * * * *` | no_agent | `agent-remediate-apply.py` | origin |
| `agent-message-handler` | `*/5 * * * *` | no_agent | `agent-message-handler.py` | local |
| `agent-service-recovery` | `*/5 * * * *` | no_agent | `agent-service-recovery.py` | origin |
| `agent-system-alert-watchdog` | `*/30 * * * *` | no_agent | `agent-system-alert-watchdog.py` | origin |
| `agent-cron-quality-watchdog` | `*/10 * * * *` | no_agent | `agent-cron-quality-watchdog.py` | origin |
| `agent-langfuse-health-watchdog` | `0 * * * *` | no_agent | `agent-langfuse-health-watchdog.py` | origin |
| `agent-model-health-watchdog` | `0 7 * * *` | no_agent | `agent-model-health-watchdog.py` | origin |
| `agent-secret-leak-watchdog` | `0 */4 * * *` | no_agent | `agent-secret-leak-watchdog.py` | origin |
| `agent-ip-submission` | `*/30 * * * *` | no_agent | `agent-ip-submission.sh` | origin |
| `agent-hermes-update` | `23 22 * * *` | no_agent | `agent-hermes-update.sh` | local |
| `agent-hermes-cortex-sync` | `33 22 * * *` | no_agent | `agent-hermes-cortex-sync.sh` | origin |
| `agent-memory-to-brain-sync` | `0 */6 * * *` | no_agent | `agent-memory-to-brain-sync.py` | local |
| `agent-governance-auditor` | `0 */6 * * *` | no_agent | `agent-governance-auditor.py` | origin |
| `agent-learning-collector` | `0 */6 * * *` | no_agent | `agent-learning-collector.py` | local |
| `agent-session-mine` | `0 2 * * *` | no_agent | `agent-session-mine-cron.py` | local |
| `agent-nginx-threat-pipeline` | `0 5 * * *` | no_agent | `agent-nginx-threat-pipeline.sh` | `telegram:${TELEGRAM_HOME_CHANNEL}` | *(explicit target from env — script-created crons get origin=null and would be silent)* |
| `agent-gbrain-doctor` | ~~`5 6 * * *`~~ | ~~no_agent~~ | ~~`agent-gbrain-doctor.sh`~~ | ~~origin~~ | ⚠️ **STALE/REMOVED 2026-08-02** — gbrain decommissioned; mycortex replaces (`mycortex doctor`). Agents with gbrain components still installed: decommission per-host or ignore. |
| `agent-gbrain-nightly-dream` | ~~`0 3 * * 6`~~ | ~~no_agent~~ | ~~`agent-gbrain-nightly-dream.sh`~~ | ~~origin~~ | ⚠️ **STALE/REMOVED 2026-08-02** — gbrain decommissioned; no consumer (verified). |
| `agent-gbrain-update-sync` | ~~`0 2 * * 0`~~ | ~~no_agent~~ | ~~`agent-gbrain-update-sync.sh`~~ | ~~origin~~ | ⚠️ **STALE/REMOVED 2026-08-02** — obsolete with gbrain binary uninstall. |
| `agent-mycortex-sync` | `*/15 * * * *` | no_agent | `agent-mycortex-sync.sh` | origin | *(knowledge brain sync — replaces gbrain autopilot)* |
| `agent-mycortex-dream-nightly` | `0 3 * * *` | LLM | (prompt) | origin | *(nightly serendipity digest — fresh-page connections, writes to `~/brain/<profile>/dreams/`; replaces gbrain creative-dream layer; optional via install-dream-crons.sh)* |
| `agent-mycortex-dream-weekly` | `0 3 * * 6` | LLM | (prompt) | origin | *(weekly deep dream — lessons synthesis + scripture connection, ~200-250 words written to `~/brain/<profile>/dreams/`; optional)* |
| `agent-mycortex-dream-monthly` | `0 3 1 * *` | LLM | (prompt) | origin | *(monthly arc — time-lapse + knowledge-gap probe, ~300 words written to `~/brain/<profile>/dreams/`; optional)* |
| `agent-mycortex-parity` | ~~removed 2026-08-03~~ | no_agent | — | origin | *(S-010 flip-gate watchdog — RETIRED with gbrain; gate closed, parity is now a manual regression fixture only)* |
| `agent-scoring-activity-watchdog` | `0 14,20 * * *` | no_agent | `agent-scoring-activity-watchdog.py` | origin |
| `agent-session-cache-build` | `0 5 * * 1` | no_agent | `agent-session_cache.py` | origin |
| `agent-offline-code-index` | `0 5 * * 0` | no_agent | `agent-offline-code-index.sh` | local |
| `agent-llm-judge-scorer-weekday` | `0 12,20 * * 1-5` | no_agent | `agent-llm-judge-scorer.py` | local |
| `agent-llm-judge-scorer-weekend` | `0 22 * * 0,6` | no_agent | `agent-llm-judge-scorer.py` | local |
| `agent-memory-pruning` | `0 4 * * 1` | LLM | (prompt) | origin |
| `agent-auto-save-sessions` | `every 360m` | no_agent | `agent-auto-save-sessions.py` | local |
| `agent-stale-ref-watchdog` | `0 5 * * *` | no_agent | `manage/agent-stale-ref-watchdog.sh` | origin |
| `agent-swap-refresh` | `0 5 * * *` | no_agent | `agent-swap-refresh.py` | origin |
| `agent-agents-md-prune-scan` | `0 4 * * 1-6` | no_agent | `agent-agents-md-prune-scan.py` | local |
| `agent-agents-md-prune-apply` | `30 4 * * 1-6` | LLM | (prompt) | origin |
| `cortex-bus-workday` | `0 9-17 * * 1-5` | LLM | session-active-guard.py | origin |
| `cortex-bus-evening` | `0 18,20,22 * * 1-5` | LLM | (prompt) | origin |
| `cortex-bus-overnight` | `0 3 * * 1-5` | LLM | (prompt) | origin |
| `agent-daily-bible-reading` | `0 1 * * *` | LLM | agent-daily-bible-reading skill | origin |
| `agent-daily-soul-refinement` | ~~`0 23 * * *`~~ | ~~LLM~~ | ~~soul-refinement skill~~ | ~~origin~~ | ⚠️ **ABSORBED 2026-08-02** — fleet-level daily soul refinement merged into `orch-skill-lifecycle`. Per-host variant is `local-agent-daily-soul-refinement`. |
| `agent-weekly-loop-eval` | ~~`0 9 * * 1`~~ | ~~LLM~~ | ~~loop-governance skill~~ | ~~origin~~ | ⚠️ **ABSORBED 2026-08-02** — fleet-level weekly loop eval merged into `orch-skill-lifecycle`. Per-host variant is `local-agent-weekly-loop-eval`. |
| `agent-no-verify-audit` | `every 60m` | LLM | (prompt) | origin |
| `agent-inbox-workday` | `0 9-17 * * 1-5` | LLM | session-active-guard.py | origin |
| `agent-inbox-evening` | `0 18,20,22 * * 1-5` | LLM | (prompt) | origin |
| `agent-inbox-overnight` | `0 3 * * 1-5` | LLM | (prompt) | origin |
| `cortex-bus-failover-watchdog` | `*/5 * * * *` | no_agent | `cortex-bus-failover-watchdog.py` | Telegram |
| `agent-push-metrics` | `every 5m` | no_agent | `agent-push-metrics.sh` | local |
| `agent-session-correction-scan` | `0 22 * * 0` | no_agent | `manage/agent-session-correction-scan.py` | local |
| `agent-mycortex-retention` | `0 6 * * *` | no_agent | `agent-mycortex-retention.py` | origin |

## Local-only (`local-*` prefix)

| Name | Schedule | Type | Deliver |
|------|----------|------|---------|
| `local-agent-daily-news-brief` | `0 7 * * *` | LLM | Telegram |
| `local-agent-daily-finance-brief` | `0 18 * * 1-5` | LLM | Telegram |
| `local-agent-agents-doc-audit` | `0 7 * * 1` | LLM | origin |
| `local-agent-upwork-job-scanner` | `0 8 * * *` | LLM | Telegram |
| `local-agent-daily-soul-refinement` | `0 23 * * *` | LLM | origin |
| `local-agent-weekly-loop-eval` | `0 9 * * 1` | LLM | origin |
| `local-orch-fleet-command-verifier` | `every 10m` | no_agent | Telegram |

---

**Migration:** All crons renamed to `agent-*` prefix Jul 21 2026. Old bare names are replaced. Run `fix-cron-duplicates.py` to verify.

**All running crons documented above — last verified: 2026-08-03**
