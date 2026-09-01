---
name: task-start
version: 1.2.0
category: workflow
description: >-
  MANDATORY first action for every task. Bundles the complete
  pre-task sequence into one reference. Load this BEFORE any
  other tool call — it prescribes the exact sequence that
  follows.
pinned: true
aliases:
  - session-start-discipline
related_skills:
  - agent-flow
  - survey-before-action
  - change-checklist
  - reflexion-check
  - loop-governance
  - task-persistence
---

# Task Start — Mandatory First Action

**Nothing comes before this skill.** No tool calls, no file reads, no commands.
This is the first and only thing you do when a new task arrives.

## The Sequence

Execute these steps in order. Do not skip, batch, or defer any step.

### Step 1: Cache search
```python
mcp_loop_governance_cache_search(query="<the user's request>")
```
Learn from past cycles before starting work.

### Step 2: Begin governance
```python
mcp_loop_governance_begin_change(task_id="<short-name>", description="<what you are about to do>")
```
Mandatory before any code/config change. Write tools are blocked without this.

### Step 3: Load always skills
Call `skill_view(name)` for every skill listed in the `always` section of
`.hermes-cortex/skills.yaml` (or `skills.yaml` in the current working directory).

These skills define HOW you think and work — they are active context
for the entire task, not one-time loads. **Do not skip this step.**
(Formerly its own skill `session-start-discipline` — merged here 2026-08-20.)

**Marker mechanics:** the governance enforcer auto-creates a per-session
marker at `~/.hermes-cortex/state/skills-loaded/<session-id>` once all
always-section skills are loaded via actual `skill_view()` calls. Never
`touch` the marker — a bare file fails content verification. Concurrent
sessions each own their marker file, so no session can stomp another's
proof. If write tools are blocked with "session skills not fully loaded":
- The per-session loaded-set lives in the GATEWAY PROCESS's memory. If the
  set still holds all 7 (no gateway restart since you loaded them), ONE
  serial `skill_view(name='<any-always-skill>')` call re-triggers the
  auto-create (batching all loads in one turn does NOT trigger it — a
  serial extra call does).
- After a GATEWAY RESTART or a DEPLOY that changed a skill file (the marker
  pins a fingerprint of skill mtimes), the in-memory set is empty and the
  stored fingerprint is stale — you must re-load ALL 7 always-skills via
  `skill_view()` (they are read-only, so the gate does not block them);
  the 7th call regenerates the marker. This is the "7/7 loaded ✅ but still
  blocked" state — the message's ✅ reflects the current load, the block
  reflects the stale marker.

### Step 4: Load domain skills (new Phase 0a)

After classification but BEFORE begin_change, run `survey-before-action` Phase 0a — the operation-type × file-extension domain-skill mapping table. Load ALL matching skills. Discovery fallback: `skills_list(category=<domain>)`.

### Step 5: Select reasoning pattern
Load `agent-flow` and use its embedded reasoning-pattern table to choose:
- **Plan-Execute-Verify** (default) — write a plan, execute steps, verify each
- **ReAct** — debugging, exploration
- **Reflexion** — add to any pattern when quality is critical
- **Tree of Thoughts** — design decisions with trade-offs

State your choice: *"Using Plan-Execute-Verify with Reflexion check."*
(The former `reasoning-patterns` skill was folded into agent-flow 2026-08-20.)

### Step 6: Classify with agent-flow
Match the request against the 12 workflow patterns.
This determines toolset, output format, and checklist.

### Step 7: Load on-task skills
After classification, load every skill matching your classification from the
`on_task` section of `.hermes-cortex/skills.yaml`. Then call `skills_list()`
for the relevant category to discover skills not in the manifest.

### Step 8: Restore cross-session todos
```bash
~/.hermes-cortex/scripts/task-db.py pending
```
If items exist, restore them to the in-memory todo list:
```python
todo(todos=<json_items>, merge=true)
```
(From the former `session-start-discipline` skill — merged here 2026-08-20.)

### Step 9: Survey before action
Load `survey-before-action` and run its checklist BEFORE creating any file,
writing any code, or running any command. Search for existing resources first.
Its repo-specific pre-flight (git search, Hermes boundary, deploy verification —
formerly `cortex-preflight`) is embedded in the same skill since 2026-08-20.

### Step 10: Work
Execute the task using the loaded skills, following the chosen reasoning
pattern and the classified workflow pattern's checklist.

### Step 11: Reflexion check before delivery
After completing the work but BEFORE presenting results:
1. Load `reflexion-check` and run the seven-question audit
2. Score confidence (HIGH / MEDIUM / LOW / ZERO)
3. If LOW or ZERO: fix before delivering

### Step 12: Change checklist before end_change
For code/config/cron changes: load `change-checklist` and run all phases
before calling `end_change()`. Phase 6 (Reflexion) is mandatory.

### Step 13: Score and close
```python
mcp_loop_governance_cycle_query(task_id="<task-id>")
mcp_loop_governance_feedback_accept(id=<cycle-id>, note="<summary>")
mcp_loop_governance_end_change(task_id="<task-id>")
```

## Quick Reference Table

| Step | Action | Tool/Skill |
|------|--------|------------|
| 1 | Cache search | `cache_search()` |
| 2 | Begin governance | `begin_change()` |
| 3 | Load always skills | `skill_view()` per skill in `always` section |
| 4 | Choose reasoning | `agent-flow` embedded pattern table |
| 5 | Classify workflow | `agent-flow` skill |
| 6 | Load on-task skills | `skill_view()` + `skills_list()` |
| 7 | Restore todos | `task-db.py pending` → `todo()` |
| 8 | Survey + preflight | `survey-before-action` (cortex-preflight merged in) |
| 9 | Work | (task execution) |
| 10 | Reflexion check | `reflexion-check` skill |
| 11 | Change checklist | `change-checklist` skill |
| 12 | Score and close | `cycle_query` → `feedback_accept` → `end_change` |

## Known Gaps & Recovery

- **Date-format daemon session IDs:** the enforcer's daemon guard protects
  `cron_`/`bg_` prefixes only. Sessions with `HERMES_CRON_SESSION=1` but
  date-format IDs bypass the guard; concurrent sessions can then overwrite
  the marker. Symptom: "7/7 loaded" immediately followed by "not fully
  loaded". Fix: re-call `skill_view('<any>')` to re-trigger auto-create.
- **Subagents overwrite markers:** `delegate_task` subagents run with
  date-format session IDs and load skills themselves, which can invalidate
  the parent's marker. Include the marker workaround in subagent context
  (see `references/recovery-from-violation.md`).
- **Mid-session correction:** if the user asks "did you load all skills?"
  mid-task, you skipped Step 3. Stop, load the always skills, and only then
  continue. See `references/recovery-from-violation.md` and
  `references/survey-before-creating.md` for the pre-creation survey
  discipline.

## Why This Exists

The pre-task sequence was previously 8+ independent steps documented across
3 files (AGENTS.md, SOUL.md, skills). Agents skipped them because the path
from "user says do X" to "actually doing X" required too many remembered
actions. This skill bundles all steps into one reference so the agent
only has to remember one call: `skill_view('task-start')`.

Every existing rule still applies. Nothing is weakened. The difference is
that the sequence is now a single skill invocation rather than 8 separate
things an agent must independently remember.

On 2026-08-20 `session-start-discipline` (todo-restore + marker mechanics)
was merged into this skill and deleted as a standalone always-skill — one
load, one sequence, no duplicated marker lore.
