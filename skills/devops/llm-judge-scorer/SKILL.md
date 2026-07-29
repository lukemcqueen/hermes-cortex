---
name: llm-judge-scorer
version: 1.0.0
category: devops
description: "LLM-as-Judge trace quality scorer. Evaluates Hermes conversation traces in Langfuse using a local Ollama model and posts quality scores back to Langfuse. Cron schedule: weekdays 12pm/8pm, weekends 10pm KST."
author: Hermes Cortex
license: MIT
metadata:
  hermes:
    tags: [langfuse, scoring, quality, eval, ollama, cron]
---

# LLM Judge Scorer

A `no_agent` cron script that evaluates Hermes conversation traces in Langfuse using `qwen2.5-coder:3b` as the judge model. Scores are posted back to Langfuse under `helpfulness`, `clarity`, `depth`, and `overall`.

## How It Works

```
Langfuse (traces)
    │
    ▼
llm-judge-scorer.py (no_agent cron)
    │
    ├── Fetches unscored traces from past 14 days
    ├── Sends input/output to Ollama (qwen2.5-coder:3b)
    ├── Parses JSON response: helpfulness, clarity, depth, overall
    └── Posts scores back to Langfuse API
```

## Prerequisites

| Dependency | Check | Fix |
|---|---|---|
| Langfuse running | `curl -s http://localhost:3000/api/public/health` | `docker compose -f ~/langfuse/docker-compose.yml up -d` |
| Ollama running | `curl -s http://localhost:11434/api/tags` | `brew services start ollama` |
| Judge model | `ollama list \| grep qwen2.5-coder:3b` | `ollama pull qwen2.5-coder:3b` |
| Env file | `~/.hermes-cortex/.env` (symlink to `~/langfuse/.env`) or `--env-path` | `ln -sf ~/langfuse/.env ~/.hermes-cortex/.env` |

## Invocation

```bash
# Default (finds unscored traces, evaluates, posts scores)
python3 ~/.hermes/scripts/llm-judge-scorer.py

# Dry run (no scores posted)
python3 ~/.hermes/scripts/llm-judge-scorer.py --dry-run

# Specific trace
python3 ~/.hermes/scripts/llm-judge-scorer.py --trace-id=<id>

# Quiet mode (silent when no traces to score)
python3 ~/.hermes/scripts/llm-judge-scorer.py --quiet

# Custom env path
python3 ~/.hermes/scripts/llm-judge-scorer.py --env-path ~/langfuse/.env
```

## Score Interpretation

| Score | Name | Meaning |
|---|---|---|
| 1-5 | helpfulness | How well the response addresses the user's request |
| 1-5 | clarity | Structure, formatting, readability |
| 1-5 | depth | Substance beyond surface-level |
| 1-10 | overall | Holistic quality assessment |

## What Agents Should Do With Low Scores

When `overall` < 5 on your traces:

- **Be more thorough** — include concrete code, verify with actual execution, don't summarize plans
- **Improve readability** — use proper formatting, concise explanations
- **Check completeness** — did you answer the full question or just the first part?
- **Verify before claiming** — run tools, don't fabricate results

## Troubleshooting

| Symptom | Fix |
|---|---|
| `FileNotFoundError: .env` | Create symlink: `ln -sf ~/langfuse/.env ~/.hermes-cortex/.env` |
| `HTTP 401` from Langfuse | Check `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` and `SECRET_KEY` in `.env` |
| `ollama: connection refused` | `brew services start ollama` or `ollama serve` |
| `Model not found` | `ollama pull qwen2.5-coder:3b` |
| Zero traces scored | Normal if all traces already scored. Check Langfuse has traces. |

## Deployment

Script lives at `ops/scripts/manage/llm-judge-scorer.py` in the cortex repo.
Deployed to `~/.hermes/scripts/llm-judge-scorer.py` via `cortex-update`.