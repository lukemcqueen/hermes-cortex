# Elicit/Party Before Implementing + Granularity Stress-Test — 2026-08-06

Workflow preference Luke pushed during the todo-workflow redesign session.
Applies to ANY cross-cutting system change (schema, storage, fleet-wide
feature) — not just mycortex/todos.

## The rule: elicit + party BEFORE implementing

When a change touches every agent (or every session), Luke's steer is:

> "this might be a good time to do some elicit/party to make sure our
> todo/workflow system is enterprise-grade"

Do NOT jump from "found the flaw" straight to "fix it." For cross-cutting
designs:
1. Write the elicitation doc first (`docs/elicit/YYYY-MM-DD_<topic>-elicit.md`)
   — established facts, domain decomposition, open questions with stated
   defaults.
2. Surface the open questions to Luke with YOUR defaults marked, and let
   him push back (he will).
3. Run the 6-role party (architecture-review skill) on the storage/scoping
   options before writing the design doc.
4. Only then implement.

The cost of skipping: the 2026-08-06 todo fix shipped `bus.todos` (built on
a foundation that never existed) and the worker-exclusion flaw was only
caught when Luke asked "are agents ready to pull?" — an elicit would have
surfaced the per-host/bus-schema reality before a line of code changed.

## Granularity stress-test: "is this granular enough? just make sure"

Luke pushes on model granularity. When proposing a data model (schema
columns, scoping dimensions), STRESS-TEST it before locking:

1. **Run REAL examples from the domain through the model.** Not
   hypotheticals — actual records from the session/work. For todos: "verify
   deepseek rollout on cisnet02" (host-scoped, no repo!), "learn postgres
   extension auth" (brain-scoped), "migrate all hosts to new cert"
   (fleet-scoped, no owner). A model of `agent_name × repo × scope` broke
   on all three — repo was too narrow a target.
2. **Name the dimensions that break** and the minimal fix. `repo` →
   `context` (repo:|host:|brain:|fleet); `agent_name` → `created_by` +
   `assignee` (conflated before); tenant declared not columned (document
   the decision so it's deliberate).
3. **Separate must-have columns from future-proofing.** Ship `due`, `tags`,
   `depends_on`, `priority` now so there's no second migration — but
   DELIBERATELY EXCLUDE teams/roles tables, milestones, comments, SLA
   (that's where enterprise-grade becomes enterprise-bloat). State the
   exclusions explicitly.
4. **Present the granularity question, don't presume it.** "Is this
   granular enough?" from Luke means: prove it with real cases, show the
   breaks, offer the refined model.

## Luke's five defaults that carried (2026-08-06 todo system)

- Fleet transport: defer fleet-write (ship personal + `scope` column; add
  transport when a real fleet task appears)
- Repo resolution: flag wins, CWD fallback
- Repo value: NAME only, never path (PII discipline)
- Kanban columns: fixed enum (backlog/todo/in_progress/review/done) +
  position int
- MCP toolset: `todos` with plain names (`todo_add`, `todo_list`, ...) —
  no `bus_` prefix

Reference elicitation: `docs/elicit/2026-08-06_todo-workflow-elicit.md`.
