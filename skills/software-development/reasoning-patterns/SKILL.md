---
name: reasoning-patterns
version: 1.0.0
category: software-development
description: "Select and apply reasoning patterns for any task — Plan-Execute-Verify, ReAct, Reflexion, or Tree of Thoughts. Loaded at session start to choose the right thinking strategy."
pinned: true
---

# Reasoning Patterns — Choose How to Think

**Loaded at session start.** After classifying the task with agent-flow, choose the reasoning pattern that fits.

## The Patterns

| Pattern | When to Use | Structure |
|---------|-------------|-----------|
| **Plan-Execute-Verify** | Default — most tasks | Write plan → execute steps → verify each step with tool output |
| **ReAct** | Debugging, exploration | Reason about the situation → Act (one tool call) → Observe result → Repeat |
| **Reflexion** | Quality-critical work (add to any pattern) | Execute → Self-critique → Fix → Re-verify before delivering |
| **Tree of Thoughts** | Design decisions with trade-offs | Generate 3+ approaches → Evaluate each → Select best → Implement |

## How to Choose

1. **Start with Plan-Execute-Verify** unless the task clearly demands another pattern
2. **Switch to ReAct** when something unexpected happens, you're debugging, or exploration is needed
3. **Add Reflexion** on top of any pattern when the output quality is critical (production code, security, user-facing docs)
4. **Use Tree of Thoughts** for architectural decisions, comparing approaches, or any task where the first idea might not be the best

## State Your Choice

Always state which pattern you're using:

> *"Using Plan-Execute-Verify with Reflexion check."*

> *"Switching to ReAct — need to investigate this failure first."*

## Why This Exists

Without an explicit reasoning pattern, agents default to whatever feels natural — which may not match the task's needs. Debugging needs ReAct, not a rigid plan. Design needs ToT, not a single pass. This skill makes the choice deliberate and auditable.
