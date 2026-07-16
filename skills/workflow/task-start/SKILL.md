---
name: task-start
version: 1.0.0
category: workflow
description: >-
  MANDATORY first action for every task. Bundles the complete
  pre-task sequence into one reference. Load this BEFORE any
  other tool call — it prescribes the exact sequence that
  follows.
pinned: true
related_skills:
  - agent-flow
  - reasoning-patterns
  - survey-before-action
  - change-checklist
  - reflexion-check
  - loop-governance
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

### Step 4: Select reasoning pattern
Load `reasoning-patterns` and choose:
- **Plan-Execute-Verify** (default) — write a plan, execute steps, verify each
- **ReAct** — debugging, exploration
- **Reflexion** — add to any pattern when quality is critical
- **Tree of Thoughts** — design decisions with trade-offs

State your choice: *"Using Plan-Execute-Verify with Reflexion check."*

### Step 5: Classify with agent-flow
Load `agent-flow` and match the request against the 12 workflow patterns.
This determines toolset, output format, and checklist.

### Step 6: Load on-task skills
After classification, load every skill matching your classification from the
`on_task` section of `.hermes-cortex/skills.yaml`. Then call `skills_list()`
for the relevant category to discover skills not in the manifest.

### Step 7: Survey before action
Load `survey-before-action` and run its checklist BEFORE creating any file,
writing any code, or running any command. Search for existing resources first.

### Step 8: Work
Execute the task using the loaded skills, following the chosen reasoning
pattern and the classified workflow pattern's checklist.

### Step 9: Reflexion check before delivery
After completing the work but BEFORE presenting results:
1. Load `reflexion-check` and run the five-question audit
2. Score confidence (HIGH / MEDIUM / LOW / ZERO)
3. If LOW or ZERO: fix before delivering

### Step 10: Change checklist before end_change
For code/config/cron changes: load `change-checklist` and run all phases
before calling `end_change()`. Phase 6 (Reflexion) is mandatory.

### Step 11: Score and close
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
| 4 | Choose reasoning | `reasoning-patterns` skill |
| 5 | Classify workflow | `agent-flow` skill |
| 6 | Load on-task skills | `skill_view()` + `skills_list()` |
| 7 | Survey before action | `survey-before-action` skill |
| 8 | Work | (task execution) |
| 9 | Reflexion check | `reflexion-check` skill |
| 10 | Change checklist | `change-checklist` skill |
| 11 | Score and close | `cycle_query` → `feedback_accept` → `end_change` |

## Why This Exists

The pre-task sequence was previously 8+ independent steps documented across
3 files (AGENTS.md, SOUL.md, skills). Agents skipped them because the path
from "user says do X" to "actually doing X" required too many remembered
actions. This skill bundles all 11 steps into one reference so the agent
only has to remember one call: `skill_view('task-start')`.

Every existing rule still applies. Nothing is weakened. The difference is
that the sequence is now a single skill invocation rather than 8 separate
things an agent must independently remember.
