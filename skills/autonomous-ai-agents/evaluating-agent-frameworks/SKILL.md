---
name: evaluating-agent-frameworks
description: Evaluate an external agent framework for interop.
---

# Evaluating Agent Frameworks

Assess an external agent framework (Vercel eve, LangGraph, CrewAI, etc.) and decide
what — if anything — our core (Hermes Cortex) must add to support or interoperate
with it. The deliverable is a coverage map, not an essay.

## Workflow

1. **Clone the source — don't trust search summaries.** `git clone --depth 1 <repo>`
   into a throwaway dir, then read the real files: `README.md`, `AGENTS.md` (or the
   framework's equivalent), `docs/concepts/*`, and `docs/protocols/*`. These hold the
   actual authoring surfaces and interop points; web summaries bury them.
   - Reading a docs site instead of a repo? `git clone` the repo and read the
     `docs/` tree locally — it is the same content without auth/paywall/redirect
     friction.

2. **Enumerate the framework's surfaces** and bucket each one: tools, skills,
   memory, subagents/background tasks, schedules, channels (Slack/Discord/Telegram/…),
   sandbox file+exec tools, evals, approvals/HITL, and the **protocols** it speaks
   (MCP, ACP, UCP — see `references/interop-standards.md`).

3. **Grep our core for each surface** to build the coverage map. For every surface,
   classify as *already-have-equivalent* or *net-new*. Example command:
   ```bash
   cd ~/hermes-cortex && grep -ril "<surface|protocol>" . --include='*.md' --include='*.py' --include='*.yaml' --include='*.json' | grep -v '.git/'
   ```
   Grep for the *protocol name and its aliases* (e.g. "agent client protocol",
   "agentclient", "acpx") — a bare acronym greps false positives.

4. **Report as a compact table + one recommendation.** One row per surface: what
the framework offers → what we already have → net-new or not. Lead with the answer:
the single net-new interop surface worth adding (usually a protocol we lack), then the
rest. Everything that maps to an existing equivalent is "no action".

## Rules

- **Recommend only net-new interop standards.** Do not propose adopting a parallel
  framework wholesale or re-implementing capabilities we already have (skills, memory,
  subagents, channels, sandbox tools, evals, approvals). The point is to *interoperate*,
  not to migrate.
- **Net-new is almost always a protocol, not a feature.** Frameworks that are otherwise
  equivalent diverge on the wire: MCP (tools/connections), ACP (agent↔client launch),
  UCP (commerce discovery). See `references/interop-standards.md` for the taxonomy.
- **State what's in-scope vs out-of-scope explicitly** (e.g. commerce/agentic-commerce
  is usually out of scope for our fleet).

## Pitfalls

- **A bare acronym grep yields false positives.** "acp" matches `grok`, `linux`,
  `outlines`, etc. Grep the full protocol name *and* its client/tool aliases, and
  confirm each hit is the real protocol before claiming support or its absence.
- **Web search names the repo but not the architecture.** Searching "<framework>"
  returns marketing pages and changelogs; the interop surfaces (which protocol, over
  what transport) only live in the source's `docs/protocols/` and `docs/concepts/`.
  Clone before you conclude.
- **Do not let a parallel framework's feature list imply we are behind.** Map first;
  most "novel" capabilities (durable state, subagents, sandbox, evals) already have a
  Hermes Cortex equivalent under a different name.
