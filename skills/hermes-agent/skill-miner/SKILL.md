--- Full content (truncated) ---
---
name: skill-miner
description: "Mine loop governance DB, sessions, and memory for reusable skill patterns. Scores findings with nomic-embed-text and reports to Moses via agent inbox."
version: 1.0.0
author: Hermes Cortex
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [mining, skills, patterns, loop-governance, moses]
    related_skills: [soul-refinement, save-lesson, hermes-agent-skill-authoring]
---

# Skill Miner

## What This Is

A script that mines available local data sources on an agent machine for reusable patterns — high-scoring TDD cycles from loop governance, session history patterns, agent memory workflows, and custom skills not yet in the hermes-cortex repo.

Scores findings with `nomic-embed-text` (Ollama) and sends high-confidence results to Moses via the agent inbox for review and upstreaming.

## Location

| File | Path |
|------|------|
| Bash wrapper | `hermes-cortex/src/loop-governance/skill-miner` |
| Python script | `hermes-cortex/src/loop-govern
... [truncated]
--- End skill ---