--- Full content (truncated) ---
---
name: cron-no-agent-conversion
version: 1.0.0
category: devops
description: "Convert LLM-driven Hermes agent crons to no_agent scripts with targeted API calls. Maximizes deterministic Python work, uses LLM only for the single creative task the model uniquely provides."
author: Hermes Cortex
license: MIT
metadata:
  hermes:
    tags: [cron, no-agent, automation, script, conversion, deepseek, ollama]
---

# Cron → no_agent Script Conversion

A class-level pattern: replace full agent-loop crons (which run an LLM agent with tools each tick) with lightweight `no_agent=true` scripts that handle deterministic orchestration in Python and make a single API call for creative work.

## When to Convert

Convert when the cron's LLM produces **5-50 token useless output** (1 API call, no real work). This is the signature of a small model struggling with a multi-step agentic workflow.

Small local models like `qwen2.5-coder:3b` (3B params) are reliable for:
- ✅ Single-shot tasks (code gen, classification
... [truncated]
--- End skill ---