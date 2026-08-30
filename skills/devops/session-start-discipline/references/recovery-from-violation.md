# Recovery from Ritual Violation

If you caught yourself mid-session (or were corrected) for having called `begin_change` without loading all always skills:

## Recovery Steps

1. **Do not close the current lock yet** — closing it and re-opening doesn't fix the missing context. You can load skills at any point.

2. **Load the missing always skills NOW** by calling `skill_view()` on each one you skipped:
   - `skill_view('agent-flow')`
   - `skill_view('reasoning-patterns')`
   - `skill_view('reflexion-check')`
   - `skill_view('change-checklist')`
   - `skill_view('survey-before-action')`
   - `skill_view('cortex-preflight')`
   - `skill_view('agent-contract')`

3. **Select reasoning pattern** — state it explicitly: "Using Plan-Execute-Verify with Reflexion."

4. **Classify with agent-flow** — match the task to one of the 12 patterns.

5. **Load on-task skills** from `.hermes-cortex/skills.yaml` matching your classification.

6. **Add a structural guardrail** (Principle 9) so the failure cannot repeat. In this session, the guardrail was:
   - The MANDATORY SESSION-START RITUAL in SOUL.md was updated with numbered steps 1-7
   - The ritual now explicitly says "begin_change() is the LAST step — NOT the second one"
   - All 7 agent profiles (Moses, Esther, Gisu, Joseph, Kustos, Titus, Operator) received the updated ritual

## Commit the Fix

The SOUL.md changes must be committed to the repo so all fleet agents benefit:

```bash
cd ~/hermes-cortex
git add profiles/personal/agent-profiles/*/SOUL.md docs/templates/SOUL.md
git commit -m "fix: structural guardrail for session-start skill loading order"
git push origin main
```

## Real Example (Moses session 2026-07-23)

A user asked for a "thorough review of prompt response visibility." The agent loaded `task-start` but called `begin_change` before loading always skills. Worked for 20+ tool calls without `agent-flow`, `reasoning-patterns`, `change-checklist`, or `agent-contract` until the user said: "Did you load all skills?" The mid-session correction created this skill.
