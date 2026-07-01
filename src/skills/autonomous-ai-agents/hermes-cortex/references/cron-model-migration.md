# Cron Model Migration

When switching an LLM-powered cron from one model/provider to another, **three layers** must be updated. Skipping any one leaves inconsistency — docs say one thing, cron runs another, script uses old model.

## The Three Layers

### Layer 1 — Cron definition (jobs.json)

Pin the model/provider so the scheduler uses the right LLM:

```
cronjob(action="update", job_id="<id>", model={"model": "qwen2.5-coder:3b", "provider": "custom:ollama-local"})
```

Get job IDs from `cronjob(action="list")`.

**For no_agent crons:** model/provider fields are irrelevant (scheduler doesn't invoke LLM). Update the script directly (Layer 2).

### Layer 2 — Underlying script

If the cron runs a script that makes its own API calls, the script may hardcode a model:

- `llm-judge-scorer.py` — `JUDGE_MODEL` constant at top
- `offline_code.py` — `GEN_MODEL` / `_detect_gen_model()`

Search: `grep -n "qwen2.5-coder\|deepseek\|judge_model\|JUDGE_MODEL" <script>.py`

### Layer 3 — Documentation

Update all files referencing the old model:

| File | What to update |
|------|---------------|
| `AGENTS.md` | Cron migration table (model + why) |
| Skill `SKILL.md` | Description, prerequisites, troubleshooting |
| `deploy/README-langfuse-clickhouse.md` | Setup instructions, verify commands |
| `docs/model-tier-strategy.md` | Integration points (if wiring changed) |

Search: `grep -rn "qwen2.5-coder:1.5b\|<old-model>" ~/hermes-cortex/ --include="*.md"`

## Current Model Inventory

### qwen2.5-coder:3b (local, zero cost)
`agent-daily-bible-reading`, `agent-daily-soul-refinement`, `memory-pruning`, `orch-process-agent-messages`, `llm-judge-scorer-weekday/weekend`, `local-agent-agents-doc-audit`

### deepseek-v4-flash (API, quality-sensitive)
`agent-auto-remediate`, `agent-weekly-loop-eval`, `process-mcp-agent-inbox-messages`, `local-agent-daily-system-brief`, `local-agent-daily-finance-brief`, `local-agent-daily-news-brief`

## Verification

```bash
# Layer 1 — check cron pin
hermes cron list | grep <cron-name>
# Layer 2 — check script constant
grep "JUDGE_MODEL\|GEN_MODEL" ~/.hermes-cortex/scripts/<script>.py
# Layer 3 — check docs
grep -rn "<old-model>" ~/hermes-cortex/ --include="*.md"
```
