# Cron Schedules — Hermes Cortex

> **Canonical schedule reference.** Every cron job in the fleet, its schedule, type, script/prompt, and delivery. Keep this file in sync whenever a cron is created, renamed, removed, or rescheduled.
>
> **Local-only crons:** Jobs with the `local-` prefix are server-specific and NOT in the repo installer. They're created directly via `cronjob action='create' name='local-<name>'`. Don't add them to `install-crons.sh`.

## Legend

| Column | Meaning |
|--------|---------|
| **Name** | Cron job name (matches `cronjob action='list'`) |
| **Schedule** | Crontab expression or human-friendly interval |
| **Type** | `LLM` = agent-driven (uses tokens), `no_agent` = script-only ($0) |
| **Script** | Script file (relative to `~/.hermes/scripts/` or `~/.hermes-cortex/scripts/`) |
| **Deliver** | Where output is sent |
| **Orch?** | `yes` = only on orchestrators (Moses, Esther), `—` = all agents |

---

## HIGH FREQUENCY

| Name | Schedule | Type | Script / Prompt | Deliver | Orch? |
|------|----------|------|-----------------|---------|-------|
| `orch-bus-audit-watchdog` | `*/1 * * * *` | no_agent | `orch-bus-audit-watchdog.py` | Telegram | ✅ |
| `orch-bus-forwarder-sync` | `*/2 * * * *` | no_agent | `orch-bus-forwarder.py` | origin | ✅ |
| `orch-bus-recover-timeouts` | `*/5 * * * *` | no_agent | `orch-bus-recover-timeouts.sh` | origin | ✅ |
| `orch-bus-confirmation-poller` | `every 10m` | no_agent | `orch-bus-message-tracker.py` | local | ✅ |
| `orch-bus-confirmation-alert` | `every 60m` | no_agent | `orch-bus-message-tracker-alert.sh` | origin | ✅ |
| `workflow-dispatcher` | `*/1 * * * *` | no_agent | `workflow-dispatcher.py` | local | — |
| `workflow-router` | `*/1 * * * *` | no_agent | `workflow-router.py` | local | — |
| `orch-fleet-watchdog` | `*/5 * * * *` | no_agent | `orch-fleet-watchdog.py` | Telegram | yes |
| `remediation-sensor` | `*/5 * * * *` | no_agent | `remediation-sensor.py` | local | — |
| `service-recovery` | `*/5 * * * *` | no_agent | `service-recovery.py` | origin | — |
| `workflow-sla-watchdog` | `*/5 * * * *` | no_agent | `workflow-sla-watchdog.py` | origin | — |
| `agent-apply-fixes` | `*/10 * * * *` | no_agent | `agent-apply-fixes.py` | local | — |
| `agent-remediate-apply` | `*/10 * * * *` | no_agent | `agent-remediate-apply.py` | origin | — |
| `cron-quality-watchdog` | `*/10 * * * *` | no_agent | `cron-quality-watchdog.py` | origin | — |
| `inbox-flag` | `*/10 * * * *` | no_agent | `inbox-flag.py` | local | — |
| `inbox-sensor` | `*/10 * * * *` | no_agent | `inbox-sensor.py` | local | — |
| `agent-inbox-workday` | `0 9-17 * * 1-5` | LLM | deepseek-v4-flash Agent Bus processing | origin | — |
| `inbox-depth-watchdog` | `*/1 * * * *` | no_agent | `inbox/inbox-depth-watchdog.sh` | local | — |
| `system-alert-watchdog` | `*/30 * * * *` | no_agent | `system-alert-watchdog.py` | origin | — |
| `swap-refresh` | `0 5 * * *` | no_agent | `swap-refresh.py` | origin | — |
| `agent-ip-submission` | `*/30 * * * *` | no_agent | `agent-ip-submission.sh` | origin | — |
| `agent-inbox-evening` | `0 18,20,22 * * 1-5` | LLM | deepseek-v4-flash Agent Bus processing | origin | — |
| `agent-fixer-workday` | `0 9-17 * * 1-5` | LLM | deepseek-v4-flash auto-remediation (auto-remediation skill) | origin | — |
| `agent-fixer-evening` | `0 18,20,22 * * 1-5` | LLM | deepseek-v4-flash auto-remediation (auto-remediation skill) | origin | — |
| `agent-fixer-overnight` | `0 3 * * 1-5` | LLM | deepseek-v4-flash auto-remediation (auto-remediation skill) | origin | — |
| `langfuse-health-watchdog` | `0 * * * *` | no_agent | `langfuse-health-watchdog.py` | origin | — |

## DAILY

| Name | Schedule | Type | Script / Prompt | Deliver | Orch? |
|------|----------|------|-----------------|---------|-------|
| `agent-daily-bible-reading` | `0 1 * * *` | no_agent | `agent-daily-bible-reading.py` (local qwen2.5-coder:3b) | origin | — |
| `agent-inbox-overnight` | `0 3 * * 1-5` | LLM | deepseek-v4-flash Agent Bus processing | origin | — |
| `threat-pipeline` | `0 5 * * *` | no_agent | `nginx-threat-pipeline.sh` | origin | — |
|| `agent-gbrain-doctor` | `0 6 * * *` | no_agent | `agent-gbrain-doctor.sh` | origin | — |
| `local-agent-daily-news-brief` | `0 7 * * *` | LLM | deepseek-v4-flash news briefing | Telegram | local |
| `model-health-watchdog` | `0 7 * * *` | no_agent | `model-health-watchdog.py` | origin | — |
| `upwork-job-scanner` | `0 8 * * *` | LLM | deepseek-v4-flash Upwork scanner | Telegram | — |
| `local-agent-daily-system-brief` | `0 9 * * *` | LLM | deepseek-v4-flash system briefing | Telegram | local |
| `orch-health-report-weekday` | `0 9-18 * * 1-5` | no_agent | `orch-health-report.py` | origin | yes |
| `local-agent-daily-finance-brief` | `0 18 * * 1-5` | LLM | deepseek-v4-flash finance briefing | Telegram | local |
| `memory-to-brain-sync` | `0 */6 * * *` | no_agent | `memory-to-brain-sync.py` | local | — |
| `governance-auditor` | `0 */6 * * *` | no_agent | `governance-auditor.py` | origin | — |
| `agent-learning-collector` | `0 */6 * * *` | no_agent | `agent-learning-collector.py` | local | — |
| `scoring-activity-watchdog` | `0 14,20 * * *` | no_agent | `scoring-activity-watchdog.py` | origin | — |
| `secret-leak-watchdog` | `0 */4 * * *` | no_agent | `secret-leak-watchdog.py` | origin | — |
| `orch-skill-lifecycle` | `0 4 * * *` | LLM | `orch-skill-lifecycle` skill | origin | — |
| `hermes-update` | `23 22 * * *` | no_agent | `hermes-update.sh` | local | — |
| `hermes-cortex-sync` | `33 22 * * *` | no_agent | `hermes-cortex-sync.sh` | origin | — |
| `llm-judge-scorer-weekday` | `0 12,20 * * 1-5` | no_agent | `llm-judge-scorer.py` | local | — |
| `skill-report-process` | `0 3 * * *` | no_agent | `process-skill-reports.py` | origin | — |

## WEEKLY / INFREQUENT

| Name | Schedule | Type | Script / Prompt | Deliver | Orch? |
|------|----------|------|-----------------|---------|-------|
| `llm-judge-scorer-weekend` | `0 22 * * 0,6` | no_agent | `llm-judge-scorer.py` | local | — |
| `memory-pruning` | `0 4 * * 1` | LLM | deepseek-v4-flash memory consolidation | origin | — |
| `session-cache-build` | `0 5 * * 1` | no_agent | `session_cache.py` | origin | — |
| `harvest-lessons` | `0 5 * * 1` | no_agent | `harvest-lessons.sh` | origin | — |
| `skill-miner` | `0 6 * * 1` | no_agent | `skill_miner.py` | origin | — |
| `local-agent-agents-doc-audit` | `0 7 * * 1` | LLM | deepseek-v4-flash doc audit | origin | local |
| `agent-weekly-loop-eval` | `0 9 * * 1` | LLM | deepseek-v4-flash loop governance eval | origin | — |
| `skill-report-request` | `0 2 * * 1` | no_agent | `request-skill-reports.sh` | origin | yes |
| `offline-code-index` | `0 5 * * 0` | no_agent | `offline_code_index_cron.sh` | local | — |
| `gbrain-update-sync` | `0 2 * * 0` | no_agent | `gbrain-update-sync.sh` | origin | — |
| `gbrain-nightly-dream` | `0 3 * * 6` | no_agent | `gbrain-nightly-dream.sh` | origin | — |
| `orch-health-report-saturday` | `0 11,17 * * 6` | no_agent | `orch-health-report.py` | origin | yes |
| `local-ai-hot-topics-news` | `0 7 * * 1,3,5` | LLM | deepseek AI news briefing | origin | local |
| `agents-md-prune-scan` | `0 4 * * 1-6` | no_agent | `agents-md-prune-scan.py` | local | — |
| `agents-md-prune-apply` | `30 4 * * 1-6` | LLM | deepseek-v4-flash prune application | origin | — |
| `skill-evaluate` | `0 9 * * 2` | LLM | deepseek-v4-flash skill evaluation | origin | — |
| `auto-save-sessions` | `every 360m` | no_agent | `auto-save-sessions.py` | local | — |

---

## Orchestrator-only summary

These crons run only on Moses and Esther (defined by `IS_ORCHESTRATOR=true`):

| Cron | Schedule | Type |
|------|----------|------|
| `orch-fleet-watchdog` | `*/5 * * * *` | no_agent |
| `orch-health-report-weekday` | `0 9-18 * * 1-5` | no_agent |
| `orch-health-report-saturday` | `0 11,17 * * 6` | no_agent |
| `skill-report-request` | `0 2 * * 1` | no_agent |

## Local-only summary

These crons run only on the machine where they were created (not shared to peers):

| Cron | Schedule | Type |
|------|----------|------|
| `local-agent-daily-news-brief` | `0 7 * * *` | LLM |
| `local-agent-daily-system-brief` | `0 9 * * *` | LLM |
| `local-agent-daily-finance-brief` | `0 18 * * 1-5` | LLM |
| `local-agent-agents-doc-audit` | `0 7 * * 1` | LLM |
| `local-ai-hot-topics-news` | `0 7 * * 1,3,5` | LLM |

---

## Maintenance

When changing a cron schedule, update this file in the same commit. The change flow is:

1. `cronjob action='update' job_id=<id> schedule='<new>'`
2. Update the row in this table
3. Commit both changes together

---

**See also:** [`docs/cron-format-standard.md`](cron-format-standard.md) — required output format for all LLM-driven crons.

### Notes

- `orch-bus-recover-timeouts` — **silent below 50** recoveries/tick. Routine visibility timeouts are normal; threshold was 10 before DLQ auto-archive fix. See [`agent-bus-setup.md`](agent-bus-setup.md#dlq-maintenance) for baselines.
- `inbox-depth-watchdog` — monitors inbox backlog depth; alerts on buildup.
- All `orch-*` crons run only on orchestrators (Moses/Esther).
