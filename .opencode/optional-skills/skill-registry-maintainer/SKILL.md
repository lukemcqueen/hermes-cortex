---
name: skill-registry-maintainer
description: |
  Add, rename, remove, and validate AgentKore skills while updating all
  references, registries, mirrors, commands, AGENTS.md, and docs.

  Triggers when user mentions:
  - "add skill"
  - "remove skill"
  - "rename skill"
  - "update skill registry"
  - "sync skills"
---

# Skill Registry Maintainer

## Purpose
Keep AgentKore skill references consistent after skill changes.

Use when:
- adding a new skill
- deleting a skill
- renaming a skill
- moving skill files
- updating required/default skill lists

---

## Core Rule

A skill change is not complete until all references are updated and validated.

---

## Workflow (STRICT)

1. Identify skill change:
   - add | update | rename | delete
2. Update primary skill:
   ```txt
   .opencode/skills/<skill-name>/SKILL.md
   ```

3. Update mirrors if used:

   ```txt
   .agentkore/skills_source/<category>/<skill-name>.md
   .claude/skills/<skill-name>/SKILL.md
   .agents/skills/<skill-name>/SKILL.md
   ```
4. Update registries/configs:

   * `.agentkore/skills_source/registry.md`
   * `.agentkore/config/agentkore.json`
   * install/validation scripts
5. Update references:

   * `AGENTS.md`
   * `.opencode/commands/*.md`
   * docs
   * README
   * memory only if durable
6. Search for stale names:

   ```bash
   grep -Rni "<old-skill-name>" AGENTS.md .agentkore .opencode .claude .agents docs memory 2>/dev/null
   ```
7. Validate:

   ```bash
   .agentkore/scripts/agentkore-validate.sh
   ```
8. Report changed files and stale references removed

---

## Add Skill Rules

When adding a skill:

* create primary skill folder
* add concise trigger phrases
* add to registry/config if applicable
* add to `agent-flow` only if it affects routing
* add to `AGENTS.md` optional skill hints if broadly useful
* add command only if it is user-invoked directly

---

## Rename Skill Rules

When renaming:

1. create new skill path
2. update all references
3. delete old skill path only after search confirms replacement
4. validate no stale references remain

---

## Delete Skill Rules

Before deleting:

* confirm replacement or redundancy
* remove all references
* update workflows that mentioned it
* validate no missing skill references

---

## Registry Rules

Each registered skill should include:

```json
{
  "name": "<skill-name>",
  "path": ".opencode/skills/<skill-name>/SKILL.md",
  "category": "<planning|execution|review|data|ui|infra|state|docs|llm|utility>"
}
```

---

## Validation Checklist

Confirm:

* skill folder exists
* `SKILL.md` has valid frontmatter
* name matches folder
* description has useful triggers
* no stale references
* registry/config updated
* mirrors synced
* validation passes

---

## Anti-Patterns

Avoid:

* adding skill file only
* forgetting mirrors
* stale references in `agent-flow`
* duplicate skill names
* keeping deleted skills in registry
* adding every skill to required/default load
* updating memory for trivial skill changes

---

## Final Report

```md
## Skill Registry Result
added | updated | renamed | deleted

## Skill
- name:

## Files changed
- path: purpose

## References updated
- AGENTS.md:
- agent-flow:
- commands:
- registry/config:

## Validation
- command: result

## Notes
Stale references, risks, follow-ups
```

---

## Goal

Keep AgentKore skills synchronized, discoverable, and free of stale references.