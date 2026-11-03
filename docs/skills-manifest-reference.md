# Skills Manifest Reference

> **Two directories share the name `.steadfaste-fleet` — know which one you mean.**
>
> | Directory | What it is | Written as |
> |-----------|-----------|------------|
> | `~/.steadfaste-fleet/` | The **runtime infra dir**, deployed by `cortex-update.sh`: `scripts/`, `state/`, `sessions/`, `memory/`, `hooks/`, and the `skills.yaml` the governance **enforcer** reads. | Always with the home anchor — `~/.steadfaste-fleet/…` |
> | `./.steadfaste-fleet/` | A **repo-local overlay inside a consumer project**, created by `seed-project.sh`. Only this page describes it. | Qualified — "repo-local", or a project path |
>
> A bare `.steadfaste-fleet/` in a doc that means the runtime dir is a bug: agents read it as this project overlay, then look for the infra dir inside the project and report it as "the Hermes agent infra directory". **Operator report, 2026-10-30** (source: a seeded project AGENTS.md on a dev host; not re-measured here): that convention table listed `.steadfaste-fleet/sessions/`, `.steadfaste-fleet/memory/` and `.steadfaste-fleet/skills.yaml` as the infra dir. Verified on this host instead: all three live in `~/.steadfaste-fleet/` — see the counts and the deployed-copy check in `docs/evidence/steadfaste-fleet-path-anchor-2026-10-30.txt`. The Cortex repo itself must carry **no** repo-local overlay (doctor check `Repo-local .steadfaste-fleet`).

Replaces the old approach of copying skill files into the project's repo-local `.steadfaste-fleet/skills/`. The manifest is a single YAML file that references global skills by name — no drift, no stale copies, no disk bloat.

## File location

`<project-root>/.steadfaste-fleet/skills.yaml` — **repo-local**, created by `seed-project.sh`.
This is a different file from the runtime manifest at `~/.steadfaste-fleet/skills.yaml`,
which is the one the enforcer reads.

## Format

```yaml
# Skills Manifest — {{PROJECT_NAME}}

always:
  - name: change-test-loop
    why: TDD discipline for every code change

on_task:
  debug:
    - name: root-cause-debugging
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
| `debug` | root-cause-debugging, save-lesson |
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

1. **Session start** — agent reads `AGENTS.md`, which points at the deployed manifest `~/.steadfaste-fleet/skills.yaml`. In a seeded project the repo-local manifest is an additional, project-level hint.
2. **Load `always`** — agent calls `skill_view(name)` for each skill in the `always` section.
3. **Classify** — agent runs agent-flow to determine the task type.
4. **Load `on_task`** — agent calls `skill_view(name)` for skills mapped to that task type.
5. **Work** — agent proceeds with the task, having the relevant skill instructions in context.

## Migration from file-copy approach

Projects seeded with the old approach have skill files in the repo-local `.steadfaste-fleet/skills/<name>/SKILL.md`.
Those files still work — Hermes loads them when `workdir` is set.
The manifest is additive: if both exist, the manifest takes precedence.

To migrate a project from file-copy to manifest:

```bash
# 1. In the PROJECT root — drop stale repo-local skill copies (optional)
rm -rf .steadfaste-fleet/skills/*

# 2. Re-seed to get the manifest
bash ~/steadfaste-fleet/ops/scripts/install/seed-project.sh --project=/path/to/project
```

## Generating the manifest

Run `seed-project.sh` which writes the repo-local `.steadfaste-fleet/skills.yaml` with the default
skill set. Use `--skill-refs` to customize:

```bash
bash ~/steadfaste-fleet/ops/scripts/install/seed-project.sh \\
  --project=~/Developer/my-api \
  --skill-refs=change-test-loop,code-review,root-cause-debugging
```

This populates the `always` section. The `on_task` mappings come from the template.
