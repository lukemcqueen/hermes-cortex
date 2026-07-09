# Skills Manifest Reference

Replaces the old approach of copying skill files into `.hermes-cortex/skills/` per project. The manifest is a single YAML file that references global skills by name — no drift, no stale copies, no disk bloat.

## File location

`.hermes-cortex/skills.yaml` at the project root.

## Format

```yaml
# Skills Manifest — {{PROJECT_NAME}}

always:
  - name: change-test-loop
    why: TDD discipline for every code change

on_task:
  debug:
    - name: systematic-debugging
      why: 6-phase root cause analysis
  review:
    - name: code-review
      why: Two-axis review (standards + spec)
```

## Two sections

| Section | When loaded | Purpose |
|---------|-------------|---------|
| `always` | Session start, every task | Core workflow skills the agent should have active for any work in this project |
| `on_task` | After agent-flow classification | Task-specific skills loaded when the request matches that pattern |

## Task types (from agent-flow)

| Type | Skills you might map |
|------|---------------------|
| `simple-code` | — |
| `enterprise` | subagent-driven-development, dev-plan, change-test-loop |
| `debug` | systematic-debugging, save-lesson |
| `ui` | react-best-practices, react-component-testing, react-composition-patterns |
| `api` | test-driven-development |
| `db` | test-seed-uniqueness |
| `data` | — |
| `pipeline` | git-deployment-workflow, nginx-web-app-deployment |
| `research` | — |
| `writing` | — |
| `review` | code-review, architecture-review, pr-review |
| `planning` | dev-plan, spike |

## How agents use it

1. **Session start** — agent reads `AGENTS.md`, which says "load skills from `.hermes-cortex/skills.yaml`".
2. **Load `always`** — agent calls `skill_view(name)` for each skill in the `always` section.
3. **Classify** — agent runs agent-flow to determine the task type.
4. **Load `on_task`** — agent calls `skill_view(name)` for skills mapped to that task type.
5. **Work** — agent proceeds with the task, having the relevant skill instructions in context.

## Migration from file-copy approach

Projects seeded with the old approach have skill files in `.hermes-cortex/skills/<name>/SKILL.md`.
Those files still work — Hermes loads them when `workdir` is set.
The manifest is additive: if both exist, the manifest takes precedence.

To migrate a project from file-copy to manifest:

```bash
# 1. Remove stale skill copies (optional — they won't conflict)
rm -rf .hermes-cortex/skills/*

# 2. Re-seed to get the manifest
bash ~/hermes-cortex/src/scripts/install/seed-project.sh --project=/path/to/project
```

## Generating the manifest

Run `seed-project.sh` which writes `.hermes-cortex/skills.yaml` with the default
skill set. Use `--skill-refs` to customize:

```bash
bash ~/hermes-cortex/src/scripts/install/seed-project.sh \
  --project=~/Developer/my-api \
  --skill-refs=change-test-loop,code-review,systematic-debugging
```

This populates the `always` section. The `on_task` mappings come from the template.
