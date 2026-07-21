# Cron Schedules — Hermes Cortex

> **Canonical schedule reference.** Every cron job in the fleet, its schedule, type, script/prompt, and delivery.
>
> **Naming convention:** All crons MUST use group prefixes. No bare names.

| Column | Meaning |
|--------|---------|
| **Name** | Cron job name (matches `cronjob action='list'`) |
| **Schedule** | Crontab expression or human-friendly interval |
| **Type** | `LLM` (uses tokens) or `no_agent` (script-only, $0) |
| **Script** | Script file (relative to `~/.hermes/scripts/`) |
| **Deliver** | Where output is sent |
| **Scope** | `orch` = orchestrator-only, `agent` = all agents, `local` = this machine |

## Orchestrator-only (`orch-*` prefix)

| Name | Schedule | Type | Script | Deliver |
|------|----------|------|--------|---------|
| `orch-bus-audit-watchdog` | `*/1 * * * *` | no_agent | `orch-bus-audit-watchdog.py` | Telegram |
| `orch-bus-recover-timeouts` | `*/5 * * * *` | no_agent | `orch-bus-recover-timeouts.sh` | origin |
| `orch-bus-confirmation-poller` | `every 10m` | no_agent | `orch-bus-message-tracker.py` | local |
| `orch-bus-confirmation-alert` | `*/15 * * * *` | no_agent | `orch-bus-message-tracker-alert.sh` | Telegram |
| `orch-bus-forwarder-sync` | `*/2 * * * *` | no_agent | `orch-bus-forwarder.py` | origin |
| `orch-fleet-watchdog` | `*/5 * * * *` | no_agent | `orch-fleet-watchdog.py` | Telegram |
| `orch-health-report-weekday` | `0 9-18 * * 1-5` | no_agent | `orch-health-report.py` | origin |
| `orch-health-report-saturday` | `0 11,17 * * 6` | no_agent | `orch-health-report.py` | origin |
| `orch-skill-lifecycle` | `0 4 * * *` | LLM | (orch-skill-lifecycle skill) | origin |

## All-agent (`agent-*` prefix)

| Name | Schedule | Type | Script / Skill | Deliver |
|------|----------|------|----------------|---------|
| `agent-fixer-workday` | `0 9-17 * * 1-5` | LLM | auto-remediation skill | origin |
| `agent-fixer-evening` | `0 18,20,22 * * 1-5` | LLM | auto-remediation skill | origin |
| `agent-fixer-overnight` | `0 3 * * 1-5` | LLM | auto-remediation skill | origin |
| `agent-remediation-sensor` | `*/5 * * * *` | no_agent | `remediation-sensor.py` | local |
| `agent-remediate-apply` | `*/10 * * * *` | no_agent | `agent-remediate-apply.py` | origin |
| `agent-message-handler` | `*/5 * * * *` | no_agent | `agent-message-handler.py` | local |
| `agent-service-recovery` | `*/5 * * * *` | no_agent | `service-recovery.py` | origin |
| `agent-system-alert-watchdog` | `*/30 * * * *` | no_agent | `system-alert-watchdog.py` | origin |
| `agent-cron-quality-watchdog` | `*/10 * * * *` | no_agent | `cron-quality-watchdog.py` | origin |
| `agent-langfuse-health-watchdog` | `0 * * * *` | no_agent | `langfuse-health-watchdog.py` | origin |
| `agent-model-health-watchdog` | `0 7 * * *` | no_agent | `model-health-watchdog.py` | origin |
| `agent-secret-leak-watchdog` | `0 */4 * * *` | no_agent | `secret-leak-watchdog.py` | origin |
| `agent-ip-submission` | `*/30 * * * *` | no_agent | `agent-ip-submission.sh` | origin |
| `agent-hermes-update` | `23 22 * * *` | no_agent | `hermes-update.sh` | local |
| `agent-hermes-cortex-sync` | `33 22 * * *` | no_agent | `hermes-cortex-sync.sh` | origin |
| `agent-memory-to-brain-sync` | `0 */6 * * *` | no_agent | `memory-to-brain-sync.py` | local |
| `agent-governance-auditor` | `0 */6 * * *` | no_agent | `governance-auditor.py` | origin |
| `agent-learning-collector` | `0 */6 * * *` | no_agent | `agent-learning-collector.py` | local |
| `agent-daily-bible-reading` | `0 1 * * *` | no_agent | `agent-daily-bible-reading.py` | origin |
| `agent-threat-pipeline` | `0 5 * * *` | no_agent | `nginx-threat-pipeline.sh` | origin |
| `agent-gbrain-nightly-dream` | `0 3 * * 6` | no_agent | `gbrain-nightly-dream.sh` | origin |
| `agent-gbrain-update-sync` | `0 2 * * 0` | no_agent | `gbrain-update-sync.sh` | origin |
| `agent-scoring-activity-watchdog` | `0 14,20 * * *` | no_agent | `scoring-activity-watchdog.py` | origin |
| `agent-session-cache-build` | `0 5 * * 1` | no_agent | `session_cache.py` | origin |
| `agent-offline-code-index` | `0 5 * * 0` | no_agent | `offline_code_index_cron.sh` | local |
| `agent-llm-judge-scorer-weekday` | `0 12,20 * * 1-5` | no_agent | `llm-judge-scorer.py` | local |
| `agent-llm-judge-scorer-weekend` | `0 22 * * 0,6` | no_agent | `llm-judge-scorer.py` | local |
| `agent-memory-pruning` | `0 4 * * 1` | LLM | (prompt) | origin |
| `agent-auto-save-sessions` | `every 360m` | no_agent | `auto-save-sessions.py` | local |
| `agent-stale-ref-watchdog` | `0 5 * * *` | no_agent | `manage/stale-ref-watchdog.sh` | origin |
| `agent-upwork-job-scanner` | `0 8 * * *` | LLM | (prompt) | Telegram |
| `agent-agents-md-prune-scan` | `0 4 * * 1-6` | no_agent | `agents-md-prune-scan.py` | local |
| `agent-agents-md-prune-apply` | `30 4 * * 1-6` | LLM | (prompt) | origin |
| `agent-bus-workday` | `0 9-17 * * 1-5` | LLM | (prompt) | origin |
| `agent-bus-evening` | `0 18,20,22 * * 1-5` | LLM | (prompt) | origin |
| `agent-bus-overnight` | `0 3 * * 1-5` | LLM | (prompt) | origin |

## Local-only (`local-*` prefix)

| Name | Schedule | Type | Deliver |
|------|----------|------|---------|
| `local-agent-daily-news-brief` | `0 7 * * *` | LLM | Telegram |
| `local-agent-daily-system-brief` | `0 9 * * *` | LLM | Telegram |
| `local-agent-daily-finance-brief` | `0 18 * * 1-5` | LLM | Telegram |
| `local-agent-agents-doc-audit` | `0 7 * * 1` | LLM | origin |
| `local-ai-hot-topics-news` | `0 7 * * 1,3,5` | LLM | origin |

## Unprefixed (legacy, NOT to be replicated)

| Name | Schedule | Type | Script | Deliver |
|------|----------|------|--------|---------|
| `orch-clean-health-queue` | `*/10 * * * *` | no_agent | `orch-clean-health-queue.py` | origin |
| `local-fleet-dispatch-collector` | `every 15m` | no_agent | `local-fleet-dispatch-collector.sh` | origin |

---

**Migration:** All crons renamed to `agent-*` prefix Jul 21 2026. Old bare names are replaced. Run `fix-cron-duplicates.py` to verify.
