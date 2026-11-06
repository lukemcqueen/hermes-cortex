---
name: task-orient
version: 0.1.0
category: workflow
description: >-
  MANDATORY first action for every task — bundles the complete pre-task
  sequence, governance chain, and workflow routing into one reference
  (absorbed task-start + agent-flow). Load BEFORE any other tool call.
pinned: true
aliases:
  - task-start
  - agent-flow
  - session-start-discipline
  - reasoning-patterns
related_skills:
  - execute-right
  - verify-and-ship
  - loop-governance
  - task-persistence
---

# Task Orient — Mandatory First Action + Workflow Router

Nothing comes before this skill. It bundles the route → execute → verify
lifecycle: how to START a task (governance chain, always-skills, survey) and
how to CLASSIFY it (workflow patterns) so the right toolset and output format
are in play. `execute-right` owns the execution rules; `verify-and-ship` owns
pre-delivery. This file owns the sequence.

## The first 90 seconds — the exact chain

The governance chain is a fixed list of calls. Run them in ONE turn each, in
order, and do not improvise (the order below is THE order; nothing to reconcile).

```text
# 1. Learn from past cycles (MCP — allowed before any lock):
mcp__review__cache_search(query="<what you are about to do>")

# 2. Open the governance lock — exact tool name, double underscores:
mcp__loop_governance__begin_change(task_id="<short-name>", description="<what this does>")

# 3. Load the always-skills in ONE turn (batched skill_view calls — read-only,
#    always allowed). Gate 1 blocks a write until all are loaded, and a write
#    outside a cycle trips Gate 2. Load them FIRST; the gates only care that
#    both are satisfied before you write.
skill_view(name='task-orient')            # this file — sequence + router
skill_view(name='execute-right')          # execution contract + survey + TDD
skill_view(name='verify-and-ship')        # pre-ship checklist + reflexion

# 4. ... work ... then score and release — scores IN THE SAME CALL (a bare note
#    is refused): completeness, quality, progress — then:
mcp__review__feedback_accept(task_id="<short-name>", note="verified: <evidence>",
    completeness=<0-10>, quality=<0-10>, progress=<0-10>)
mcp__loop_governance__end_change(task_id="<short-name>")
```

**Harness note — `skill_view` is a Hermes tool.** A Pi session has no
`skill_view`; its OWN system prompt says "Use the read tool to load a skill's
file when the task matches its description". On Pi the load IS a `read` of the
skill's `SKILL.md`, and the reflexion gate accepts that — do not hunt for a tool
your harness does not have, and never conclude skills are unloadable. An agent
that read the skill the only way its harness allows HAS loaded it.

Loads already made count and never need repeating. If a write blocks, the block
message states which gate (GATE 1 of 2 / GATE 2 of 2) and what to call — do
exactly that. **Do not source-dive the enforcer to work out governance**: the
block message IS the procedure.

If `begin_change` is not in your tool list, the MCP server is unregistered on
this host — check lock-free with `hermes mcp list`, report to your orchestrator
(Moses/Esther). Never hand-write a lock file.

## Marker mechanics

The enforcer auto-creates the skills-loaded marker once ALL always-skills have
been loaded via real `skill_view()` calls in THIS session. The loaded set is
per-session and accumulates across turns; batched loads in one turn count too.
Never touch the marker yourself (a bare file fails content verification).

- After a gateway restart, load all always-skills again in ONE turn. After a
  DEPLOY, only skills whose CONTENT changed need re-loading — the block message
  names them. Credit is per-skill, content-hashed; identical deploy content
  costs you nothing.
- On-demand skill credit (domain skills) works the same way: only re-load when
  the file's content actually changed — one `skill_view` clears it.
- `delegate_task` subagents can invalidate the parent's marker — re-call
  `skill_view('<any>')` if blocked.

## Two independent gates — expect the second block

- **Gate 1 — skills gate:** "session skills not fully loaded (N/…)": load the
  missing always-skills (all in one turn is fine).
- **Gate 2 — lock gate:** "GOVERNANCE LOCK REQUIRED": call `begin_change()`.

After fixing gate 1, a gate-2 block is EXPECTED — not a malfunction, and the
lock is not "already held".

## Terminal classifier (what counts as a write)

Any command with compound metacharacters (`; | & > < \` $()` or a newline —
including `python3 -c "..."`) is write-capable even when it only reads, so it
requires BOTH gates. Lock-free inspection: a single clean command (a listed
primitive) or read_file/search_files; a PIPE joining two read primitives
(`dmesg -T | tail -60`) runs without a lock.

Measured traps (each costs a turn):
- A metacharacter INSIDE quotes still counts (`grep -iE "a|b"` → write-class);
  use repeated `-e` flags instead.
- A command outside the read-primitive list is write-class even bare (`sensors`).
- An INTERPRETER pointed at a file is write-class, metacharacters or not
  (`python3 script.py`, `bash script.sh` — the classifier can't see inside).
  So any verification that must RUN a script happens INSIDE the cycle while the
  lock is held; after `end_change()` it is unavailable. Plan those runs into the
  work.
- When a read is blocked, change the MECHANISM (listed primitive or
  read_file/search_files) — never re-run the same shape reworded.

## The sequence after the gate loads

1. Load domain skills — operation × extension mapping (see `execute-right`),
   discovery via `skills_list(category=<domain>)`.
2. Choose the reasoning pattern and STATE it explicitly.
3. Classify the request against the workflow patterns below (sets toolset +
   output format).
4. Load on-task skills, restore todos (`~/.steadfaste-fleet/scripts/task-db.py`).
5. Survey before creating anything (`execute-right`).
6. Work. 7. Self-critique (`verify-and-ship`). 8. Score and close.

## Reasoning patterns

| Pattern | When | Structure |
|---|---|---|
| Plan-Execute-Verify | Default — most tasks | Plan → execute → verify each step with output |
| ReAct | Debugging, exploration | Reason → Act → Observe → Repeat |
| Reflexion | Quality-critical (add to any) | Execute → Self-critique → Fix → Re-verify |
| Tree of Thoughts | Design trade-offs | 3+ approaches → evaluate → select → implement |

State your choice: *"Using Plan-Execute-Verify with Reflexion check."*

## Workflow patterns (classify → toolset → output)

| # | Pattern | Triggers (sample) | Checklist essence |
|---|---|---|---|
| 1 | simple-code | "quick", "just", "minor", "tweak" | only asked files; valid; no extra scaffolding; brief |
| 2 | enterprise | "build out", "implement with tests", "production" | read conventions; unit tests; all tests pass; error states; no secrets |
| 3 | debug | "broken", "debug", "crash", "root cause" | load root-cause-debugging (6 phases); feedback loop BEFORE theorizing; 3-5 falsifiable hypotheses; regression test |
| 4 | ui | "button", "component", "frontend", "CSS" | match existing patterns; responsive; a11y; loading/empty/error states |
| 5 | api | "endpoint", "route", "API", "GraphQL" | route conventions; validation; consistent errors; auth; verified with a real request |
| 6 | db | "column", "migration", "schema", "SQL" | reversible up+down; handles existing data; idempotent; tested on a real DB |
| 7 | data | "analyse", "transform", "ETL", "CSV" | inspected raw data first; deterministic; handles null; reproducible; documented format |
| 8 | pipeline | "CI", "action", "Docker", "deploy", "hook" | fail fast; secrets via CI vars; tested one stage locally |
| 9 | research | "what is", "compare", "look up" | local first; sources cited; fact vs opinion; stopped when answered |
| 10 | writing | "docs", "README", "spec", "design doc" | tone matches; examples complete; no undefined jargon; verified code matches doc |
| 11 | review | "review this", "code review", "audit" | load code-review; spec source identified; standards + spec axes; recommendation |
| 12 | planning | "plan", "approach", "spike", "proposal" | explored codebase first; fair alternatives; justified recommendation; saved plan |

Ambiguity: two patterns equally → prefer the more structured (higher number).
Explicit pattern name in the request → honour it. Chaining is normal
(planning → enterprise, research → writing, debug → simple-code); state each
transition explicitly.
