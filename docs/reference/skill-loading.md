# Skill Loading Procedure

> Pruned from AGENTS.md on 2026-07-10. Full reference at [`docs/skills-manifest-reference.md`](../skills-manifest-reference.md).

## Procedure — every session, every agent

**Before any coding work, every agent MUST:**

1. Read the deployed skills manifest at `~/.hermes-cortex/skills.yaml` — the copy
   the governance enforcer actually enforces.
2. Load each skill in the `always` section via `skill_view(name)`.
3. Classify the current task using the `agent-flow` skill (12 patterns).
4. Load skills in the `on_task` section matching the classification.

A **seeded project** also gets a repo-local `.hermes-cortex/` overlay of its own
(written by `seed-project.sh`). That is a DIFFERENT directory from the runtime
infra dir `~/.hermes-cortex/` — same name, two scopes, and the confusion between
them is a known trap (see [`docs/skills-manifest-reference.md`](../skills-manifest-reference.md)).
Treat the project overlay as a project-level hint; the `always` set that binds is
the deployed one.

This replaces the old file-copy approach (repo-local `.hermes-cortex/skills/<name>/SKILL.md`).
If no manifest exists, fall back to scanning the project's `.hermes-cortex/skills/`
for embedded SKILL.md files (backward compatibility).

**Why:** Skills stay in one global location (`~/.hermes/skills/`). No copies, no
drift, no per-project stale files. The manifest is a lightweight reference that
tells agents what's relevant and when.

## Canonical reference

See [`docs/skills-manifest-reference.md`](../skills-manifest-reference.md) for the full guide including format, task type mappings, and migration instructions.
