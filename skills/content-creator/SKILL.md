---
name: content-creator
version: 1.0.0
description: "Deprecated redirect skill that routes legacy 'content creator' requests to the correct specialist. Use when a user invokes 'content creator', asks to write a blog post, article, guide, or brand voice analysis (routes to content-production), or asks to plan content, build a topic cluster, or create a content calendar (routes to content-strategy). Does not handle requests directly — identifies user intent and redirects to content-production for writing/SEO/brand-voice tasks or content-strategy for planning tasks."
triggers:
  - "content creation"
  - "write content"
  - "blog post"
  - "content writer"
---

# Content Creator — Redirect (deprecated)

This skill is a routing stub by design. It does NOT handle requests itself —
identify the intent and hand off to the specialist skill.

## Route

| User wants... | Load and follow |
|---|---|
| Write a blog post, article, guide, whitepaper | `content-production` |
| Brand voice analysis, tone guidelines | `content-production` |
| Content plan, topic cluster, calendar | `content-strategy` |
| Humanize AI-sounding text | `content-humanizer` |
| Anything else under "content creator" | Classify with `agent-flow` first, then route |

## Rules

1. Always load the target skill and follow its workflow — never improvise
   a content pipeline here.
2. Never produce content directly from this skill's context.
3. If the user's request matches none of the routes, use `agent-flow` to
   classify before answering.
