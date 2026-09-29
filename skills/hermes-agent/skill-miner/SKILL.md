---
name: skill-miner
description: "Use when running the loop-gov skill digest miner."
version: 2.0.0
author: Hermes Cortex
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [mining, skills, loop-governance, digest]
    related_skills: [soul-refinement, save-lesson, hermes-agent-skill-authoring, orch-skill-lifecycle]
---

# Skill Miner (digest collector)

> **Removed-and-replaced (2026-08-02):** the original script that mined the loop
> governance DB, sessions, and memory and inboxed candidate skills to the
> orchestrator no longer exists on this host — neither deployed nor in the repo
> (verified 2026-09-28, esther). Its collection role was absorbed into the
> orchestrator's unified skill-intake pipeline (`orch-skill-lifecycle`, daily
> 04:34 KST). The `--send` / `--dry-run` CLI documented by older versions of
> this file is gone.

## What survives

`skill_miner.py` is now a **skill digest collector for loop-governance scoring** —
it hashes local skill files and feeds the session embedding cache that
`loop_scorer._cache_boost()` uses.

| File | Path |
|------|------|
| Deployed copy (run this) | `~/.hermes-cortex/tools/loop-governance/skill_miner.py` |
| Repo source | `~/hermes-cortex/core/governance/skill_miner.py` |
| Output default | `/tmp/skills-manifest.json` (change manifest: added/removed/unchanged_count) |

## Running

```bash
# Scan skill files (incremental; manifest written only on change)
python3 ~/.hermes-cortex/tools/loop-governance/skill_miner.py collect

# Embed new/changed digests into the session cache (silent when nothing new)
python3 ~/.hermes-cortex/tools/loop-governance/skill_miner.py score
```

Silent-watchdog design: zero output + exit 0 = "no changes" — not a failure.

## Known issue (2026-09-28, esther)

`~/.hermes-cortex/scripts/skill-miner-wrapper` is broken: it execs
`~/.hermes-cortex/scripts/skill_miner.py`, which does not exist on this host.
Use the deployed toolchain path above instead.

## Related

- `orch-skill-lifecycle` — the orchestrator's skill intake pipeline (successor to mining)
- `soul-refinement` — daily SOUL.md refinement (companion mining)
- `save-lesson` — one-off bug-fix lesson capture
- `hermes-agent-skill-authoring` — how to author upstreamable SKILL.md files
