# AgentKore Recreate / Extend Prompt

## Recreate / Extend AgentKore Prompt

Use this prompt when you want to rebuild AgentKore later or add a new feature without losing the system design.

```md
You are rebuilding or extending the AgentKore system.

Your goal:
Recreate the full AgentKore architecture faithfully, while optionally adding new features.

## Core principles

Do not break these:

1. Minimal context usage optimized for local models.
2. On-demand skill loading. Never load everything.
3. One-change-at-a-time execution using change-test loop.
4. Real verification only. No simulated tool/file/test results.
5. Documentation-first awareness. No duplicate docs.
6. Durable memory only, using memory scoring.
7. Separation of concerns:
   - `.agentkore/` = system brain/source/config/runtime/templates/session
   - `.opencode/` = OpenCode runtime adapter
   - `docs/` = human-readable project outputs
   - `memory/` = durable repo learning
   - `.agentkore/scripts/` = helper and validation scripts

## Required components

Recreate:

- `.agentkore/config`
- `.agentkore/prompts`
- `.agentkore/hermes/skills`
- `.agentkore/runtime`
- `.opencode/skills/<name>/SKILL.md`
- `.opencode/commands`
- `.opencode/agents`
- `docs/prd`
- `docs/architecture`
- `docs/research`
- `docs/decisions`
- `docs/tasks`
- `memory/patterns.md`
- `memory/decisions.md`
- `memory/mistakes.md`
- `memory/commands.md`
- `memory/index.md`
- `.agentkore/scripts/agentkore-validate.sh`

## Required always-loaded skills

Include:

- agent-contract
- change-test-loop
- debugging
- git-workflow
- security
- fast-bmad
- doc-system
- memory-management

## Required advanced modes

Include:

- ak-elicit
- ak-party

## Required workflows

Documentation:
doc-system → update/extend/create

Planning:
ak-elicit → ak-party → prd-lite → architecture → story-slicing

Execution:
fast-bmad → change-test-loop → verification

Memory:
post-task → memory scoring → write only if score >= 7

Validation:
Run `.agentkore/scripts/agentkore-validate.sh` and fix every reported error.

## Skill rules

Skills must be:
- small
- actionable
- command-oriented
- 300-800 words max when possible
- not duplicated across skills

## When adding a feature

1. Identify its layer:
   - skill
   - mode
   - workflow
   - config
   - docs
   - memory
   - validation
2. Make it optional/on-demand unless truly core.
3. Update:
   - `.agentkore/config/routing.md`
   - `AGENTS.md`
   - README
   - validation script if structure changes
4. Mirror any OpenCode skill to compatibility paths.
5. Do not increase default context load unless necessary.

## Output requirements

Provide:
1. Folder structure
2. Key files
3. Updated skills/prompts/config
4. Validation script
5. README usage notes
6. ZIP/downloadable package if tools allow
```
