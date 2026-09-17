---
name: agent-flow
description: "Workflow router skill — classifies the incoming request into one of 12 patterns and dispatches to the correct tooling, output format, and checklist."
version: 1.2.0
category: software-development
source: hermes-cortex
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
aliases:
  - reasoning-patterns
metadata:
  hermes:
    tags: [workflow, router, dispatch, patterns, code, debug, ui, api, db, data, pipeline, research, writing, review, planning, reasoning]
    related_skills: [dev-plan, spike, change-test-loop, root-cause-debugging, code-review, subagent-driven-development, writing-plans, memory-architecture, codebase-design]
---

# Agent Flow — Workflow Router

## Skill loading (before routing)

1. Check for a skills manifest at .hermes-cortex/skills.yaml (or skills.yaml in cwd).
2. If present: load always skills via skill_view(name), classify the task, then load matching on_task skills.
3. Always run `skills_list(category=<domain>)` to discover skills not in the manifest — a skill you never load can never save you. Load anything relevant before touching code.
4. No manifest → scan .hermes-cortex/skills/ for embedded SKILL.md files.

## How to route

1. Match the reasoning pattern first:

   | Pattern | When to Use | Structure |
   |---------|-------------|-----------|
   | Plan-Execute-Verify | Default — most tasks | Write plan → execute → verify each step with tool output |
   | ReAct | Debugging, exploration | Reason → Act (one tool call) → Observe → Repeat |
   | Reflexion | Quality-critical (add to any pattern) | Execute → Self-critique → Fix → Re-verify |
   | Tree of Thoughts | Design trade-offs | Generate 3+ approaches → evaluate → select → implement |

   State your choice explicitly: *"Using Plan-Execute-Verify with Reflexion check."*

2. Match the workflow pattern against trigger phrases below, follow its toolset + checklist.
3. Spans multiple patterns → prefix with planning.

## Workflow Patterns

### 1. simple-code — Quick, single-file change
Triggers: "add a quick function", "can you just", "minor change", "tweak this", "small fix", "update this one file", "simple script".
Toolset: file editing + search_files + optional terminal. Output: inline diff + brief summary + verify one-liner.
Checklist: only touched the asked files; syntactically valid; no unneeded imports/scaffolding; explained briefly.

### 2. enterprise — Multi-file, needs architecture + tests
Triggers: "build out the module", "add support for", "implement with tests", "production-grade", "full feature", "enterprise", "maintainable".
Toolset: file editing + terminal (test/build/lint) + optional delegate_task. Output: architecture summary + file list + test output.
Checklist: read existing conventions first; unit tests per function; all tests pass; error states handled; idiomatic; linted; no secrets.

### 3. debug — Root cause analysis
Triggers: "broken", "why is X failing", "debug", "unexpected behaviour", "error in", "doesn't work", "crash", "stack trace", "root cause", "bug".
Method: load root-cause-debugging and follow its 6-phase process (build feedback loop → reproduce/minimise → pattern analysis → hypothesise/instrument → fix + regression test → cleanup/post-mortem). If 3+ fixes fail, question the architecture with codebase-design.
Checklist: feedback loop BEFORE theorizing; 3-5 ranked falsifiable hypotheses; one variable at a time; regression test; cleaned up instrumentation; said so honestly if no cause found.

### 4. ui — Frontend component work
Triggers: "add a button", "style the", "create a component", "responsive", "frontend", "UI", "CSS", "layout", "modal", "form", "navigation", "theme".
Toolset: file editing + terminal (dev server/build) + search_files + vision_analyze (mockups).
Checklist: matched existing patterns; responsive; accessibility (aria, focus); loading/empty/error states; no inline styles if a system exists.

### 5. api — Endpoint design
Triggers: "create an endpoint", "add a route", "POST /", "GET /", "API", "REST", "GraphQL", "WebSocket", "validation", "rate limiting", "middleware".
Output: endpoint (method + path), request/response schema, side effects, auth, test command.
Checklist: route conventions; input validation; consistent errors; auth enforced; idempotent where expected; verified with a real request.

### 6. db — Schema migrations
Triggers: "add a column", "create a table", "migration", "schema change", "database", "SQL", "index", "foreign key", "seed data", "ORM model".
Output: summary + migration path + rollback + verification query.
Checklist: reversible (up AND down); handles existing data; indexes added; idempotent; tested on a real DB; ORM models updated.

### 7. data — Analysis, transformation
Triggers: "analyse this data", "transform", "parse this log", "report on", "ETL", "clean this", "visualise", "statistics", "aggregate", "CSV", "dataframe".
Output: input (source/format/size), method, output + key numbers, assumptions, caveats.
Checklist: inspected raw data first; deterministic; handles missing/null; reproducible; numerical accuracy; documented output format.

### 8. pipeline — CI/CD, automation
Triggers: "set up CI", "GitHub Action", "automate", "build script", "Docker", "deploy", "pipeline", "Makefile", "linter", "pre-commit hook", "infrastructure".
Output: what the pipeline does, files, local test command, secrets to configure.
Checklist: fail fast; secrets via CI vars; caching; tested one stage locally; notification path; portable.

### 9. research — Information gathering, no code
Triggers: "what is", "how does X work", "research", "compare", "find", "explain", "documentation for", "look up", "investigate".
Toolset: web_search + web_extract + search_files (local first).
Output: question, concise sourced answer, key details, remaining unknowns.
Checklist: local first; sources cited; fact vs opinion; actionable; stopped when answered; said so if no reliable answer.

### 10. writing — Docs, specs
Triggers: "write docs", "document the", "README", "usage guide", "tutorial", "how-to", "API documentation", "spec", "ADR", "changelog", "design doc".
Output: title, metadata, body, exact file path.
Checklist: tone matches; examples complete + copy-pasteable; no undefined jargon; scoped; navigation aids; verified code works as described.

### 11. review — Code review mode
Triggers: "review this code", "code review", "does this look right", "review this PR", "audit this", "security review".
Method: load code-review — two axes (Standards: repo conventions + Fowler smells; Spec: does it meet the issue/PRD). Run axes as parallel subagents, present separately.
Output: summary, standards findings, spec findings, recommendation (approve/changes/blocked).
Checklist: identified spec source; standards first; separate subagents; checked tests; no bikeshedding; actionable suggestions.

### 12. planning — Design before implementation
Triggers: "plan this out", "how should I approach", "design the architecture", "spike this", "feasibility", "proposal", "compare approaches", "blueprint".
Output: goal, constraints, 2+ approaches with pros/cons, recommended + rationale, step-by-step plan, risks. Save to docs/plans/.
Checklist: explored codebase first; fair alternatives; justified recommendation; concrete steps; risks flagged; saved plan.

## Quick reference table
| # | Pattern | Primary toolset | Output focus | Tests needed? |
|---|---------|----------------|--------------|--------------|
| 1 | simple-code | file editing | inline diff | no |
| 2 | enterprise | file + terminal + test runner | architecture + tests | yes |
| 3 | debug | terminal + grep | root cause + fix | maybe |
| 4 | ui | file + dev server | component + visuals | maybe |
| 5 | api | file + curl/httpie | schema + handlers | yes |
| 6 | db | file + migration tool | migration + rollback | yes |
| 7 | data | file + terminal scripts | analysis + output | no |
| 8 | pipeline | file + CI platform | workflow config | no |
| 9 | research | web_search + web_extract | answer + sources | n/a |
| 10 | writing | file editing | doc sections | n/a |
| 11 | review | read_file + analysis | issues + recommendations | n/a |
| 12 | planning | read_file + web_search | saved plan | n/a |

## Ambiguity & transitions

- Two patterns equally → prefer the more structured one (higher number); can drop back mid-flow.
- Explicit pattern name in request → honour it regardless of triggers.
- Chaining is normal (planning → enterprise, research → writing, debug → simple-code, db → api → ui, review → enterprise). State each transition explicitly.
