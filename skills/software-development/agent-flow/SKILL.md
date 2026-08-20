---
name: agent-flow
description: "Workflow router skill — classifies the incoming request into one of 12 patterns and dispatches to the correct tooling, output format, and checklist."
version: 1.1.0
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

## Before starting: load skills from manifest AND search for relevant skills

Before routing, check for a skills manifest at `.hermes-cortex/skills.yaml` (or
`skills.yaml` in the current working directory).

If it exists:

1. **Load `always` skills** — Read the `always` section and call `skill_view(name)`
   for each skill. These define HOW to think and work: reasoning patterns,
   execution contract, pre-ship checklist. **Do not proceed without loading these.**
2. **Classify the task** (see "How to route" below).
3. **Load `on_task` skills** — After classifying, read the `on_task` section for
   your classification and call `skill_view(name)` for each matching skill.

### Critical step: search for relevant skills you don't know about

After loading the manifest, and after classifying the task:

**Call `skills_list()` with a category keyword that matches your task domain.**
Scan the descriptions. If any skill's purpose matches the task, load it with
`skill_view(name)` — even if it wasn't in the manifest. Skills you don't know
exist will never be loaded unless you search for them proactively.

```yaml
# Example: for a devops change, search devops skills
skills_list(category="devops")
# → discovers cron-job-management, change-checklist, auto-remediation, etc.
# Load anything relevant before starting work.
```

**Do this before writing any code, running any command, or making any change.**
A skill you discover at this stage can save you from redoing work later.

If it doesn't exist, fall back to scanning `.hermes-cortex/skills/` for any
embedded SKILL.md files and load those.

This ensures every agent has the right procedural knowledge for the project
before touching any code — without copying skill files (no drift, no bloat).

See `docs/skills-manifest-reference.md` in the hermes-cortex repo for details.
See `references/skill-discovery-rationale.md` for why this step exists and when it can be removed.

## How to route

1. Read the user's request.
2. **Match the reasoning pattern first** — choose from the embedded table below
   (the former `reasoning-patterns` skill was folded into this section on
   2026-08-20; `aliases: [reasoning-patterns]` keeps old references working):
   - **Plan-Execute-Verify (default)** for most tasks — write a plan, execute steps, verify each
   - **ReAct** for debugging/exploration — reason, act, observe, repeat
   - **Reflexion** to self-critique before delivering (always pair with PEV or ReAct)
   - **Tree of Thoughts** for design trade-offs
   
   State your chosen pattern explicitly: *"Using Plan-Execute-Verify with Reflexion check."*

   | Pattern | When to Use | Structure |
   |---------|-------------|-----------|
   | **Plan-Execute-Verify** | Default — most tasks | Write plan → execute steps → verify each step with tool output |
   | **ReAct** | Debugging, exploration | Reason → Act (one tool call) → Observe → Repeat |
   | **Reflexion** | Quality-critical work (add to any pattern) | Execute → Self-critique → Fix → Re-verify before delivering |
   | **Tree of Thoughts** | Design decisions with trade-offs | Generate 3+ approaches → Evaluate each → Select best → Implement |

   **How to choose:** start with Plan-Execute-Verify unless the task clearly
   demands another; switch to ReAct when debugging or exploring; add Reflexion
   for production code, security, or user-facing docs; use Tree of Thoughts for
   architectural decisions where the first idea might not be the best.
3. Then match the **workflow pattern** against trigger phrases below.
4. Follow that pattern's toolset requirements, output format, and checklist.
5. If the request spans multiple patterns (e.g., "design the API then build it"), prefix with planning:
   *"First I'll use Tree of Thoughts to evaluate API designs, then Plan-Execute-Verify to implement."*

---

## Workflow Patterns

---

### 1. simple-code — Quick, single-file changes

**Use when:** The user wants a small, self-contained change to one file. No test suite needed. No architectural design. No multi-file coordination.

**Trigger phrases:**
- "add a quick function to …"
- "can you just …"
- "minor change"
- "tweak this"
- "small fix in …"
- "update this one file"
- "simple script"

**Toolset requirements:**
- `read_file` / `write_file` / `patch` — file editing primitives
- `search_files` — to find the target
- `terminal` — optional, for one-shot verification (e.g., `python -c …`)

**Output format:**
- Inline diff or replacement snippet
- One- or two-sentence summary of what changed
- If possible, a one-liner the user can run to verify

**Checklist:**
- [ ] Did I modify only the file(s) the user asked about?
- [ ] Is the change syntactically valid? (run linter/compiler if trivial)
- [ ] Did I avoid adding imports, config, or scaffolding beyond what's needed?
- [ ] Did I explain what I changed and why, briefly?

---

### 2. enterprise — Multi-file, needs architecture + tests

**Use when:** The task spans multiple files, introduces new capabilities, or requires test coverage and architectural thought.

**Trigger phrases:**
- "build out the … module"
- "add support for …"
- "implement … with tests"
- "this should be production-grade"
- "write the full … feature"
- "needs to be maintainable"
- "enterprise"
- "production quality"

**Toolset requirements:**
- `read_file` / `write_file` / `patch` — file editing
- `search_files` — codebase exploration
- `terminal` — test runner, build commands, linter
- (optional) `delegate_task` — for parallel sub-task fan-out

**Output format:**
- Summary of architectural decisions (2–4 sentences)
- List of files created or modified with paths
- Test output (pass/fail summary)
- Commit-ready summary if relevant

**Checklist:**
- [ ] Did I read existing code to understand conventions before writing?
- [ ] Are there unit tests for each new function?
- [ ] Do all tests pass before I declare done?
- [ ] Did I handle error states (bad input, missing resources)?
- [ ] Is the code idiomatic for the project's language/framework?
- [ ] Did I run the linter/formatter?
- [ ] Are there no hardcoded secrets or credentials?

---

### 3. debug — Root cause analysis, log inspection

**Use when:** Something is broken or behaving unexpectedly. The priority is understanding *why*, not fixing (though fixes often follow).

**Trigger phrases:**
- "this is broken"
- "why is … failing?"
- "debug this"
- "something's wrong with …"
- "unexpected behaviour"
- "error in …"
- "it doesn't work"
- "crash"
- "stack trace"
- "trace this issue"
- "root cause"
- "bug"

**Toolset requirements:**
- `terminal` — run the failing command, inspect logs
- `read_file` — examine source where error originates
- `search_files` — grep for error patterns across codebase

**Method: Load the `root-cause-debugging` skill and follow its 6-phase process:**

1. **Phase 0 — Build a feedback loop.** Before theorizing, build a tight pass/fail signal: failing test, curl harness, CLI invocation, headless browser script, or bisection harness. Tighten it (faster, sharper, deterministic). Non-deterministic bugs: raise reproduction rate above 1%.
2. **Phase 1 — Reproduce + minimise.** Run the loop, confirm the correct bug, shrink to smallest load-bearing scenario. Gather evidence: error messages, recent changes, data flow.
3. **Phase 2 — Pattern analysis.** Find working examples, compare against references, identify what's different.
4. **Phase 3 — Hypothesise + instrument.** Generate 3-5 ranked falsifiable hypotheses. Tag debug logs with `[DEBUG-XXXX]`. One variable at a time. Perf bugs: measure first, fix second.
5. **Phase 4 — Fix + regression test.** Check for a correct test seam first. Turn minimised repro into a failing test. Apply fix. Verify original loop goes green.
6. **Phase 5 — Cleanup + post-mortem.** Remove tagged instrumentation. Document correct hypothesis. Ask: "What would prevent this bug?" If answer involves architecture (no test seam), hand off to `codebase-design`.

If 3+ fixes failed, question the architecture using the `codebase-design` skill — the module may need deepening to create a testable seam.

**Output format:**
1. **Feedback loop** — the pass/fail signal built (command, test, harness)
2. **Hypotheses** — 3-5 ranked, each falsifiable
3. **Root cause** — definitive answer after investigation
4. **Fix** — code/solution with regression test
5. **Post-mortem** — what would prevent this bug

**Checklist:**
- [ ] Did I build a tight feedback loop BEFORE theorizing?
- [ ] Did I reproduce, minimise, and confirm the correct bug?
- [ ] Did I generate 3-5 ranked hypotheses (not just one)?
- [ ] Did I instrument one variable at a time with tagged debug logs?
- [ ] Did I check for a correct test seam before writing the regression test?
- [ ] Did I clean up all [DEBUG-...] instrumentation?
- [ ] If 3+ fixes failed, did I question the architecture?
- [ ] If I can't find the cause, did I say so honestly and suggest next steps?

---

### 4. ui — Frontend component work

**Use when:** The task involves user interface — React components, HTML/CSS, styling, layout, responsiveness, or component logic.

**Trigger phrases:**
- "add a button that …"
- "style the …"
- "create a component for …"
- "make this responsive"
- "frontend"
- "UI"
- "CSS"
- "layout"
- "modal"
- "form"
- "navigation"
- "theme"

**Toolset requirements:**
- `read_file` / `write_file` / `patch` — edit component files
- `terminal` — dev server, build, stylelint
- `search_files` — find existing components to match patterns
- `vision_analyze` — if design mockup is provided as image

**Output format:**
- What component(s) were created/modified
- How the component interacts with state/props/data
- Visual summary (if a dev server is runnable, URL or screenshot)
- If CSS-in-JS / Tailwind / modules — consistent with project's existing approach

**Checklist:**
- [ ] Did I match the project's existing component patterns (file structure, naming, imports)?
- [ ] Is it responsive? Does it work at common breakpoints?
- [ ] Are accessibility basics covered (aria labels, tab order, focus states)?
- [ ] Did I handle loading, empty, error states?
- [ ] Did I avoid inline styles if the project uses a styling system?
- [ ] Is the component tree shallow enough? Can it be split?

---

### 5. api — Endpoint design

**Use when:** The task involves REST, GraphQL, WebSocket, or any API endpoint — request handling, response formatting, validation, authentication, documentation.

**Trigger phrases:**
- "create an endpoint that …"
- "add a route for …"
- "POST /…"
- "GET /…"
- "API endpoint"
- "REST"
- "GraphQL"
- "WebSocket handler"
- "request validation"
- "response format"
- "rate limiting"
- "middleware"

**Toolset requirements:**
- `read_file` / `write_file` / `patch` — edit route handlers
- `terminal` — run server, test with curl/httpie
- `search_files` — find existing routes, shared middleware, models

**Output format:**
- **Endpoint:** method + path
- **Request:** expected params, headers, body schema
- **Response:** success shape, error shapes (with status codes)
- **Side effects:** DB writes, cache invalidation, event emission
- **Auth:** required permissions / roles
- **Test command(s):** exact curl/httpie/python one-liner to exercise it

**Checklist:**
- [ ] Does the endpoint follow the project's route naming conventions?
- [ ] Are all inputs validated (type, range, required/optional)?
- [ ] Are error responses consistent with the project's error format?
- [ ] Is authentication/authorisation enforced (if applicable)?
- [ ] Is the handler idempotent where semantically expected?
- [ ] Does it handle common edge cases (empty body, missing fields, type mismatches)?
- [ ] Did I verify the endpoint works with a real request?

---

### 6. db — Schema migrations

**Use when:** The task touches database schema — tables, columns, indexes, migrations, seed data, or query optimisation.

**Trigger phrases:**
- "add a column for …"
- "create a table for …"
- "migration"
- "schema change"
- "database"
- "DB"
- "SQL"
- "index"
- "foreign key"
- "seed data"
- "ORM model"
- "normalize"
- "denormalize"

**Toolset requirements:**
- `read_file` / `write_file` / `patch` — edit migrations, models
- `terminal` — run migration tool, connect to DB, execute queries
- `search_files` — find existing models, migration history, schema files

**Output format:**
- **Summary:** what changed and why
- **Migration file:** exact path and contents (or link to it)
- **Rollback:** how to undo the change
- **Seed data:** if new seed data was added
- **Verification:** query to confirm the migration ran correctly

**Checklist:**
- [ ] Did I create a reversible migration (up AND down)?
- [ ] Does the migration handle existing data (default values, nullable, backfill)?
- [ ] Did I add the appropriate indexes for query patterns?
- [ ] Did I check for naming consistency with existing tables/columns?
- [ ] Is the migration idempotent (safe to run twice — e.g., `IF NOT EXISTS`)?
- [ ] Did I test the migration against a real/local database?
- [ ] Did I update the ORM model / type definitions to match?

---

### 7. data — Analysis, transformation

**Use when:** The task involves processing, cleaning, analysing, or transforming data — CSV, JSON, logs, APIs-as-source, reports, dashboards.

**Trigger phrases:**
- "analyse this data"
- "transform this … into …"
- "parse this log file"
- "generate a report on …"
- "data pipeline"
- "ETL"
- "clean this dataset"
- "visualise"
- "chart"
- "statistics"
- "aggregate"
- "CSV"
- "dataframe"
- "query this data"

**Toolset requirements:**
- `read_file` — inspect raw data
- `write_file` — write scripts, save transformed output
- `terminal` — run analysis scripts, pip install tools
- `web_search` — for library docs, statistical methods
- (optional) `vision_analyze` — if results need visual output review

**Output format:**
- **Input:** source, format, size
- **Method:** approach / algorithm / query
- **Output:** file(s) produced, or inline results with key numbers
- **Assumptions** made during cleaning/transformation
- **Caveats** about data quality or methodological limits

**Checklist:**
- [ ] Did I inspect the raw data before writing code?
- [ ] Is the script deterministic (seed set for any randomness)?
- [ ] Did I handle missing/null/malformed data explicitly?
- [ ] Are my findings reproducible (script + input committed)?
- [ ] Did I check for numerical accuracy (no integer overflow, precision loss)?
- [ ] Did I document the output format so others can use it?

---

### 8. pipeline — CI/CD, automation

**Use when:** The task involves build tooling, continuous integration/deployment, scripts, task runners, Makefiles, Docker, or infrastructure automation.

**Trigger phrases:**
- "set up CI for …"
- "add a GitHub Action that …"
- "automate …"
- "build script"
- "Docker"
- "Dockerfile"
- "deploy"
- "pipeline"
- "Makefile"
- "task runner"
- "workflow"
- "linter"
- "pre-commit hook"
- "infrastructure"
- "IaC"

**Toolset requirements:**
- `read_file` / `write_file` / `patch` — edit config files, scripts
- `terminal` — test pipeline stages locally, run linters
- `search_files` — find existing pipeline configs to match patterns
- `web_search` — for CI platform syntax (GitHub Actions, GitLab CI, etc.)

**Output format:**
- **What the pipeline does** (trigger events, stages, jobs)
- **File(s) created/modified** with paths
- **Test command** to verify a stage locally (e.g., `act` for GitHub Actions)
- **Secrets/variables** the user must configure

**Checklist:**
- [ ] Does the pipeline fail fast (fastest feedback first)?
- [ ] Are secrets handled via CI vars, not checked in?
- [ ] Are caching directives present to speed up repeated runs?
- [ ] Did I test at least one stage locally?
- [ ] Does the pipeline have a clear success/failure notification path?
- [ ] Is the pipeline portable (runs on maintainer's machine too)?

---

### 9. research — Information gathering, no code

**Use when:** The user needs to learn, compare, or investigate something — no code output expected (or at least not yet). Pure knowledge acquisition.

**Trigger phrases:**
- "what is …?"
- "how does … work?"
- "research …"
- "compare … and …"
- "find …"
- "explain …"
- "documentation for …"
- "what's the difference between …"
- "look up …"
- "investigate …"
- "tell me about …"

**Toolset requirements:**
- `web_search` — primary tool for finding information
- `web_extract` — read docs, articles, blog posts
- `search_files` — search local codebase/docs for existing knowledge
- `terminal` — only if needed to check installed versions or run doc tools

**Output format:**
- **Question:** what was asked
- **Answer:** concise, fact-based, with sources
- **Key details:** specifics that matter (versions, code snippets, config options)
- **Remaining unknowns:** what wasn't found or is uncertain

**Checklist:**
- [ ] Did I search the local codebase first before going to the web?
- [ ] Are my sources cited (URLs, doc section references)?
- [ ] Did I distinguish fact from opinion / convention from requirement?
- [ ] Is the answer actionable? If the user wanted "how to X", did I include steps?
- [ ] Did I avoid over-researching? Stop when the question is answered.
- [ ] If I can't find a reliable answer, did I say so clearly?

---

### 10. writing — Docs, specs

**Use when:** The task is about producing documentation — README, API docs, architecture decisions (ADRs), troubleshooting guides, specifications, changelogs.

**Trigger phrases:**
- "write docs for …"
- "document the …"
- "README"
- "usage guide"
- "tutorial"
- "how-to"
- "explain how to …"
- "API documentation"
- "spec"
- "ADR"
- "changelog"
- "design doc"
- "contribution guide"

**Toolset requirements:**
- `read_file` — read existing docs for tone/format consistency
- `write_file` / `patch` — write or update docs
- `search_files` — find code to document, find existing doc patterns
- `terminal` — run doc build tools if applicable (e.g., `mkdocs`, `typedoc`)

**Output format:**
- **Title** — clear, descriptive heading
- **Metadata** — status, date, authors if applicable
- **Body** — organized by sections appropriate to the doc type (usage → examples → API → troubleshooting)
- **File path** — exact location written/updated

**Checklist:**
- [ ] Does the tone match the project's existing docs?
- [ ] Are code examples complete (copy-pasteable), with expected output?
- [ ] Did I avoid jargon the reader won't know (or define it)?
- [ ] Is the doc scoped — one topic, done well?
- [ ] Are there navigation aids (tables of contents, cross-references)?
- [ ] Did I spell-check and format consistently?
- [ ] If documenting code, did I check that the code actually works as described?

---

### 11. review — Code review mode

**Use when:** The user submitted code (a diff, a PR link, a file, or a snippet) and wants it reviewed — not executed or fixed.

**Trigger phrases:**
- "review this code"
- "code review"
- "what do you think of …"
- "does this look right?"
- "review this PR"
- "check my …"
- "audit this"
- "security review"
- "code quality"
- "review this change"

**Toolset requirements:**
- `read_file` — read the code under review
- `search_files` — find related code for context
- `terminal` — optional, to run linter or tests on the code

**Method: Load the `code-review` skill and follow its two-axis process:**

Review along two independent axes:
1. **Standards** — does the code follow documented repo conventions + the Fowler smell baseline (Mysterious Name, Duplicated Code, Feature Envy, Primitive Obsession, Speculative Generality, etc.)? Hard violations (documented standards breached) vs judgement calls (code smells).
2. **Spec** — does the code implement what the originating issue/PRD asked for? Check for missing requirements, scope creep, and wrong implementations.

Run both axes as parallel sub-agents so they don't pollute each other. Present findings separately — do NOT merge or rerank axes.

**Output format:**
1. **Summary** — one-sentence overview of the change.
2. **Standards** — hard violations and code smells found.
3. **Spec** — missing items, scope creep, wrong implementations (or "no spec available").
4. **Recommendation** — approve / changes requested / blocked.

**Checklist:**
- [ ] Did I identify the spec source (issue ref, PRD, user-provided path)?
- [ ] Did I check documented repo standards FIRST (before code smells)?
- [ ] Did I run Standards and Spec as separate sub-agents (no shared context)?
- [ ] Did I present findings separately without merging or reranking?
- [ ] Did I check for tests — do they exist, are they meaningful?
- [ ] Did I avoid bikeshedding (nitpicking trivial preferences)?
- [ ] Did I provide actionable suggestions, not just problems?

---

### 12. planning — Design before implementation

**Use when:** The request is large, ambiguous, or architectural — the user needs a plan, design, or investigation before any code is written.

**Trigger phrases:**
- "plan this out"
- "how should I approach …"
- "design the architecture for …"
- "let me think about …"
- "spike this"
- "feasibility"
- "proposal"
- "compare approaches"
- "what's the best way to …"
- "blueprint"
- "tech design"
- "pre-build"
- "exploration"

**Toolset requirements:**
- `read_file` — understand existing architecture
- `search_files` — explore the codebase for patterns
- `web_search` — research approaches, libraries, best practices
- `write_file` — to save the plan

**Output format:**
- **Goal:** what the plan achieves
- **Constraints:** time, technology, team, compatibility
- **Approaches** considered (2+ with pros/cons if there's a real choice)
- **Recommended approach** with rationale
- **Step-by-step plan** with file paths, test targets, verification
- **Open questions / risks** that remain
- Save to `docs/plans/` per the `dev-plan` skill conventions

**Checklist:**
- [ ] Did I explore the existing codebase before proposing architecture?
- [ ] Are alternative approaches presented fairly (no strawmen)?
- [ ] Is the recommended approach justified with specific evidence?
- [ ] Are all steps concrete (file paths, commands, expected outputs)?
- [ ] Did I flag risks and unknowns honestly?
- [ ] Is the plan sized reasonably (max ~10 steps for the initial pass)?
- [ ] Did I save the plan to `docs/plans/`?

---

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

---

## Ambiguity resolution

If the request matches **two patterns equally**, prefer the more structured one (higher number = more structure). The structured patterns produce safer outcomes for complex work, and you can always drop back to a simpler pattern mid-flow.

If the request explicitly mentions a pattern name ("enterprise this"), honour it regardless of trigger matching — the user knows what they want.

## Flow transitions

Patterns can chain. Common transitions:

- **planning → enterprise** — designed blueprint gets implemented
- **research → writing** — findings become docs
- **research → spike → enterprise** — learn, prototype, then build
- **debug → simple-code** — found the bug, fix is small
- **db → api → ui** — full feature slice (data → logic → presentation)
- **review → enterprise** — issues found in review need a full fix

When transitioning, state the new pattern explicitly: *"Routing to debug for investigation; once root cause is found, I'll switch to simple-code for the fix."*
