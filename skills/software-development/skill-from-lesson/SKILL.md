---
name: skill-from-lesson
description: "Use when you learn a durable operational lesson from a bug, user correction, or discovery. Evaluate whether it should be encoded as a skill, then create or update one."
version: 1.0.0
author: Moses
license: MIT
metadata:
  hermes:
    tags: [meta, skills, learning, lessons, self-improvement]
    related_skills: [public-contribution, knowledge-lifecycle, memory-architecture, hermes-agent-skill-authoring, nginx-web-app-deployment]
---

# Skill-From-Lesson — Turning Lessons Into Skills

## Overview

Every time a bug is fixed, a user corrects you, or you discover a non-obvious pattern, you have a choice: forget it next session, save it to memory (where it might get compressed out), or encode it as a **skill** — durable procedural knowledge that loads automatically every turn.

This meta-skill helps you decide which path to take and executes the workflow.

## When to Use

This meta-skill activates whenever you:
- Fix a bug caused by a recurring pattern (not a one-off typo)
- Are corrected by the user on a workflow, tool usage, or convention
- Discover a non-obvious pitfall in a tool, config, or deployment pattern
- Notice you did something manually that could be systematized
- The user asks "did you have a skill for that?" and you didn't

**Don't use for:**
- One-off bugs with a unique cause (those go to a lessons index)
- Configuration values or environment facts (those go to memory)
- Task-specific steps the user asked you to do once (no need)

## Decision Tree

When you learn something, ask these questions in order:

```
Did the lesson involve a REPEATABLE WORKFLOW or TOOL USAGE?
├── YES → Should it be a skill?
│   ├── Does it have ≥2 steps? → YES → Create/update a skill
│   ├── Does it have a non-obvious pitfall? → YES → Create/update a skill
│   ├── Will you do this again? → YES → Create/update a skill
│   └── No to all → Save to lessons index only
└── NO → Is it a configuration fact or user preference?
    ├── YES → Save to memory
    └── NO → Is it a one-time insight?
        ├── YES → Save to lessons index
        └── NO → Skip (not worth preserving)
```

## Workflow

### Step 1: Check existing skills

Before creating anything, `skills_list()` to check if a skill already covers this territory. If one does but is missing the new insight, **update it** with `skill_manage(action='patch')` instead of creating a new one.

### Step 2: Create or update the skill

- **Create:** `skill_manage(action='create', name='<descriptive-name>', category='<category>', content='...')`
  - Name must be lowercase with hyphens, ≤ 64 chars
  - Pick the closest existing category from the skills list
  - Include: Overview, When to Use, Step-by-step instructions, Common Pitfalls (with the bug you just fixed as entry #1), Verification Checklist

- **Update existing:** `skill_manage(action='patch', name='<existing>', old_string='...', new_string='...')`
  - Add the new pitfall to the Common Pitfalls section
  - Or update a step that was wrong

### Step 3: Verify the skill loaded correctly

```python
skill_view(name='<skill-name>')
```

Check that the skill exists and the content is correct.

### Step 4: Cross-reference in lessons index

Also add a brief note to your lessons index with the skill name as a pointer, so long-term knowledge base indexes the connection.

### Step 5: Remove from memory if applicable

If the lesson previously existed as a memory entry that's now superseded by the skill, consider removing or shortening it to save space.

### Step 6: Evaluate for public contribution

Run the `public-contribution` decision tree. If this skill would help other Hermes Cortex users, genericize it and contribute to the public repo.

## Common Pitfalls

1. **Creating a skill when memory would do.** Skills are for procedural workflows (step-by-step). Configuration facts, user preferences, and environment details belong in memory.
2. **Not checking existing skills first.** Always skills_list() before creating — you may just need to patch an existing one.
3. **Skipping the lessons index.** The skill is the executable knowledge; the lessons index is the searchable record. Both should exist for discoverability.
4. **Creating too narrow a skill.** "nginx dual-listener fix" is too narrow — "nginx-web-app-deployment" is the right scope. The lesson is a pitfall in a broader workflow.
5. **Letting the lesson get compressed out of memory.** If a lesson is important enough to save, it's important enough to be a skill. Memory is for facts, not procedures.
6. **Keeping good patterns private.** If the skill solves a problem others likely face, contribute it to the public Hermes Cortex repo. See the `public-contribution` skill.

## Verification Checklist

- [ ] `skills_list()` checked for existing coverage
- [ ] Skill created or patched with the right scope (workflow-level, not one-off)
- [ ] Common Pitfalls includes the newly discovered bug
- [ ] Lesson also added to lessons index with skill pointer
- [ ] Memory entry removed or shortened if superseded
- [ ] `skill_view(name)` confirms content loaded correctly
- [ ] `public-contribution` decision tree run — is this worth sharing?
