---
name: skill-creator
description: |
  Create or update OpenCode skills (SKILL.md files) with concise,
  deterministic, small-model-friendly structure.

  Triggers when user mentions:
  - "create skill"
  - "update skill"
  - "SKILL.md"
---

# Skill Creator

## Purpose
Create concise, portable, self-contained skills at:

```txt
.opencode/skills/<skill-name>/SKILL.md
```

## Core Rules

- Write/edit the real skill file when file tools are available
- Keep skills short, deterministic, and easy for small models
- Use specific trigger phrases in frontmatter
- Avoid vague or overlapping skills

## Required Frontmatter

```yaml
---
name: <skill-name>
description: |
  <1-line purpose>

  Triggers when user mentions:
  - "phrase 1"
  - "phrase 2"
  - "phrase 3"
---
```

## Recommended Structure

```md
# <Skill Name>

## Purpose
When to use it and what it produces.

## Workflow (STRICT)
1. Step one
2. Step two
3. Step three

## Rules
Non-negotiable constraints.

## Output
Exact format.

## Anti-Patterns
What to avoid.

## Goal
Desired result.
```

## Quality Checklist

- clear purpose
- specific triggers
- defined workflow
- explicit output format
- safety rules
- no unnecessary prose
- no duplicated responsibilities

## Anti-Patterns

Avoid:
- vague descriptions
- long theory sections
- missing trigger phrases
- overlapping another skill without reason
- chat-only output when a real file should be written

## Goal
Produce small, reliable skills that trigger correctly and guide small models effectively.
