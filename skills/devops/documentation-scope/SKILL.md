---
name: documentation-scope
version: 1.0.0
category: devops
description: >
  Multi-audience documentation scoping conventions for Hermes Cortex. Defines
  when and how to distinguish general (universal) content from deployment-
  specific content using scope banners and section tags. Keeps the public
  OSS repo usable by everyone while preserving Luke's personal deployment notes.
author: Hermes Cortex
tags: [docs, scope, multi-audience, conventions, hermes-cortex]
related_skills: [agent-contract, public-contribution]
---

# Documentation Scope Conventions

## When to Use

Load this skill when:
- Adding a new document or section to Hermes Cortex that mixes general guidance with deployment-specific details
- Reviewing existing docs for content that should be clearly scoped
- Adding agent handoff notes, cron job references, or deployment-specific schedules to the public repo
- A reader might misinterpret your deployment-specific setup as required or universal
- You encounter hardcoded agent names (Moses, Titus, Gisu, Joseph) in general documentation

## Scope Convention

The Hermes Cortex repo serves **two audiences**:
1. **General developers** — anyone who clones the repo for their own use
2. **Luke's deployment** — the Moses-orchestrated multi-machine setup operating in KST (Seoul)

### Banner pattern

Every multi-audience doc should start with a `🪪 Scope:` blockquote:

```
> **🪪 Scope:** This document serves two audiences:
> - **General agents** — sections without a marker are universal.
> - **Luke's deployment (Moses server)** — sections marked with `⚡` are specific
>   to Luke's multi-machine, multi-agent orchestration setup (Moses orchestrator,
>   peer agents Titus/Gisu/Joseph, KST timezone, Telegram delivery). Treat these
>   as examples you can adapt for your own setup.
>
> Everything unmarked is general guidance — apply it to any project using this repo.
```

### Section tagging

Tag deployment-specific sections with a leading `⚡` in the heading:

```
## ⚡ Daily Priority Check-in (Luke's multi-agent setup)
## ⚡ Agent Handoffs (Luke's deployment — session-to-session notes)
## ⚡ 📨 Moses Inbox Remediation Processor
```

### Inline generalization pattern

When a general skill or document hardcodes Luke-specific agent names, **generalize the rule first, then add a blockquote example**:

```markdown
### 7.5 Operator Notification Protocol

When any Hermes Cortex agent receives a task from an upstream orchestrator
agent, it MUST notify its human operator before executing the task.

> **Example (Luke's deployment):** The Moses orchestrator delegates to peer
> agents Titus, Gisu, and Joseph. Each peer notifies Luke via Telegram before
> acting on Moses's task.
```

## When to tag vs. when to generalize

| Situation | Action |
|-----------|--------|
| The content is a **user-facing workflow** that only applies to Luke's machines | Tag the entire section with `⚡` |
| A **general rule** happens to reference Luke-specific agents | Generalize the rule, add Luke's setup as a blockquote example |
| A **cron schedule** with KST times | Tag with `⚡` (Luke's deployment — KST) |
| A **skill** that explicitly names Moses as the actor | Keep the skill name descriptive (e.g., `moses-inbox-remediation`), tag `⚡` in docs referencing it |
| An **agent handoff note** about a specific fix/change | Tag the entry with `⚡` unless the fix is universally applicable (e.g., auto-remediation system) |

## Pitfalls

- **Creating docs without loading this skill first.** If you are creating a new doc or updating an existing one for the public repo, load `documentation-scope` via `skill_view()` BEFORE writing. Without it you will: (a) miss the scope banner, (b) use deployment-specific examples without a scope marker, (c) make the doc unusable by general developers. This happened 2026-07-23 when `agent-architecture.md` was created without loading this skill — had to retroactively add the banner and tag deployment sections.
- **Over-tagging.** Not everything in a deployment-specific section needs a `⚡` — tag the header, not every paragraph within.
- **Under-tagging.** If a section references KST, Telegram, specific agent names, or private repo paths without a scope marker, add one.
- **Scope drift.** When updating a tagged section, the new content stays under the same scope. Don't re-tag every edit.
- **Leaking deployment details into general skills.** The `agent-contract` skill is a general Hermes Cortex contract — hardcoding Titus/Gisu/Joseph into it makes it unusable by outsiders. Always generalize rules, add examples in blockquotes.
- **Dual-scope headers.** Don't mix general and deployment-specific concepts in the same heading level. Structure subsections under a general parent if needed.

## Verification checklist

- [ ] Does each multi-audience doc have a `🪪 Scope:` banner near the top?
- [ ] Are deployment-specific sections tagged with `⚡` in their heading?
- [ ] Are hardcoded agent names in general skills generalized with blockquote examples?
- [ ] Does the scope banner describe both audiences and what the tag means?
- [ ] Are KST times, Telegram references, and agent names only in `⚡` sections or examples?