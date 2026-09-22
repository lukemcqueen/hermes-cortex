---
name: task-start
version: 1.3.0
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

Nothing comes before this skill. Execute the sequence in order; do not skip or defer any step.

## The Sequence

1. Cache search — cache_search(query="<the user's request>")
2. Begin governance — begin_change(task_id="<short-name>", description="<what you are about to do>") — mandatory before any write; write tools block without it.
3. Load always skills — skill_view(name) for every skill in the always section of .hermes-cortex/skills.yaml.
4. Load domain skills — run survey-before-action Phase 0a (operation × extension mapping); load every matching skill; discovery via skills_list(category=<domain>).
5. Choose reasoning pattern — from `agent-flow`'s table (Plan-Execute-Verify default; ReAct for debug; Reflexion for quality; Tree of Thoughts for trade-offs). State it explicitly.
6. Classify — match the request against agent-flow's 12 workflow patterns (sets toolset + output format).
7. Load on-task skills — from the on_task manifest section, then skills_list() for the category.
8. Restore todos — ~/.hermes-cortex/scripts/task-db.py pending → todo(todos=<items>, merge=true)
9. Survey — run `survey-before-action`'s checklist before creating/writing anything.
10. Work — execute using the loaded skills.
11. Reflexion — reflexion-check seven-question audit; if LOW/ZERO, fix before delivering.
12. Change checklist — change-checklist all phases before end_change() (Phase 6 Reflexion mandatory).
13. Score and close — feedback_accept → end_change.

## Marker Mechanics

The enforcer auto-creates ~/.hermes-cortex/state/skills-loaded/<session-id> once all always skills load via actual skill_view() calls — never touch it (a bare file fails content verification). The loaded-set lives in the gateway process's memory.

If write tools block with "session skills not fully loaded":
- No gateway restart since loading → ONE serial skill_view('<any-always-skill>') re-triggers auto-create (batched loads in one turn do NOT).
- After a gateway restart or deploy changed a skill mtime → re-load ALL 7 always-skills serially; the last call regenerates the marker. This is the "7/7 loaded ✅ but still blocked" state.
- delegate_task subagents can invalidate the parent's marker — re-call skill_view('<any>') if blocked.

## Two Independent Gates — Expect the Second Block

The enforcer gates write tools with TWO independent checks; fixing one does not
satisfy the other:

- **Gate 1 — skills gate:** "session skills not fully loaded (N/7)" → load the 7 always-skills serially (above).
- **Gate 2 — lock gate:** "GOVERNANCE LOCK REQUIRED" → `begin_change()`.

After fixing gate 1, a gate-2 block is EXPECTED — call `begin_change()`; it is
not a malfunction and the lock is not "already held". Each block message labels
its gate (GATE 1 of 2 / GATE 2 of 2).

Terminal nuance: any command with compound metacharacters (`; | & > < \` $() or
a newline — including `python3 -c "..."`) is treated as write-capable even when
it only reads, so it requires BOTH gates. For lock-free inspection use a single
clean command (`ls`, `grep`, `git status`) or read_file/search_files.

## Quick Reference

| Step | Action |
|------|--------|
| 1 | cache_search |
| 2 | begin_change |
| 3 | load always skills |
| 4 | load domain skills (Phase 0a) |
| 5 | choose reasoning pattern |
| 6 | classify (agent-flow) |
| 7 | load on-task skills |
| 8 | restore todos |
| 9 | survey before action |
| 10 | work |
| 11 | reflexion-check |
| 12 | change-checklist |
| 13 | feedback_accept → end_change |
