create_cron "agent-fixer-workday" "0 8,20 * * 1-5" \
  "session-active-guard.py" \
  "SESSION GUARD: the session-active guard output is injected as context. If it says ACTIVE, an interactive session is running — SKIP this tick entirely: do not load skills, do not begin_change, do not touch the repo. Reply only: [SILENT]. Proceed only when the guard says IDLE.

Respond in English. Run the auto-remediation workflow using the auto-remediation skill. Load the skill first, check for errors, fix, report.

PUSHBACK CONTRACT (SOUL Principle 5): before any destructive or irreversible remediation (delete, overwrite, config/state change, permission change), challenge it — if the fix is wrong, harmful, or better done differently, do NOT execute; record the objection (record_issue) and deliver the objection as the report. Default to no-op when in doubt.

OUTPUT POLICY (HARD RULE — overrides everything above):
- Deliver ONLY when there is a REAL issue: a failure, a blocked/failed workflow, a critical alert, or something you actually fixed or restored.
- NEVER deliver status or ops narration: no \"no issues\", \"all clear\", \"system healthy\", \"nothing to report\", idle/skipped notices, scan/assessment summaries, governance/cycle/cleanup reports, or \"here's my report\".
- If nothing is actionable, reply with EXACTLY this single line and nothing else: [SILENT]
- A real issue = a short, factual report of WHAT failed and WHAT you did. No preamble, no closing narrative." \
  "auto-remediation" \
  "terminal,file,web" \
  "telegram:${TELEGRAM_HOME_CHANNEL}" \
  "" \
  "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

create_cron "agent-remediation-sensor" "*/5 * * * *" \
  "agent-remediation-sensor.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"



# ── 2. System Health Monitoring ──────────────────────────────
printf "\\n${CYAN}  2. System Health Monitoring${RESET}\\\n"

create_cron "agent-system-alert-watchdog" "*/30 * * * *" \
  "agent-system-alert-watchdog.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

create_cron "agent-service-recovery" "*/5 * * * *" \
  "agent-service-recovery.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── 3. Knowledge & Memory ────────────────────────────────────
printf "\\n${CYAN}  3. Knowledge & Memory${RESET}\\\n"

create_cron "agent-memory-to-brain-sync" "0 */6 * * *" \
  "agent-memory-to-brain-sync.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# mycortex knowledge brain sync — every 15 min (design D4: per-host, NOT
# orchestrator-only). Syncs this host's registered sources into the mycortex
# schema. no_agent watchdog pattern: silent on success, output only on
# failure. Jittered per host inside the wrapper (stable hostname-derived
# offset); advisory lock makes multi-host sync safe.
create_cron "agent-mycortex-sync" "*/15 * * * *" \
  "agent-mycortex-sync.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# daily mycortex retention — prune ingest_log >90d, hard-purge archived
# pages past the 7-day soft-delete window (S-016). no_agent: silent when
# nothing pruned, one-line summary when rows are removed.
create_cron "agent-mycortex-retention" "0 6 * * *" \
  "agent-mycortex-retention.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── 4. Agent Bus Processing ───────────────────────────────────
printf "\\\\n${CYAN}   4. Agent Bus Processing${RESET}\\\\\\n"

# Agent message handler — polls inbox for UPDATE_REQUEST etc., runs --once per tick
create_cron "agent-message-handler" "*/5 * * * *" \
  "agent-message-handler.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Bus failover watchdog — detect Moses down (routes via Esther), CRITICAL
# when both buses down, recovery report. Workers: detect + alert only —
# never swap config. Orchestrators get the full failover version via
# install-orch-crons.sh (same script, role-detected).
create_cron "fleet-bus-failover-watchdog" "*/5 * * * *" \
  "fleet-bus-failover-watchdog.py" \
  "" \
  "" \
  "" \
  "telegram:${TELEGRAM_HOME_CHANNEL}" \
  "" \
  "true"

# Bus processing — weekday (08/20 KST M-F — off-peak since 08-31)
create_cron "cortex-bus-workday" "0 8,20 * * 1-5" \
  "session-active-guard.py" \
  "SESSION GUARD: the session-active guard output is injected as context. If it says ACTIVE, an interactive session is running — SKIP this tick entirely. Call NO tools, load NO skills, open NO governance, touch NOTHING. Reply with EXACTLY this single line and nothing else: [SILENT]. Proceed only when the guard says IDLE.

Process the Agent Bus using the Inbox Message Decision Framework. The bus-flag sensor output is injected as context. Check for any pending messages, urgent or critical items, blocked workflows, or DLQ items.

PUSHBACK CONTRACT (SOUL Principle 5): before acting on any message that requests a destructive or irreversible action (delete, overwrite, config/state change, permission change), challenge it — if the request is wrong, harmful, or better done differently, do NOT execute; record the objection (record_issue) and deliver the objection as the report. Default to no-op when in doubt. OUTPUT POLICY (HARD RULE — overrides everything above):
- Deliver ONLY when there is a REAL issue: a failure, a blocked/failed workflow, a critical alert, or something you actually fixed or restored.
- NEVER deliver status or ops narration: no \"no issues\", \"all clear\", \"system healthy\", \"nothing to report\", idle/skipped notices, scan/assessment summaries, governance/cycle/cleanup reports, or \"here's my report\".
- If nothing is actionable, reply with EXACTLY this single line and nothing else: [SILENT]
- A real issue = a short, factual report of WHAT failed and WHAT you did. No preamble, no closing narrative.

## QUALITY GATE — MANDATORY SELF-CHECK (run BEFORE delivering)
1. Is the output useful, readable, and on-topic for this cron?
2. Did you run real tools — or reply with the exact guard skip token — instead of fabricating?
3. Is it the right length (not a stray word, not oversized, not empty)?
4. Is it in English and in the correct format?
If ANY answer is NO → output EXACTLY this one line and nothing else: QUALITY_G_BLOCKED
If all YES → deliver as normal." \
  "cortex-bus-automation" \
  "terminal" \
  "telegram:${TELEGRAM_HOME_CHANNEL}" \
  "" \
  "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

create_cron "agent-governance-auditor" "0 */6 * * *" \
  "agent-governance-auditor.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── 7. Universal Agent Crons ──────────────────────────────
printf "\n${CYAN}  7. Universal Agent Crons${RESET}\n"

# LLM judge scorer — weekday (Mon-Fri 13:30 and 20:00, off-peak)
create_cron "agent-llm-judge-scorer-weekday" "30 13,20 * * 1-5" \
  "agent-llm-judge-scorer.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# LLM judge scorer — weekend (Sat-Sun 22:00)
create_cron "agent-llm-judge-scorer-weekend" "0 22 * * 0,6" \
  "agent-llm-judge-scorer.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Model health watchdog (daily 07:00)
create_cron "agent-model-health-watchdog" "0 7 * * *" \
  "agent-model-health-watchdog.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Langfuse health + ClickHouse merge watchdog (silent when healthy, every hour)
create_cron "agent-langfuse-health-watchdog" "0 * * * *" \
  "agent-langfuse-health-watchdog.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Governance MCP health watchdog (M-001/M-002, 2026-08-18 write-deadlock
# mitigation): probes every configured MCP server (spawn + list_tools) every
# 5 min + scans mcp-stderr for import crashes. Silent when healthy; CRITICAL
# alert when loop-governance/tasks go down (ALL WRITES BLOCKED). no_agent.
create_cron "agent-mcp-health-watchdog" "*/5 * * * *" \
  "agent-mcp-health-watchdog.py" \
  "" \
  "" \
  "" \
  "telegram:${TELEGRAM_HOME_CHANNEL}" \
  "" \
  "true"

# Loop-gov DB-lock watchdog (2026-09-30, security-audited): learns that
# begin_change fails with "database is locked" when ANY loop-gov daemon holds
# an open/uncommitted write txn on loop-governance.db (post-deploy leaks
# included — the mtime heuristic alone misses these). Restarts the fd-holding
# daemons so the gateway supervisor respawns them clean; re-probes; alerts if a
# NON-loop-gov holder is found. Silent when the DB is writable. no_agent.
create_cron "agent-loop-gov-lock-watchdog" "*/5 * * * *" \
  "agent-loop-gov-lock-watchdog.py" \
  "" \
  "" \
  "" \
  "telegram:${TELEGRAM_HOME_CHANNEL}" \
  "" \
  "true"

# Bus outbox retry sweep (2026-08-27): re-sends messages queued by
# bus_send when the bus was unreachable (~/.steadfaste-fleet/bus-retry/).
# Watchdog pattern — silent when the outbox is empty; alerts on
# quarantine / persistent bus-down. no_agent. Runs the lib module
# directly (no wrapper): lib/ is on sys.path[0] as the script's dir.
create_cron "agent-bus-retry-sweep" "*/15 * * * *" \
  "lib/bus_outbox.py" \
  "Bus outbox retry sweep — re-sends messages queued by bus_send when the bus was unreachable. Silent when the outbox is empty; alerts on quarantine or persistent bus-down." \
  "" \
  "" \
  "telegram:${TELEGRAM_HOME_CHANNEL}" \
  "" \
  "true"

# Daily swap refresh (no_agent — cycles swapoff/swapon, safety-guarded:
# only runs when RAM > swap_used + 1 GB; silent no-op otherwise).
# Requires NOPASSWD sudo for /sbin/swapoff, /sbin/swapon (docs/cron-job-recipes.md).
create_cron "agent-swap-refresh" "0 5 * * *" \
  "agent-swap-refresh.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"


# Agent remediation apply (no_agent script — reads sensor output, applies deterministic fixes)
create_cron "agent-scoring-activity-watchdog" "0 14,20 * * *" \
  "agent-scoring-activity-watchdog.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# PENDING-cycle watchdog (O5-S1) — governance leak detection every 6h
# (no_agent: mirrors fleet_doctor/checks.py PENDING rules; silent when clean)
create_cron "agent-pending-cycle-watchdog" "0 */6 * * *" \
  "agent-pending-cycle-watchdog.py" \
  "" \
  "" \
  "" \
  "telegram:${TELEGRAM_HOME_CHANNEL}" \
  "" \
  "true"

# Deploy drift-audit (O5-S2) — deployed-vs-repo drift detection daily 07:00
# (no_agent: mirrors fleet_doctor/checks.py deploy-content + stale-deploy
#  rules; silent when clean/unchanged — StateTracker-gated)
create_cron "agent-deploy-drift-audit" "0 7 * * *" \
  "agent-deploy-drift-audit.py" \
  "" \
  "" \
  "" \
  "telegram:${TELEGRAM_HOME_CHANNEL}" \
  "" \
  "true"

# Review-queue stale-sweep (O5/G-5) — daily 01:45, no_agent: auto-closes
# STOP/auto-accepted cycles older than 3d (clean outcome notes), surfaces
# LOOP/MOVE ON/hard-fail/PENDING; silent when clean, alerts once per anomaly
# (state-deduped) via the home channel. Script: agent-review-queue-sweep.py.
create_cron "agent-review-queue-sweep" "45 1 * * *" \
  "agent-review-queue-sweep.py" \
  "" \
  "" \
  "" \
  "telegram:${TELEGRAM_HOME_CHANNEL}" \
  "" \
  "true"




# Session embedding cache rebuild (weekly Monday 05:00 — universal, loop-governance)
create_cron "agent-session-cache-build" "0 5 * * 1" \
  "agent-session_cache.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Daily agent card generation (06:00)

# Replaced by orch-skill-lifecycle (install-orch-crons.sh, 04:00 daily)

# Agent learning collector — every 6h: collect skills delta + lessons + session stats from ALL agents
create_cron "agent-learning-collector" "0 */6 * * *" \
  "agent-learning-collector.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Agent session mine — overnight: mines sessions and dumps lessons into ~/brain/lessons/
create_cron "agent-session-mine" "0 2 * * *" \
  "agent-session-mine-cron.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Cron output quality gate (every 10 min, silent when healthy — universal)
create_cron "agent-cron-quality-watchdog" "*/10 * * * *" \
  "agent-cron-quality-watchdog.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Consecutive-failure escalation (every 5 min, silent when healthy — universal)
# Counts last_status=error per job; after 3 consecutive failures alerts AND
# pauses the cron so it stops re-firing. Fixes the 1053-run gap: nothing used
# to count failures or pause them — the 2026-08-30..09-14 push-metrics outage
# burned 1000+ ticks before anyone noticed. Transient failures stay silent.
create_cron "agent-cron-failure-watchdog" "*/5 * * * *" \
  "agent-cron-failure-watchdog.py" \
  "" \
  "" \
  "" \
  "telegram:${TELEGRAM_HOME_CHANNEL}" \
  "" \
  "true"

# ── 8. Deployment-Specific Crons ─────────────────────────────
# These are specific to Luke's deployment but tracked in the
# repo so install-crons.sh --force can recreate them.
# (All crons listed in the AGENTS.md reference table.)

printf "${CYAN}  8. Deployment-Specific Crons${RESET}\n"

# Daily Hermes Agent self-update
create_cron "agent-offline-code-index" "0 5 * * 0" \
  "agent-offline-code-index.sh" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Daily steadfaste-fleet sync and update
create_cron "agent-steadfaste-fleet-sync" "33 22 * * *" \
  "agent-steadfaste-fleet-sync.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Weekly memory pruning and consolidation (deepseek — needs Hermes memory tool)
create_cron "agent-memory-pruning" "0 4 * * 1" \
  "" \
  "Consolidate Hermes agent memory and project agent instructions. Read MEMORY.md, USER.md from the active profile and project roots. Consolidate into compact pointers. Prune stale entries. Keep under 2,200 chars.

## TIMEZONE — READ FIRST
The header timestamp must use the host configured timezone, NOT a hardcoded label. Run \`date '+%Y-%m-%d %H:%M %Z'\` (or \`date '+%H:%M %Z'\` for time-only) and use its exact output — the timezone comes from HERMES_TIMEZONE / system local time. The KST in the example below is illustrative; substitute whatever %Z returns.

## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values.
Everything else stays: dashes, colons, spacing, line breaks.

memory-pruning (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Memory read: MEMORY.md at 1,850 chars (12 entries), USER.md at 890 chars (8 entries)
- Found 3 stale entries (dated 2026-06-15 or earlier, no longer referenced in recent sessions)
- Found 2 verbose entries that could be consolidated

Phase 2 — Pruning applied: Removed 3 stale entries (185 chars freed)
- Consolidated 2 tool-quirk entries into 1 compact pointer
- Merged 2 user-preference entries into 1
- Final MEMORY.md: 1,420 chars (within 2,200 limit)

Phase 3 — USER.md: No changes needed — all 8 entries still current

Result: Memory consolidated. 3 stale entries pruned, 2 merged. Under limit.

📊 deepseek-v4-flash (deepseek) | \$0.006/run ≈ \$2.18/mo

If nothing to report: output exactly [SILENT]" \
  "" "" "telegram:${TELEGRAM_HOME_CHANNEL}" "" "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

# Auto-save sessions every 6 hours
create_cron "agent-auto-save-sessions" "every 360m" \
  "agent-auto-save-sessions.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"




create_cron "agent-nginx-threat-pipeline" "0 5 * * *" \
  "agent-nginx-threat-pipeline.sh" \
  "" \
  "" \
  "" \
  "telegram:${TELEGRAM_HOME_CHANNEL}" \
  "" \
  "true"

# Agent IP submission processor (every 30 min) — universal
create_cron "agent-ip-submission" "*/30 * * * *" \
  "agent-ip-submission.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Agent metrics push (every 5 min, no_agent) — pushes system metrics to VictoriaMetrics
create_cron "agent-push-metrics" "every 5m" \
  "agent-push-metrics.sh" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# ── AGENTS.md auto-trim: daily scan + LLM apply (M-Sa) ──
# Phase 1: deterministic scan — silent when clean, JSON report when candidates found
create_cron "agent-agents-md-prune-scan" "0 4 * * 1" \
  "agent-agents-md-prune-scan.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Phase 2: LLM review + apply — reads scan output via context_from
create_cron "agent-agents-md-prune-apply" "30 4 * * 1" \
  "" \
  "Review the AGENTS.md pruning scan report injected below (via context_from=agents-md-prune-scan).
If candidates exist and look correct, apply them by running:
  python3 ~/.steadfaste-fleet/scripts/agents-doc-audit.py --repo ~/steadfaste-fleet --prune --apply
Then commit and push the changes.
If no candidates (empty context) or you disagree with the recommendations, stay silent.

## TIMEZONE — READ FIRST
The header timestamp must use the host configured timezone, NOT a hardcoded label. Run \`date '+%Y-%m-%d %H:%M %Z'\` (or \`date '+%H:%M %Z'\` for time-only) and use its exact output — the timezone comes from HERMES_TIMEZONE / system local time. The KST in the example below is illustrative; substitute whatever %Z returns.

## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values.
Everything else stays: dashes, colons, spacing, line breaks.

agents-md-prune-apply (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Scan: 12 candidates found
Phase 2 — Review: accepted 10 / rejected 2
Phase 3 — Apply: 10 sections moved to docs/

📊 deepseek-v4-flash (opencode-zen) | \$0.006/run ≈ \$0.18/mo

If nothing to apply: output exactly [SILENT]" \
  "documentation-scope" "" "telegram:${TELEGRAM_HOME_CHANNEL}" \
  "" "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

# ── 9. Skill Collection (universal — all agents) ──────────
printf "${CYAN}  9. Skill Collection Pipeline${RESET}\n"

# Collect custom skills every 6h — scans skills dirs, reports to the orchestrator inbox
#  (Restored: send-skill-report — rewritten to use /api/pgmq/send with Bearer/Basic auth.
#  Now resolves CORTEX_BUS_URL → CORTEX_BUS_FALLBACK_URL, supports Basic auth for nginx proxy.
#  Fixed: was using deprecated /api/send endpoint. See ops/scripts/manage/send-skill-report.py)
#  Agent inbox migrated to Agent Bus (PGMQ). Collect-agent-skills.sh
#  Note: agent-collect-skills.sh script still on disk for manual debugging,
#  but the cron is removed — agent-learning-collector handles all collection.
echo ""
printf "${CYAN}━━━ Summary ━━━${RESET}\n"
if $DRY_RUN; then
  info "Would create: ${WOULD_CREATE} cron job(s)"
  info "Would skip: ${SKIPPED} existing job(s)"
  info "Run without --dry-run to apply"
else
  info "Created: ${CREATED} new cron job(s)"
  info "Skipped: ${SKIPPED} existing job(s)"
  if [[ "$FAILED" -gt 0 ]]; then
    warn "Failed: ${FAILED} cron job(s) — check warnings above"
  fi
fi
echo ""
info "Cron jobs are stored in: ${CRON_JOBS_FILE}"
if [[ "$CREATED" -gt 0 && -n "$HERMES_CMD" ]]; then
  info "Verify with: ${HERMES_CMD} cron list"
fi

# Exit with error if any crons failed
if [[ "$FAILED" -gt 0 ]]; then
  exit 1
fi

# Secret leak watchdog (every 4h, scans cron outputs for leaked credentials)
create_cron "agent-secret-leak-watchdog" "0 */4 * * *" \
  "agent-secret-leak-watchdog.py" \
  "Scans cron outputs and session files for printf/echo credential leaks" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Security posture check (hourly, fleet-wide): fail2ban service + jails,
# firewall ban set, SSH key-only policy, nginx jail logpath starvation,
# 24h brute-force volume. Silent when healthy (watchdog pattern); prints a
# report + exit 1 on any gap → delivered to the origin channel.
create_cron "agent-security-posture-check" "17 * * * *" \
  "agent-security-posture-check.sh" \
  "Hourly security posture verification: fail2ban active + jails (sshd, nginx-http-auth, nginx-badbots), firewall ban set, SSH key-only, nginx jail logpaths, brute-force volume. Silent when healthy." \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Stale ref watchdog (daily, scans deployment layers for broken symlinks/paths)
create_cron "agent-stale-ref-watchdog" "0 5 * * *" \
  "manage/agent-stale-ref-watchdog.sh" \
  "stale-ref-watchdog -- nightly stale-path scan across all deploy layers" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Daily bible reading (no_agent script — reads SOUL.md, calls deepseek API
# internally, appends entry + brain page; canonical pattern per
# skills/spiritual-disciplines/agent-daily-bible-reading/SKILL.md)
create_cron "agent-daily-bible-reading" "0 1 * * *" \
  "agent-daily-bible-reading.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# No-verify audit — no-agent script checks for --no-verify commits every 60m
create_cron "agent-no-verify-audit" "*/10 * * * *" \
  "manage/agent-no-verify-audit.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── Correction→Guardrail Recidivism Scan (weekly) ─────────
# P0-1: scans LOCAL state.db for user corrections, classifies, checks guardrail
# registry, flags unguarded + recidivism. Runs on EVERY agent (each host's
# state.db holds that agent's own corrections). Non-orchestrator agents
# forward a condensed report to inbox_orchestrator so the orchestrator can fold
# per-agent recidivism into enforcer work. no_agent — stdout is the report.
create_cron "agent-session-correction-scan" "0 22 * * 0" \
  "manage/agent-session-correction-scan.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# ── Unannounced honeypot probe (M7.1) — low-frequency, no_agent ──
# Thin slice: the script records a placeholder probe / reports the loop; the
# real honeypot content is an orchestrator-authored follow-up. Silent when
# the loop is empty (watchdog pattern). Weekly Sunday 03:00 = low frequency.
create_cron "agent-unannounced-probe" "0 3 * * 0" \
  "agent-unannounced-probe.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# ── Auto-prune old-format cron names ──
# Remove legacy crons that lack the agent- prefix when an agent- replacement exists.
# These accumulate from older installs that used bare names (e.g. 'cron-quality-watchdog'
# before the convention became 'agent-cron-quality-watchdog').
prune_old_cron_names() {
  local jobs_file="${HERMES_HOME:-$HOME/.hermes}/cron/jobs.json"
  local pruned=0
  if [[ ! -f "$jobs_file" ]]; then
    return 0
  fi

  while IFS=$'\t' read -r old_id old_name; do
    # Derive the agent-prefixed name from the old name
    local agent_name="agent-${old_name}"
    # Check if the agent-prefixed version exists as a SEPARATE cron entry
    if grep -q "\"name\": \"$agent_name\"" "$jobs_file" 2>/dev/null; then
      echo "  Pruning duplicate: $old_name → (replaced by $agent_name)"
      hermes cron remove "$old_id" 2>/dev/null || true
      pruned=$((pruned + 1))
    fi
  done < <(python3 -c "
import json, sys
path = '$jobs_file'
try:
    with open(path) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    sys.exit(0)
jobs = data.get('jobs', [])
agent_names = {j['name'] for j in jobs if j['name'].startswith('agent-')}
for j in jobs:
    name = j['name']
    # Skip agent-prefixed and local- prefixed crons
    if name.startswith('agent-') or name.startswith('local-'):
        continue
    # Check if an agent- version exists
    if f'agent-{name}' in agent_names:
        print(f'{j[\"id\"]}\t{name}')
" 2>/dev/null)

  if [[ $pruned -gt 0 ]]; then
    echo "  Pruned $pruned old-format cron name(s)"
  fi
}

prune_old_cron_names
