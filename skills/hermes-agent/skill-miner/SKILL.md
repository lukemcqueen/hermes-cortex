---
name: skill-miner
description: "Mine loop governance DB, sessions, and memory for reusable skill patterns. Scores findings with nomic-embed-text and reports to the orchestrator via the agent inbox."
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

Scores findings with `nomic-embed-text` (Ollama) and sends high-confidence results to the orchestrator via the agent inbox (`inbox_orchestrator`) for review and upstreaming.

## Location

| File | Path |
|------|------|
| Bash wrapper | `~/.hermes-cortex/scripts/skill-miner-wrapper` (deployed) |
| Python script | `~/hermes-cortex/core/governance/skill_miner.py` |
| Config | `~/.hermes-cortex/state/skill-miner.json` |

## Data Sources

1. **Loop governance DB** — high-scoring TDD cycles (`composite >= 0.7`) with
   clean `feedback_accept` notes. These prove a reusable pattern was found.
2. **Session history** — recurring tool sequences and user corrections.
3. **Agent memory** — MEMORY.md / USER.md entries that describe workflows.
4. **Custom skills** — `~/.hermes/skills/` skills not present in the
   hermes-cortex repo (candidates for upstreaming).

## Scoring

Each finding is embedded with `nomic-embed-text` and compared against the
embedding of "reusable Hermes agent skill pattern". Findings above a
similarity threshold are reported; low-confidence findings are dropped
to keep the report signal-dense.

## Output

The script sends Moses an inbox message with subject
`📬 SKILL MINER: N candidates` containing:

- Skill name (or pattern name)
- Category suggestion
- Evidence (cycle id / session id / memory entry)
- Score
- Suggested trigger/description

Moses reviews the candidates, upstreams the good ones to `skills/`, and
updates `skill-decisions.json` with the disposition.

## Running Manually

```bash
# Full scan + report
python3 ~/hermes-cortex/core/governance/skill_miner.py --send

# Dry run — show candidates without sending
python3 ~/hermes-cortex/core/governance/skill_miner.py --dry-run
```

## Related
- `soul-refinement` — daily SOUL.md refinement (companion mining)
- `save-lesson` — one-off bug-fix lesson capture
- `hermes-agent-skill-authoring` — how to author upstreamable SKILL.md files
- `orch-skill-lifecycle` — the orchestrator's skill intake pipeline
