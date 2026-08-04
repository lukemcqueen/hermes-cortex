# Fleet Reference (Luke's Deployment)

> **⚠️ FOUR HARD RULES — Every Agent Must Follow**
>
> **RULE 1: USE LOOP GOVERNANCE ALWAYS**
> Every code/config/cron change REQUIRES: `begin_change` → work → `cycle_query` → `feedback_accept/override` → `end_change`. No exceptions.
>
> **RULE 2: SHARE IMPROVEMENTS TO THE PUBLIC REPO**
> Every improvement you make that benefits other agents MUST go into the `hermes-cortex` repo.
>
> **RULE 3: DOCUMENTATION IS NOT OPTIONAL**
> Every change includes doc updates. If another agent would be confused without reading an updated doc, the doc must be updated before the governance lock is released.
>
> **RULE 4: CLEAN UP AFTER YOURSELF**
> If you rename a cron, update BOTH the `create_cron` call AND the uninstall array in the same commit. Run `fix-cron-duplicates.py` before closing any cycle that touched install scripts.

---

## Agent Type Reference

Every agent in the fleet falls into one of three types. This determines which install scripts apply, what crons they run, and what the doctor validates.

| Capability | Moses (orch) | Esther (orch) | Joseph | Kustos | Gisu | Titus |
|------------|-------------|---------------|--------|--------|------|-------|
| **Role** | Primary orchestrator | Backup orchestrator | Web/infra server | Security server | Operations server | macOS dev machine |
| **Platform** | Linux | Linux | Linux | Linux | Linux | macOS |
| **sudo** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
|| **cronjob MCP tool** | ✅ | ✅ | ❌ (partial) | ❌ | ❌ | ❌ (see note) |
| **Bus mode** | `both` (server + poll) | `both` (server + poll) | `poll` | `poll` | `poll` | `push_only` |
| **Postgres access** | ✅ (direct) | ✅ (direct) | ❌ | ❌ | ❌ | ❌ |
| **Install scripts** | `install-crons.sh` + `install-orch-crons.sh` | same | `install-crons.sh` only | same | same | same |
| **Local bus daemon** | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **nginx** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Has Ollama** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Has gbrain** | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |

> **Note on cronjob MCP tool availability:** Most non-orchestrator agents do not have the cronjob tool in any context. The macOS dev-agent (Titus) has it when running direct user sessions (Telegram DM, CLI) but not in cron/auto-remediation contexts. When running under a restricted toolset (e.g. cron), all non-orchestrator agents should route cron requests through Moses using the [cron-request-protocol](skills/devops/cron-request-protocol/SKILL.md).

### What this means for cron installs

| Action | Orchestrators (Moses/Esther) | All other agents |
|--------|------------------------------|------------------|
| Run `install-crons.sh` | ✅ Creates all `agent-*` + bare crons | ✅ Creates all `agent-*` + bare crons |
| Run `install-orch-crons.sh` | ✅ Creates `orch-*` crons (bus, fleet, health) | ❌ Guard blocks — exits with info message |
| Run `cortex-doctor.py` | ✅ Validates all crons including `orch-*` | ✅ Validates only `agent-*` + bare crons, skips `orch-*` |
| Create cron manually | ✅ Has `cronjob` MCP tool | ❌ Must request via inbox or edit `jobs.json` directly |

### Cron naming convention (enforced)

Every cron name MUST start with a group prefix. No bare names:

| Prefix | Scope | Install script | Doctor validates | Runs on |
|--------|-------|---------------|-----------------|---------|
| `orch-*` | Orchestrator-only | `install-orch-crons.sh` | `parse_orch_crons()` | Moses, Esther |
| `agent-*` | All agents | `install-crons.sh` | `parse_expected_crons()` | All agents |
| `local-*` | This machine only | Manual `cronjob create` | Silently excluded by doctor | This machine only |

**Rules:**
- Every `create_cron` name MUST have a matching entry in the same file's uninstall array
- After any cron rename or addition, run:
  ```bash
  python3 ~/hermes-cortex/ops/scripts/manage/fix-cron-duplicates.py
  ```
  Zero issues = arrays are in sync.

---

## Current Cron State (61 jobs)

### Orchestrator-only (`orch-*`) — 12 crons

| Name | Schedule | Type | Script | Deliver |
|------|----------|------|--------|---------|
| `orch-bus-audit-watchdog` | `*/1 * * * *` | no_agent | `orch-bus-audit-watchdog.py` | Telegram |
| `orch-bus-recover-timeouts` | `*/5 * * * *` | no_agent | `orch-bus-recover-timeouts.sh` | origin |
| `orch-bus-confirmation-poller` | `every 10m` | no_agent | `orch-bus-confirmation-poller.py` | local |
| `orch-bus-confirmation-alert` | `*/15 * * * *` | no_agent | `orch-bus-confirmation-alert.sh` | Telegram |
| `orch-bus-forwarder-sync` | `*/2 * * * *` | no_agent | `orch-bus-forwarder.py` | origin |
| `orch-fleet-watchdog` | `*/5 * * * *` | no_agent | `orch-fleet-watchdog.py` | Telegram |
| `orch-health-report-weekday` | `0 9-18 * * 1-5` | no_agent | `orch-health-report.py` | origin |
| `orch-health-report-saturday` | `0 11,17 * * 6` | no_agent | `orch-health-report.py` | origin |
| `orch-skill-lifecycle` | `0 4 * * *` | LLM | (skill) | origin |

### All-agent crons (`agent-*`) — 44 crons

These run on every agent in the fleet. Created by `install-crons.sh`.

| Name | Schedule | Type | Script | Deliver |
|------|----------|------|--------|---------|
| `agent-fixer-workday` | `0 9-17 * * 1-5` | LLM | auto-remediation skill | origin |
| `agent-fixer-evening` | `0 18,20,22 * * 1-5` | LLM | auto-remediation skill | origin |
| `agent-fixer-overnight` | `0 3 * * 1-5` | LLM | auto-remediation skill | origin |
| `agent-remediation-sensor` | `*/5 * * * *` | no_agent | `agent-remediation-sensor.py` | local (runs only where IS_SERVER=true) |
| `agent-remediate-apply` | `*/10 * * * *` | no_agent | `agent-remediate-apply.py` | origin |
| `agent-message-handler` | `*/5 * * * *` | no_agent | `agent-message-handler.py` | local |
| `agent-bus-failover-watchdog` | `*/5 * * * *` | no_agent | `agent-bus-failover-watchdog.py` | Telegram |
| `agent-service-recovery` | `*/5 * * * *` | no_agent | `agent-service-recovery.py` | origin |
| `agent-system-alert-watchdog` | `*/30 * * * *` | no_agent | `agent-system-alert-watchdog.py` | origin |
| `agent-hermes-update` | `23 22 * * *` | no_agent | `agent-hermes-update.sh` | local |
| `agent-hermes-cortex-sync` | `33 22 * * *` | no_agent | `agent-hermes-cortex-sync.sh` | origin |
| `agent-memory-to-brain-sync` | `0 */6 * * *` | no_agent | `agent-memory-to-brain-sync.py` | local |
| `agent-governance-auditor` | `0 */6 * * *` | no_agent | `agent-governance-auditor.py` | origin |
| `agent-learning-collector` | `0 */6 * * *` | no_agent | `agent-learning-collector.py` | local |
| `agent-cron-quality-watchdog` | `*/10 * * * *` | no_agent | `agent-cron-quality-watchdog.py` | origin |
| `agent-scoring-activity-watchdog` | `0 14,20 * * *` | no_agent | `agent-scoring-activity-watchdog.py` | origin |
| `agent-model-health-watchdog` | `0 7 * * *` | no_agent | `agent-model-health-watchdog.py` | origin |
| `agent-langfuse-health-watchdog` | `0 * * * *` | no_agent | `langfuse-health-watchdog.py` | origin |
| `agent-memory-pruning` | `0 4 * * 1` | LLM | — | origin |
| `agent-session-cache-build` | `0 5 * * 1` | no_agent | `session_cache.py` | origin |
| `agent-daily-bible-reading` | `0 1 * * *` | no_agent | `agent-daily-bible-reading.py` | origin |
| `agent-gbrain-nightly-dream` | ~~`0 3 * * 6`~~ | ~~no_agent~~ | ~~`agent-gbrain-nightly-dream.sh`~~ | ~~origin~~ | ⚠️ STALE/REMOVED 2026-08-02 — gbrain decommissioned; no consumer (verified) |
| `agent-gbrain-update-sync` | ~~`0 2 * * 0`~~ | ~~no_agent~~ | ~~`agent-gbrain-update-sync.sh`~~ | ~~origin~~ | ⚠️ STALE/REMOVED 2026-08-02 — obsolete with gbrain binary uninstall |
| `agent-nginx-threat-pipeline` | `0 5 * * *` | no_agent | `nginx-threat-pipeline.sh` | origin |
| `agent-ip-submission` | `*/30 * * * *` | no_agent | `agent-ip-submission.sh` | origin |
| `agent-offline-code-index` | `0 5 * * 0` | no_agent | `offline_code_index_cron.sh` | local |
| `agent-llm-judge-scorer-weekday` | `0 12,20 * * 1-5` | no_agent | `llm-judge-scorer.py` | local |
| `agent-llm-judge-scorer-weekend` | `0 22 * * 0,6` | no_agent | `llm-judge-scorer.py` | local |
| `agent-agents-md-prune-scan` | `0 4 * * 1-6` | no_agent | `agents-md-prune-scan.py` | local |
| `agent-agents-md-prune-apply` | `30 4 * * 1-6` | LLM | — | origin |
| `agent-auto-save-sessions` | `every 360m` | no_agent | `agent-auto-save-sessions.py` | local |

### Local-only crons (`local-*`) — 5 crons

These run only on this machine. NOT in repo installers.

| Name | Schedule | Type | Deliver |
|------|----------|------|---------|
| `local-agent-daily-news-brief` | `0 7 * * *` | LLM | Telegram |
| `local-agent-daily-system-brief` | `0 9 * * *` | LLM | Telegram |
| `local-agent-daily-finance-brief` | `0 18 * * 1-5` | LLM | Telegram |
| `local-agent-agents-doc-audit` | `0 7 * * 1` | LLM | origin |
| `local-ai-hot-topics-news` | `0 7 * * 1,3,5` | LLM | origin |

### Manually-created LLM crons — 4 crons

These run on this machine but use `agent-*` naming. Not in repo installers (intentional — they were created before the naming convention was enforced).

| Name | Schedule | Type | Deliver |
|------|----------|------|---------|
| `agent-bus-workday` | `0 9-17 * * 1-5` | LLM | origin |
| `agent-bus-evening` | `0 18,20,22 * * 1-5` | LLM | origin |
| `agent-bus-overnight` | `0 3 * * 1-5` | LLM | origin |
| `upwork-job-scanner` | `0 8 * * *` | LLM | Telegram |

### Other crons — 8 crons

| Name | Schedule | Type | Script | Deliver |
|------|----------|------|--------|---------|
| `cron-quality-watchdog` | `*/10 * * * *` | no_agent | `agent-cron-quality-watchdog.py` | origin |
| `remediation-sensor` | `*/5 * * * *` | no_agent | `agent-remediation-sensor.py` | local |
| `service-recovery` | `*/5 * * * *` | no_agent | `agent-service-recovery.py` | origin |
| `system-alert-watchdog` | `*/30 * * * *` | no_agent | `agent-system-alert-watchdog.py` | origin |
| `memory-to-brain-sync` | `0 */6 * * *` | no_agent | `agent-memory-to-brain-sync.py` | local |
| `governance-auditor` | `0 */6 * * *` | no_agent | `agent-governance-auditor.py` | origin |
| `hermes-update` | `23 22 * * *` | no_agent | `agent-hermes-update.sh` | local |
| `hermes-cortex-sync` | `33 22 * * *` | no_agent | `agent-hermes-cortex-sync.sh` | origin |
| `threat-pipeline` | `0 5 * * *` | no_agent | `nginx-threat-pipeline.sh` | origin |
| `model-health-watchdog` | `0 7 * * *` | no_agent | `agent-model-health-watchdog.py` | origin |
| `langfuse-health-watchdog` | `0 * * * *` | no_agent | `langfuse-health-watchdog.py` | origin |
| `gbrain-nightly-dream` | ~~`0 3 * * 6`~~ | ~~no_agent~~ | ~~`agent-gbrain-nightly-dream.sh`~~ | ~~origin~~ | ⚠️ STALE/REMOVED 2026-08-02 — gbrain decommissioned |
| `gbrain-update-sync` | ~~`0 2 * * 0`~~ | ~~no_agent~~ | ~~`agent-gbrain-update-sync.sh`~~ | ~~origin~~ | ⚠️ STALE/REMOVED 2026-08-02 — gbrain decommissioned |
| `memory-pruning` | `0 4 * * 1` | LLM | — | origin |
| `offline-code-index` | `0 5 * * 0` | no_agent | `offline_code_index_cron.sh` | local |
| `llm-judge-scorer-weekday` | `0 12,20 * * 1-5` | no_agent | `llm-judge-scorer.py` | local |
| `llm-judge-scorer-weekend` | `0 22 * * 0,6` | no_agent | `llm-judge-scorer.py` | local |
| `session-cache-build` | `0 5 * * 1` | no_agent | `session_cache.py` | origin |
| `agent-daily-bible-reading` | `0 1 * * *` | no_agent | `agent-daily-bible-reading.py` | origin |
| `agent-ip-submission` | `*/30 * * * *` | no_agent | `agent-ip-submission.sh` | origin |
| `agents-md-prune-scan` | `0 4 * * 1-6` | no_agent | `agents-md-prune-scan.py` | local |
| `agents-md-prune-apply` | `30 4 * * 1-6` | LLM | — | origin |
| `secret-leak-watchdog` | `0 */4 * * *` | no_agent | `agent-secret-leak-watchdog.py` | origin |
| `scoring-activity-watchdog` | `0 14,20 * * *` | no_agent | `agent-scoring-activity-watchdog.py` | origin |
| `auto-save-sessions` | `every 360m` | no_agent | `agent-auto-save-sessions.py` | local |
| `agent-learning-collector` | `0 */6 * * *` | no_agent | `agent-learning-collector.py` | local |
| `agent-session-mine` | `0 2 * * *` | no_agent | `agent-session-mine-cron.py` | local |
| `stale-ref-watchdog` | `0 5 * * *` | no_agent | `manage/agent-stale-ref-watchdog.sh` | origin |
| `agent-swap-refresh` | `0 5 * * *` | no_agent | `agent-swap-refresh.py` | origin |
| `orch-clean-health-queue` | `*/10 * * * *` | no_agent | `orch-clean-health-queue.py` | origin |
| `local-fleet-dispatch-collector` | `every 15m` | no_agent | `local-fleet-dispatch-collector.sh` | origin |

---

## Migration history

**Jul 2026 — Bus cron duplication bug:** The `orch-bus-*` rename (commit d247880) created new `orch-bus-*` crons but did NOT remove the old `bus-*` crons. 5 duplicate pairs. Fixed Jul 21:
1. Created `ops/scripts/manage/fix-cron-duplicates.py` — detects + removes duplicates
2. Aligned `install-orch-crons.sh` create sections and uninstall arrays to `orch-bus-*`
3. Removed dead `agent-apply-fixes` create_cron block
4. Added AGENTS.md Rule 3 (doc) and Rule 4 (cleanup) to prevent recurrence
5. Added install-array-sync check to change-checklist Phase 0

**Detection script:** `fix-cron-duplicates.py` is safe to run on ALL agent types (Linux/macOS, with/without sudo, with/without cron MCP tool). It falls back to direct `jobs.json` patching when the hermes CLI is unavailable.

---

## All timestamps in KST (UTC+9)

All monitoring scripts output timestamps in Seoul time.

---

## Security: Secret Leak Prevention

**The single most common agent security mistake:** passing secrets as literal strings in `terminal()` commands.

```bash
# ❌ WRONG — secret is visible in tool call metadata
curl -u "admin:supersecret" https://api.example.com

# ✅ RIGHT — only file path appears in the command string
curl -u "admin:$(cat ~/.password_file)" https://api.example.com
```

**Three layers of defense:**
1. **SOUL.md principle** — every agent has "Never Print Secrets"
2. **Pre-commit audit** — `secret-leak-detector.sh` scans staged scripts
3. **Runtime watchdog** — `secret-leak-watchdog` (no_agent, every 4h)

---

## Model Fallback Chain

Configured in `~/.hermes/config.yaml` — standard chain: primary API → free API → local Ollama.
See `config-template.yaml` for the canonical setup.
