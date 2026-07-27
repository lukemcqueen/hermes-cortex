# Session Lessons: 2026-07-23 — Prompt Response Visibility + Ordering Enforcement

## Corrections Captured

### 1. Always skills must be loaded before begin_change

**The mistake:** Loaded task-start, assumed it loaded the always skills, called begin_change as step 2. The always skills (agent-flow, reasoning-patterns, reflexion-check, change-checklist, survey-before-action, cortex-preflight, agent-contract) were never loaded via individual skill_view() calls.

**The fix:** SOUL.md MANDATORY SESSION-START RITUAL rewritten as numbered steps 1-8. begin_change is step 8, not step 2. The old wording ("task-start loads these skills") was replaced with explicit numbered skill_view() calls for each always skill.

**Files changed:**
- docs/templates/SOUL.md — canonical template
- profiles/personal/agent-profiles/moses/SOUL.md — Moses profile
- profiles/personal/agent-profiles/esther/SOUL.md — Esther profile
- ~/.hermes/SOUL.md — active copy

**Principle:** task-start describes the sequence but does not execute it. Each skill requires its own skill_view() call.

### 2. Langfuse Observability Pipeline (full stack assembled)

The full observability pipeline now includes:

| Layer | Component | Status |
|-------|-----------|--------|
| Trace capture | Langfuse v3.206.0 + Hermes plugin | 722 traces/7 days |
| Cost tracking | cron-costs.db + scheduler patches | All 8 hooks deployed |
| Quality scoring | LLM judge scorer (qwen2.5-coder:3b) | Scores posted to Langfuse |
| Quality alerts | trace-quality-watchdog | Alerts if overall < 4/10 |
| Output quality | cron-quality-watchdog | Every 10 min, no_agent |
| Cost reporting | cron-cost-report | Weekly to Telegram |
| Token analytics | config show_token_analytics=true | Visible in UI |
| Session recording | browser.record_sessions=true | Sessions searchable |

**Specific fixes applied:**
1. Cost tracking patches re-installed (all 8 were MISS after Hermes update)
2. Judge scorer delivery changed from "local" to "origin" (was dead-letter)
3. show_token_analytics=true, show_cost=true in config
4. browser.record_sessions=true
5. local-cron-cost-report: weekly cost summary cron
6. local-trace-quality-watchdog: quality alert cron (2x daily)
7. setup-fleet-langfuse.sh: script to wire fleet agents to shared Langfuse

### 3. Config.yaml is protected

Cannot use patch/write_file on ~/.hermes/config.yaml. Must use:
hermes config set <key> <value>

### 4. Langfuse trace API limitations

- PATCH is not allowed on traces (405 Method Not Allowed)
- trace-update via ingestion API fails (invalid discriminator)
- Cannot rename traces or add tags after creation
- CAN add scores (name/value pairs) which appear in Langfuse UI
- Scores are the correct enrichment mechanism
