### Cron Jobs Reference

| Name | Type | Schedule | Purpose |
|------|------|----------|---------|
| remediation-sensor | no_agent | */5 * * * * | Detect system issues |
| inbox-flag | no_agent | */10 * * * * | Flag new bus messages (file-based fallback) |
| system-alert-watchdog | no_agent | */30 * * * * | Monitor system alerts |
| service-recovery | no_agent | */5 * * * * | Auto-recover services |
| memory-to-brain-sync | no_agent | 0 */6 * * * | Sync memory to gbrain |
| inbox-sensor | no_agent | */10 * * * * | Detect bus activity |
| hermes-update | no_agent | 23 22 * * * | Nightly Hermes update |
| gbrain-nightly-dream | no_agent | 0 3 * * 6 | Weekly gbrain dream |
| gbrain-update-sync | no_agent | 0 2 * * 0 | Weekly gbrain sync |
| hermes-cortex-sync | no_agent | 33 22 * * * | Nightly cortex sync |
| harvest-lessons | no_agent | 0 5 * * 1 | Weekly lesson harvest |
| memory-pruning | LLM+prompt | 0 4 * * 1 | Weekly memory prune |
| auto-save-sessions | no_agent | every 360m | Session persistence |
| agent-daily-bible-reading | no_agent | 0 1 * * * | Daily scripture reading |
| threat-pipeline | no_agent | 0 5 * * * | Daily nginx threat update |
| agent-daily-soul-refinement | LLM+skill | 0 23 * * * | Daily SOUL.md refinement |
| llm-judge-scorer-weekday | no_agent | 0 12,20 * * 1-5 | Weekday LLM evaluation |
| llm-judge-scorer-weekend | no_agent | 0 22 * * 0,6 | Weekend LLM evaluation |
| offline-code-index | no_agent | 0 5 * * 0 | Weekly offline code index |
| model-health-watchdog | no_agent | 0 7 * * * | Daily model health check |
| agent-bus | LLM+prompt | */2 * * * * | Process Agent Bus messages |
| agent-remediate-apply | no_agent | */10 * * * * | Apply remediation fixes |
| scoring-activity-watchdog | no_agent | 0 14,20 * * * | Monitor scoring activity |
| skill-miner | no_agent | 0 6 * * 1 | Weekly skill mining |
| agent-weekly-loop-eval | LLM+skill | 0 9 * * 1 | Weekly loop evaluation |
| agent-ip-submission | no_agent | */30 * * * * | Submit IP to threat service |
| agent-apply-fixes | no_agent | */10 * * * * | Apply fix markers |
| cron-quality-watchdog | no_agent | */10 * * * * | Monitor cron output quality |
| session-cache-build | no_agent | 0 5 * * 1 | Weekly session cache build |
| agents-md-prune-scan | no_agent | 0 4 * * 1-6 | Daily AGENTS.md prune scan |
| agents-md-prune-apply | LLM+prompt | 30 4 * * 1-6 | Daily AGENTS.md prune apply |
| governance-auditor | no_agent | 0 */6 * * * | Governance compliance check |
| collect-agent-skills | no_agent | 0 */6 * * * | Collect skill usage data |
| send-skill-report | no_agent | 30 */6 * * * | Send skill reports |
| langfuse-health-watchdog | no_agent | 0 * * * * | Langfuse ClickHouse health |
| inbox-depth-watchdog | no_agent | */1 * * * * | Monitor bus backlog depth |
| agent-fixer-workday | LLM+skill | 0 9-17 * * 1-5 | Auto-remediation workday |
| agent-fixer-evening | LLM+skill | 0 18,20,22 * * 1-5 | Auto-remediation evening |
| agent-fixer-overnight | LLM+skill | 0 3 * * 1-5 | Auto-remediation overnight |

> Moved from AGENTS.md by `agents-doc-audit.py --prune --apply`
> Date: 2026-07-15T19:30:43.849964+00:00
