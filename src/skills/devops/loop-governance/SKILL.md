---
name: loop-governance
version: 1.0.0
category: devops
description: "Loop Governance system: score-cycle, loop-feedback, auto-apply, skill-miner, session-cache, and evaluation pipeline. Tracks code changes via scored cycles, auto-applies low-risk patches, and mines skills from scored data."
author: Hermes Cortex
license: MIT
metadata:
  hermes:
    tags: [scoring, governance, evaluation, tdd, loop, feedback]
---

# Loop Governance

Tracks every code/config change through scored cycles. Each cycle captures what changed, why, and whether tests passed. Data flows through the evaluation pipeline (skill-miner → auto-apply → feedback loop).

## Tools

All tools are symlinked at `~/.local/bin/`:

| Tool | Purpose |
|------|---------|
| `score-cycle` | Log a change cycle: task, code file, pass rate |
| `loop-feedback` | Accept or override a scored cycle's decision |
| `auto-apply` | Auto-apply low-risk config patches from evaluated cycles |
| `loop-config` | View/set runtime config (weights, thresholds) |
| `session-cache-build` | Build/session search cache |
| `skill-miner` | Mine scored cycles for reusable skill patterns |

## Weekly Evaluation Pipeline

1. **Pull scored cycles** from the last 7 days via the loop evaluator
2. **Run skill-miner** to extract reusable patterns from scored data
3. **Run auto-apply** to apply low-risk config changes
4. **Report results**: cycles scored, skills mined, patches applied

## Usage

```
score-cycle --task "<task-id>" --cycle <N> --code-file <path> --pass-pct <rate>
loop-feedback accept <N> --note "..."
loop-feedback override <N> --decision loop|stop|move_on --note "..."
auto-apply --dry-run          # preview without applying
auto-apply                    # apply low-risk patches
loop-config                   # show current config
session-cache-build build     # rebuild session cache
skill-miner                   # mine skills from scored cycles
```

## Scoring

| Dimension | Weight | Description |
|-----------|--------|-------------|
| Completeness | 40% | How complete the change is |
| Quality | 30% | Code quality, tests, documentation |
| Progress | 30% | Progress toward goal |

Thresholds: stop ≥ 8.0, loop ≥ 5.0, move_on ≥ 3.0, no_progress < 2.0 (3 strikes).

## Paths

- Scripts: `~/.hermes-cortex/tools/loop-governance/`
- CLI wrappers: `~/.local/bin/{score-cycle,loop-feedback,auto-apply,loop-config,session-cache-build,skill-miner}`
- DB: `~/.hermes/data/loop-governance.db`
- Config: `~/.hermes/data/loop-governance-config.json`
