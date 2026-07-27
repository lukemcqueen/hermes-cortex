# Session Lessons — 2026-07-23

## Correction 1: Survey Before Creation Enforcement

**Signal:** User said "Why didn't you survey before action? ... I need you to make survey before action PERMANENT"

**What happened:** Created 2 new crons (`local-cron-cost-report`, `local-trace-quality-watchdog`) without surveying existing `agent-scoring-activity-watchdog` which could have absorbed both features.

**Root cause:** `cortex-preflight` had survey steps as suggestions, not enforcement. SOUL.md ritual had survey-before-action as step 5 in a prose list — easy to skip.

**Fix applied:**
1. SOUL.md MANDATORY SESSION-START RITUAL reordered to numbered 10-step sequence. survey-before-action is step 8 with explicit text: "BEFORE creating any new cron, script, mechanism, or file: search_files() with 3+ different terms AND call cronjob(action='list'). Extend before create."
2. Two new crons deleted. Existing `agent-scoring-activity-watchdog` extended with cost + trace quality checks.
3. Template, Moses, Esther, Gisu, Joseph, Kustos, Titus, and Operator profiles all updated.

**Guardrail language:** "A new creation when an existing extension was possible is a structural violation. Document the survey result in your feedback note."

## Correction 2: Always-Skills Ordering (Session-Start Ritual)

**Signal:** User asked "Did you load all skills?" after work had started without them. Then: "You must permanently fix why you cut corners"

**What happened:** Called `begin_change` immediately after `skill_view('task-start')` without loading the remaining 7 always skills.

**Root cause:** Old ritual said "The task-start skill loads survey-before-action, agent-flow, reasoning-patterns..." This is false. task-start describes the sequence but does NOT load the skills. Each requires its own `skill_view()` call.

**Fix applied:**
1. SOUL.md ritual rewritten as numbered tool calls 1-10. begin_change is now step 10.
2. Added explicit exception: Principle 2 (Be Proactive) applies AFTER ritual is complete. Ritual governs task start; Principle 2 governs mid-task discovery.
3. Seven agent profiles + template + active copy all updated.

**Guardrail language:** "begin_change() is the LAST step. The governance lock opens only after all context is loaded and the survey is complete."

## Correction 3: Propagate to ALL Agents

**Signal:** "anything else need to be updated for other agents?" + "and don't forget the 'dev agents' like titus"

**What happened:** Updated Moses and Esther SOUL.md but initially missed Gisu, Joseph, Kustos, Titus, and Operator.

**Root cause:** Assumed other agents had different SOUL.md structures. After checking, 5 of 7 agents had the same numbered format and needed the same update.

**Fix applied:** Added MANDATORY SESSION-START RITUAL to all 5 remaining agents. Also created `docs/agent-architecture.md` — generic role model covering orchestrator, backup orch, server agent, and dev agent.

**Guardrail language:** SOUL.md updates propagate to the template AND all agent profiles in the same commit. Template is single source of truth.

## Technical Discovery 1: Langfuse API Limitations

The Langfuse REST API does NOT support PATCH on traces — you cannot rename or add tags to existing traces. The only way to enrich traces after creation is via the ingestion API's `trace-update` event type, but the discriminator schema is strict and undocumented.

**Practical workaround:** Use scores (name/value pairs) as the enrichment mechanism. Scores are filterable in the Langfuse UI and can be queried via `/api/public/scores`. The LLM judge scorer already uses scores for helpfulness, clarity, depth, and overall.

## Technical Discovery 2: Cost Tracking Patches Missing

The `install-cron-cost-tracking.py` patches the Hermes scheduler at `~/.hermes/hermes-agent/cron/scheduler.py` and tools at `~/.hermes/hermes-agent/tools/cronjob_tools.py`. These patches are lost after every `hermes update` because Hermes replaces its source directory.

**Deployment:** `python3 ~/.hermes-cortex/scripts/install-cron-cost-tracking.py --force`

**Verification:** `python3 ~/.hermes-cortex/scripts/install-cron-cost-tracking.py --status` — all 8 hooks must show OK.

**Cost data location:** `~/.hermes/cron/cron-costs.db` (SQLite WAL mode). Schema: `cron_runs` table with `job_id`, `input_tokens`, `output_tokens`, `estimated_cost_usd`, `model`, `provider`, `status`.

## Technical Discovery 3: Fleet Data Collection Pipeline

The fleet data pipeline is already deployed and does NOT need a new cron:
1. **Each agent** → `agent-learning-collector` (no_agent, every 6h) sends "Learning Report" to `inbox_moses` via PGMQ
2. **Moses** → `orch-skill-lifecycle` (LLM, daily 4am) reads inbox and processes all reports

This pipeline covers sessions, skills, and learnings from all fleet agents. No additional cron or collection mechanism needed.
