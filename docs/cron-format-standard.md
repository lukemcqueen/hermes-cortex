# Cron Output Format Standard

> **Canonical reference for all LLM-driven cron job output formatting.**
> See the `cron-format-standard` skill for the full standard with examples.

## Summary

Every LLM-driven cron delivery must follow this exact structure:

```
<cron-name> (<cron-id>) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — <title>: <summary>
- <evidence>
- <evidence>

Phase 2 — <title>: <summary>
- <evidence>

Phase 3 — <title>: <summary>
- <evidence>

Result: <one-line verdict>

📊 <model> (<provider>) | <cost>/run ≈ <monthly>/mo
```

## Key Rules

| Rule | Detail |
|------|--------|
| **Concrete examples** | Never use placeholders like `[N]`, `<Title>`, `<value>` in the example block. LLMs mimic concrete text, not abstract templates. |
| **Header** | `(JOB_ID) [YYYY-MM-DD HH:MM KST]` then `-------------` on the next line |
| **Phases** | Minimum 3 phases. Each starts with `Phase N — Topic: Summary on same line` |
| **Result** | `Result: <one-line verdict>` — always before the cost footer |
| **Cost footer** | `📊 <model> (<provider>) | <cost>/run ≈ <monthly>/mo` — always the last line |
| **Silent** | `[SILENT]` — the only acceptable output when nothing to report |

## Cost Calculation

Cost is proportional to run frequency. At `$0.006/run` (deepseek-v4-flash rate):

| Frequency | Runs/month | Monthly cost |
|-----------|-----------|-------------|
| Once (overnight) | ~4 | $0.002 |
| Every 2h evening | ~12 | $0.01 |
| Hourly workday | ~45 | $0.03 |
| 6x/week | ~26 | $0.18 |
| Weekly | ~4 | $0.02 |
| Daily | ~30 | $0.18 |

## Related

- `docs/cron-schedules.md` — canonical schedule reference for all crons
- `cron-format-standard` skill — full standard with 3 concrete examples and workflow
- `skills/devops/cron-format-standard/SKILL.md` — skill source in repo
