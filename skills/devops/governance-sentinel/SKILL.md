---
name: governance-sentinel
version: 1.0.0
category: devops
description: >-
  Recurring governance introspection — scrape brain sync snapshots for codepath
  patterns, compile weekly insights, and store verdicts in dream.json for
  retrospection. Runs as a sentinel after mycortex-update-sync, before daily
  police logs.
---

# Governance Sentinel v1.0.0

> **Scraping brain sync state, extracting codepath patterns, and producing
> governance insights for weekly retrospection.** This is the sentinel that
> sits after mycortex-update-sync and before daily police logs in the pipeline.

## When to Use

Load this skill when the task involves:
- "sentinel" related to brain sync, governance, or reflection
- Scraping brain snapshots for patterns
- Writing or updating `dream.json`
- Weekly retrospection or governance insight compilation
- Pipeline-position-aware sentinel work (between mycortex update and police logs)

## Pipeline Position

```
mycortex-update-sync → GOVERNANCE-SENTINEL → daily police logs
```

The sentinel runs **after** the brain snapshot is refreshed (so it sees the
latest state) and **before** the police logs (so its insights are available
for the daily governance report).

## What It Does

1. **Scrape brain sync snapshots** — read the latest mycortex sync output for
   codepath patterns (repeated file paths, recurring operation types,
   agent activity signatures).
2. **Extract patterns** — cluster the scraped activity into codepath families:
   which scripts, crons, or workflows recur most.
3. **Compile weekly insights** — aggregate the daily observations into
   weekly governance themes (drift sources, hot paths, risky patterns).
4. **Store verdicts in `dream.json`** — each run appends a verdict record
   (timestamp, pattern summary, confidence, suggested follow-up) for
   retrospection. `dream.json` is the sentinel's persistent memory.

## dream.json Format

```json
{
  "verdicts": [
    {
      "ts": "2026-08-01T03:00:00Z",
      "patterns": ["ops/scripts/cortex-update.sh x4", "cron agent-fixer-* x3"],
      "confidence": 0.8,
      "suggestion": "Review cortex-update lock purge interaction"
    }
  ]
}
```

## Running the Sentinel

```bash
# Manual run
python3 ~/hermes-cortex/src/loop-governance/governance-sentinel.py

# Verify the verdict landed
python3 -c "import json; print(len(json.load(open('~/.hermes-cortex/state/dream.json'))['verdicts']))"
```

## Related
- `loop-governance` — the cycle-scoring system it reflects on
- `legacy-brain-maintenance` — the sync step it follows
- `soul-refinement` — daily SOUL.md insights (companion)
- `orch-weekly-auto-fix` — weekly opportunity scan (consumer of insights)
