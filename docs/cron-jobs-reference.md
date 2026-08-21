### Cron Jobs Reference

> **Note:** `local-*` prefixed crons are server-specific and maintained outside the repo installer. They are created directly via `cronjob action='create'`. See the `cron-job-management` skill for full naming conventions and when to use the installer vs local-only creation.
>
> **Canonical reference:** See [`cron-schedules.md`](cron-schedules.md) for the complete table including schedules, scripts, and delivery targets.

| Name | Type | Schedule | Purpose |
|------|------|----------|---------|
| agent-remediation-sensor | no_agent | */5 * * * * | Detect system issues. Runs only where IS_SERVER=true in ~/hermes-cortex/.env (server agents); other hosts no-op |
| agent-system-alert-watchdog | no_agent | */30 * * * * | Monitor system alerts |
| agent-service-recovery | no_agent | */5 * * * * | Auto-recover services |
| agent-memory-to-brain-sync | no_agent | 0 */6 * * * | Sync memory to mycortex |
| hermes-update | no_agent | 23 22 * * * | Nightly Hermes update |
| agent-mycortex-nightly-dream | ~~no_agent~~ | ~~0 3 * * 6~~ | ⚠️ STALE/REMOVED 2026-08-02 — legacy brain decommissioned; no consumer (verified) |
| agent-mycortex-update-sync | ~~no_agent~~ | ~~0 2 * * 0~~ | ⚠️ STALE/REMOVED 2026-08-02 — obsolete with mycortex binary uninstall |
| agent-hermes-cortex-sync | no_agent | 33 22 * * * | Nightly cortex sync |
| memory-pruning | LLM+prompt | 0 4 * * 1 | Weekly memory prune |
| agent-auto-save-sessions | no_agent | every 360m | Session persistence |
| agent-daily-bible-reading | LLM+skill | 0 1 * * * | Daily scripture reading |
| threat-pipeline | no_agent | 0 5 * * * | Daily nginx threat update |
| agent-daily-soul-refinement | LLM+skill | 14 23 * * * | Daily SOUL.md refinement |
| agent-llm-judge-scorer-weekday | no_agent | 30 13,20 * * 1-5 | Weekday LLM evaluation |
| agent-llm-judge-scorer-weekend | no_agent | 0 22 * * 0,6 | Weekend LLM evaluation |
| agent-offline-code-index | no_agent | 0 5 * * 0 | Weekly offline code index |
| agent-model-health-watchdog | no_agent | 0 7 * * * | Daily model health check |
| agent-remediate-apply | no_agent | */10 * * * * | Apply remediation fixes |
| agent-scoring-activity-watchdog | no_agent | 0 14,20 * * * | Monitor scoring activity |
| agent-weekly-loop-eval | LLM+skill | 0 9 * * 1 | Weekly loop evaluation |
| agent-ip-submission | no_agent | */30 * * * * | Submit IP to threat service |
| agent-cron-quality-watchdog | no_agent | */10 * * * * | Monitor cron output quality |
| session-cache-build | no_agent | 0 5 * * 1 | Weekly session cache build |
| agents-md-prune-scan | no_agent | 0 4 * * 1-6 | Daily AGENTS.md prune scan |
| agents-md-prune-apply | LLM+prompt | 30 4 * * 1-6 | Daily AGENTS.md prune apply |
| agent-governance-auditor | no_agent | 0 */6 * * * | Governance compliance check |
| langfuse-health-watchdog | no_agent | 0 * * * * | Langfuse ClickHouse health |
| agent-fixer-workday | LLM+skill | 0 9-17 * * 1-5 | Auto-remediation workday |
| agent-fixer-evening | LLM+skill | 0 19,20,22 * * 1-5 | Auto-remediation evening |
| agent-fixer-overnight | LLM+skill | 0 3 * * 1-5 | Auto-remediation overnight |
| agent-legacy-brain-doctor | ~~no_agent~~ | ~~5 6 * * *~~ | ⚠️ STALE/REMOVED 2026-08-02 — legacy brain decommissioned; mycortex replaces (`mycortex doctor`) |
| agent-message-handler | no_agent | */5 * * * * | Agent bus message handler |
| agent-secret-leak-watchdog | no_agent | 0 */4 * * * | Scan for leaked credentials |
| agent-stale-ref-watchdog | no_agent | 0 5 * * * | Check for stale file references |
| agent-learning-collector | no_agent | 0 */6 * * * | Collect skills delta + lessons |
|| agent-no-verify-audit | no_agent | every 60m | Check for --no-verify commits |
| orch-skill-report-request | no_agent | 0 2 * * 1 | Request skill reports from agents |
| orch-skill-evaluate | LLM+prompt | 0 9 * * 2 | Evaluate custom skills for upstreaming |
| orch-backlog-driver | LLM+skill | 0 8-22 * * * | Orchestrator backlog driver (F-023) |

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-15T19:30:43.849964+00:00
> Last updated: 2026-07-27
