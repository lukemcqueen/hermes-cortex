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

## START HERE — the first 90 seconds

The governance chain is a fixed, known list of calls. Do them in ONE turn each and
do not improvise:

```text
# 1. All 7 always-skills in ONE turn (7 skill_view calls, batched — read-only, always allowed):
skill_view(name='task-start')            # this file — bundles the whole sequence
skill_view(name='agent-flow')            # workflow router + reasoning patterns
skill_view(name='reflexion-check')       # self-critique before delivering
skill_view(name='change-checklist')      # pre-ship verification
skill_view(name='survey-before-action')  # pre-flight resource search
skill_view(name='agent-contract')        # execution rules
skill_view(name='test-driven-development')  # TDD Iron Law

# 2. Learn from past cycles (MCP, allowed before any lock):
mcp__loop_governance__cache_search(query="<what you are about to do>")

# 3. Open the governance lock — exact tool name, double underscores:
mcp__loop_governance__begin_change(task_id="<short-name>", description="<what this does>")

# 4. ... work ... then score and release:
mcp__loop_governance__feedback_accept(task_id="<short-name>", note="verified: <evidence>")
mcp__loop_governance__end_change(task_id="<short-name>")
```

Loads already made count and never need repeating. If a write tool blocks, the
block message states which gate is unmet (GATE 1 of 2 / GATE 2 of 2) and what to
call — read it and do exactly that. **Do not go reading
`~/.hermes/plugins/governance-enforcer/` to work out how governance works**: the
block message already contains the whole procedure, and source-diving burns turns
without unblocking anything.

If `mcp__loop_governance__begin_change` is not in your tool list, the MCP server is
not registered on this host — check lock-free with `hermes mcp list`, then report it
to your orchestrator (Moses/Esther). Never hand-write a lock file.

## The Sequence

1. Cache search — `mcp__loop_governance__cache_search(query="<the user's request>")`
2. Begin governance — `mcp__loop_governance__begin_change(task_id="<short-name>", description="<what you are about to do>")` — mandatory before any write; write tools block without it.
3. Load always skills — `skill_view(name)` for every skill in the always section of .hermes-cortex/skills.yaml (7 skills; do all 7 in one turn).
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

The enforcer auto-creates `~/.hermes-cortex/state/skills-loaded/<session-id>` once
all 7 always-skills have been loaded via real `skill_view()` calls in THIS session
(`~/.hermes-cortex/state/skills-state/<session-id>.json` records which). The loaded
set is per-session and **accumulates across turns; batched loads in a single turn
count too**. The marker appears the moment the 7th one lands — any order, any turn,
batched or serial. Never touch the marker yourself: a bare file (or a directly
written `skills-state.json`) fails content verification.

If write tools block with "session skills not fully loaded":
- Read the block message — it lists all 7 with ✅/blank marks. Load only the blanks;
  everything already loaded counts and never needs repeating.
- After a gateway restart the in-memory set is gone → load all 7 again.
- After a deploy that changed a skill file, the marker's fingerprint goes stale
  ("7/7 loaded ✅ but still blocked"): the in-memory set usually survives, so ONE
  `skill_view('<any-always-skill>')` regenerates the marker. If the set was lost
  too, load all 7.
- `delegate_task` subagents can invalidate the parent's marker — re-call
  `skill_view('<any>')` if blocked.

## Two Independent Gates — Expect the Second Block

The enforcer gates write tools with TWO independent checks; fixing one does not
satisfy the other:

- **Gate 1 — skills gate:** "session skills not fully loaded (N/7)" → load the missing always-skills (all 7 in one turn is fine).
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
