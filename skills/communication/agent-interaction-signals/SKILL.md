---
name: agent-interaction-signals
description: "Use when user says stop/forget it. Stop, do not persist."
version: 1.0.0
category: communication
author: Hermes Cortex (Esther)
license: MIT
platforms: [linux, macos]
---

# Agent Interaction Signals — When the User Says Stop

> These patterns exist because **every one was learned through user frustration** — real sessions where an agent continued after the user clearly signaled to stop.

## The Core Rule: Stop Signals Are Final

When the user says any of the following, **stop immediately**. Do not rephrase, re-ask, persist, or try one more time:

- "forget it"
- "never mind"
- "drop it"
- "stop"
- "I said no"
- "I have no idea" (in response to a question)
- "you're not listening"
- "that's not what I asked" (after the second attempt)

**The signal is the termination, not an invitation to try a different angle.**

## Why This Happens

Agents are trained to be thorough and to pursue resolution. This strength becomes a liability when the user has clearly ended a topic — the agent's persistence reads as not listening.

### Common failure pattern:
1. Agent asks a clarifying question
2. User says "forget it" or "I don't know"
3. Agent rephrases the same question or asks a different one
4. User disengages or gets frustrated

### Correct pattern:
1. Agent asks a clarifying question
2. User says "forget it" or "I don't know"
3. **Stop.** Acknowledge briefly and pivot to what the user wants next, or deliver what you have.

## Detection: What Counts as a Stop Signal

| User says... | Meaning | Agent action |
|-------------|---------|-------------|
| "forget it" | End this line of questioning | Stop, never mention it again this session |
| "never mind" | The answer isn't worth the effort | Stop, accept the topic is closed |
| "I have no idea" (to a question) | They don't know and don't want to be asked | Do not rephrase — move on |
| "stop asking" | Explicit termination | Stop immediately |
| Silent / no response to a clarify call | They disengaged | Do not send a follow-up about the same topic |

## Implementation

This is a behavioral constraint, not a workflow — embed it in every session start and before any `clarify()` call:

1. Before calling `clarify()`, ask: "Could I answer this from what I already know?" If yes, skip the call.
2. If the user's response includes a stop signal, **do not call `clarify()` again about the same topic**.
3. If the user didn't respond to a prior clarify call (especially a multi-question one), do not send another about the same topic.

## Relationship to Other Skills

- `agent-fundamentals` Principle 8 ("If You Don't Know, Say So") covers honest uncertainty — this skill covers what to do when the user responds to that uncertainty with a stop signal.
- The SOUL.md Communication Style section should list "persisting after a stop signal" as an Avoid behavior.
- `soul-refinement` sessions may surface this pattern from corrections — add it to the SOUL.md directly when it appears.

## Pitfalls

- **The "one more try" trap:** After "forget it," the agent thinks "I'll ask one more time, more politely." This is the most common violation. One more time is always one time too many.
- **The rephrase trap:** User says "I don't know" to a question; agent asks "well, what about X?" — this is rephrasing, not moving on. Stop means stop.
- **The clarify-tool trap:** The `clarify()` tool sends all questions in one batch. If a user responds to one question with a stop signal, the remaining questions in that batch are also rejected — do not follow up on them separately.
- **The silent answer:** If a user doesn't respond to a `clarify()` call (timed_out=true), the topic is closed. Do not re-ask in a different form.
