# Skill Loading Procedure

> Pruned from AGENTS.md on 2026-07-10. Full reference at [`docs/skills-manifest-reference.md`](../skills-manifest-reference.md).

## Procedure — every session, every agent

**Before any coding work, every agent MUST:**

1. Check for `.hermes-cortex/skills.yaml` in the project root.
2. If it exists, load each skill in the `always` section via `skill_view(name)`.
3. Classify the current task using the `agent-flow` skill (12 patterns).
4. Load skills in the `on_task` section matching the classification.

This replaces the old file-copy approach (`.hermes-cortex/skills/<name>/SKILL.md`).
If no manifest exists, fall back to scanning `.hermes-cortex/skills/` for embedded
SKILL.md files (backward compatibility).

**Why:** Skills stay in one global location (`~/.hermes/skills/`). No copies, no
drift, no per-project stale files. The manifest is a lightweight reference that
tells agents what's relevant and when.

## Canonical reference

See [`docs/skills-manifest-reference.md`](../skills-manifest-reference.md) for the full guide including format, task type mappings, and migration instructions.
