# Skills Session Manager v2 — Design

> **Status:** Design doc. Parts implemented: `skills-state.json` (per-session,
> 2026-08-01) + per-session marker files (`state/skills-loaded/<session_id>`)
> now replace the single shared binary `.skills-loaded` marker — see
> `plugins/governance-enforcer/README.md`. Remaining proposals below are open.

> **Problem:** Agents forget to load always-section skills on session start, forget task-relevant skills mid-session, and skip mandatory execution steps (docs, push, verify). The original binary `.skills-loaded` marker (single shared file) was fragile and provided no guidance.

## Root Cause Analysis

### Why the Current System Fails

1. **Binary marker** — `.skills-loaded` is a boolean file. It can't answer "which skills are loaded" or "were on_task skills loaded too"
2. **Session ID linkage** — The marker is session-scoped (`session:{id}`), which is good, but the session ID concept is opaque to the agent. Agents don't know their session ID, can't verify the marker themselves, and have no feedback loop
3. **No task-awareness** — The marker only tracks 8 always-section skills. It doesn't know about on_task skills, task classification, or workflow type
4. **Zero agent guidance** — When the enforcer blocks a tool, it says "load skills first" but doesn't say *which* skills. The agent must remember all 8 names
5. **Marker cleared by context** — Post-commit hooks, end_change, and session compaction can reset the marker state, forcing agents to reload skills they already loaded

### The Real Agent Memory Problem

An agent's "memory" across turns is its context window. When context compacts:
- The agent knows it loaded skills (it was in the transcript)
- But the compacted summary may not mention which skills
- The enforcer blocks with a generic message
- The agent falls back to loading all 8, which works but wastes 10+ tool calls per session start

## Design: Skills Session Manager v2

### Component A: Structured Skills State File

Replace `.skills-loaded` with `~/.hermes-cortex/state/skills-state.json`:

```json
{
  "session_id": "20260730_111126_9fa6031f",
  "manifest_hash": "sha256-a1b2c3...",
  "always_skills": {
    "task-start": { "loaded_at": "2026-07-30T11:11:30Z", "verified": true },
    "agent-flow": { "loaded_at": "2026-07-30T11:11:35Z", "verified": true },
    "reasoning-patterns": { "loaded_at": "2026-07-30T11:11:32Z", "verified": true },
    "reflexion-check": { "loaded_at": "2026-07-30T11:11:33Z", "verified": true },
    "change-checklist": { "loaded_at": "2026-07-30T11:11:34Z", "verified": true },
    "survey-before-action": { "loaded_at": "2026-07-30T11:11:38Z", "verified": true },
    "cortex-preflight": { "loaded_at": "2026-07-30T11:11:39Z", "verified": true },
    "agent-contract": { "loaded_at": "2026-07-30T11:11:40Z", "verified": true }
  },
  "task_type": "enterprise",
  "on_task_skills": {
    "change-checklist": { "loaded_at": "2026-07-30T11:11:34Z", "verified": true }
  },
  "workflow_state": {
    "survey_done": true,
    "change_started": true,
    "test_verified": false,
    "docs_updated": false,
    "change_closed": false
  },
  "last_updated": "2026-07-30T11:20:00Z"
}
```

**Benefits over binary marker:**
- Agent can read it to know exactly what's loaded — no guessing
- Enforcer can verify individual skill presence, not just "all or nothing"
- Workflow state tracks progress through the execution cycle
- manifest_hash detects when skills.yaml changes and suggests reload

### Component B: Session Continuity Rules

| Event | Skills State Action |
|-------|---------------------|
| New session starts | Clear state, require fresh load |
| begin_change() | No action — skills state is session-level |
| end_change() | No action — skills state is session-level |
| git commit | No action — hooks run in same session context |
| context compaction | No action — state file survives in RAM+disk |
| Session timeout / new session ID | Clear state |

**The invariant:** Skills state is a SESSION concern, not a CYCLE concern. begin_change/end_change govern individual code changes, not the agent's knowledge base.

### Component C: Enforcer — Smart Tool Blocking

The enforcer currently blocks ALL conditional write tools with a generic "skills not loaded" message. Replace with tiered blocking:

#### Tier 1: Read-Only Tools (NEVER blocked)
- `read_file`, `search_files`, `session_search`, `web_search`, `web_extract`
- `skill_view`, `skills_list`, `tool_search`, `tool_describe`
- `cronjob(action=list)` — listing is read-only
- `todo()` — reading is read-only
- `inbox_read`, `inbox_watch`

#### Tier 2: Write Tools (blocked if skills not loaded)
- `write_file`, `patch`, `execute_code`, `terminal(write commands)`, `cronjob(create/update/remove)`, `skill_manage`
- When blocked: provide **specific guidance** on which skills to load

#### Tier 3: Conditional (warning, not block)
- `terminal(read-only commands like curl, grep, python3 script.py)`
- These should work even without skills loaded — removes friction

### Component D: Helpful Block Messages

**Current (bad):**
```
WRITE TOOLS BLOCKED — SKILLS MUST BE LOADED FIRST
```

**Proposed (good):**
```
🛑 Write tool blocked — session skills not fully loaded.

Required always-section skills — load all:
  1. skill_view('task-start')
  2. skill_view('agent-flow')
  3. skill_view('reasoning-patterns')
  4. skill_view('reflexion-check')
  5. skill_view('change-checklist')
  6. skill_view('survey-before-action')
  7. skill_view('cortex-preflight')
  8. skill_view('agent-contract')

✅ Already loaded: [none | task-start, agent-flow, ...]

💡 Your recent tool calls suggest: "enterprise" workflow
   Recommended on_task skills: change-checklist, survey-before-action
```

This turns the blocker into a **navigational aid** — the agent doesn't have to remember what to load, it just follows the list.

### Component E: Task Type Detection

The enforcer can infer task type from recent tool calls:

| Tool Call Sequence | Inferred Type | Suggested On_Task Skills |
|-------------------|---------------|-------------------------|
| read_file + search_files + web_search | research | survey-before-action |
| patch/write_file + terminal build | enterprise | change-checklist, change-test-loop |
| terminal(failing command) + read_file | debug | root-cause-debugging |
| write_file(.md) | writing | documentation-scope |

This is a **best-effort suggestion**, not enforcement. The agent still classifies via agent-flow; the enforcer just helps if the agent forgot.

### Component F: Pre-Flight Checklist State

Track the execution lifecycle through the skills state:

```json
"workflow_state": {
  "skills_loaded": true,
  "task_classified": false,
  "survey_run": false,
  "change_started": false,
  "change_verified": false,
  "docs_updated": false,
  "change_scored": false,
  "change_pushed": false
}
```

The enforcer can check: "Before end_change(), verify at least: change_started → change_verified → change_scored → change_pushed."

This is a **soft check** — it warns but doesn't block. Blocking would be too invasive and prevent legitimate partial work.

### Component G: Cron Session Smart Bootstrap

Current cron bootstrap reads skills.yaml and pre-creates `.skills-loaded` for ALL always skills. This is correct for crons but the mechanism can be improved:

1. Read the cron's `attached_skills` from the cron definition
2. Pre-load only those skills (not all 8) into the state
3. Mark them as "cron_bootstrap: true" so the agent knows they were auto-loaded

## Implementation Plan

### Phase 1: Core Infrastructure
1. Replace `.skills-loaded` with `skills-state.json`
2. Add session continuity rules to enforcer (end_change doesn't clear)
3. Tiered blocking: read tools free, write tools blocked, guidance provided
4. Helpful block messages with skill names

### Phase 2: Task Awareness
1. Task type detection in enforcer
2. On_task skill suggestions in block messages
3. Workflow state tracking in skills-state.json

### Phase 3: Soft Checklist
1. Pre-flight checklist state in skills-state.json
2. end_change verification warning
3. Cron smart bootstrap with skill selection

### Phase 4: Polish
1. Documentation update in AGENTS.md and SOUL.md
2. Test with cron sessions
3. Test with multi-turn sessions
4. Test with context compaction

## Risk Analysis

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| JSON state file gets corrupted | Low | Write atomically (temp file + rename) |
| Session ID collision | Very Low | UUID v4 session IDs are unique |
| Agent ignores helpful messages | Medium | Messages are still guidance, not enforcement. The tool block is the enforcement. |
| Too many state file writes | Low | Write only on skill load, not on every tool call |
| Cron sessions broken | Medium | Test thoroughly — cron bootstrap already works, this extends it |
| Agent relies on block messages instead of learning | Low | The messages reduce frustration, not create dependency |

## Decisions (Reviewed & Approved by Luke on 2026-07-30)

1. **Read-tool exemption** → ✅ **Yes.** read_file, search_files, session_search, web_search, web_extract, skill_view, skills_list are all exempt from the skills gate.

2. **Workflow state enforcement** → ✅ **Warn only.** enforcer warns but does not block when end_change is called without verify/docs/push.

3. **Task type inference** → ✅ **Both.** agent-flow declares explicitly as primary path. Enforcer infers from tool call patterns as fallback with lower confidence.

4. **Phase 1 scope** → ✅ **Components A + B + C + D.** State file, session continuity, smart blocking, helpful messages. Phase 2 = task detection + checklist.
