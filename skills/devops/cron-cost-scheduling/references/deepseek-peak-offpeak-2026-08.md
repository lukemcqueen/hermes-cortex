# DeepSeek peak/off-peak — case detail (2026-08-18)

## The question

User asked (2026-08-18): when are DeepSeek's off-peak hours for Seoul, and
should we reschedule our LLM crons to run only off-peak?

## Authoritative source

Fetched live: https://api-docs.deepseek.com/quick_start/pricing/

Verbatim footnote (below the pricing table):

> (1) Off-peak rates are half of the peak rates. Peak hours are 01:00 - 04:00
> and 06:00 - 10:00 UTC (all other hours are off-peak).

Search snippets were contradictory at the same moment: costbench.com still
showed the OLD card ("off-peak UTC 16:30-00:30") while usagepricing.com and
aipricing.guru described the NEW card effective 2026-08-16. Only the live page
resolved it. Lesson: third-party pricing pages/blog clocks go stale; the
provider's own page is the only authority.

## Seoul (KST = UTC+9) conversion

| Window (UTC) | Window (KST) |
|---|---|
| Peak 01:00–04:00 | Peak 10:00–13:00 |
| Peak 06:00–10:00 | Peak 15:00–19:00 |
| Everything else | Off-peak: 19:00–10:00 + 13:00–15:00 |

Off-peak in Seoul = overnight (19:00–10:00) plus the lunch-hour gap
(13:00–15:00). 17h off-peak, 7h peak per day.

## Rate card (1M tokens, USD)

| Line | Model | OFF-PEAK | PEAK |
|---|---|---|---|
| Input (cache hit) | v4-flash / v4-pro | $0.007 / $0.022 | $0.014 / $0.044 |
| Input (cache miss) | v4-flash / v4-pro | $0.22 / $0.66 | $0.44 / $1.32 |
| Output | v4-flash / v4-pro | $0.66 / $1.98 | $1.32 / $3.96 |

Concurrency limits are NOT time-of-day dependent (2500 flash / 500 pro).

## Our LLM cron classification (Esther host, live cronjob list)

Peak-hit counts computed by expanding each cron's hour/minute fields:

| Cron | Schedule (KST) | Peak hits |
|---|---|---|
| agent-fixer-workday | 49 9-17 * * 1-5 | 6/9 (10:49,11:49,12:49,15:49,16:49,17:49) |
| cortex-bus-workday | 50 9-17 * * 1-5 | 6/9 |
| orch-backlog-driver | 6 8-22 * * * | 7/15 |
| agent-fixer-evening | 50 18,20,22 * * 1-5 | 1/3 (18:50) |
| cortex-bus-evening | 41 18,20,22 * * 1-5 | 1/3 (18:41) |
| agent-llm-judge-scorer-weekday | 0 12,20 * * 1-5 | 1/2 (12:00) |
| all overnight/night crons (03:xx-06:xx, 22:xx-23:xx) | — | 0/1 each |

## Decision taken

- KEEP: workday crons (fixer-workday, bus-workday, backlog-driver) — their
  function is daytime responsiveness; the extra peak cost is ~$0.003–0.007 per
  peak run at flash rates, trivial next to their value.
- FREE WINS proposed: agent-fixer-evening 18:50→19:50, cortex-bus-evening
  18:41→19:41, judge-scorer 12:00→13:30 (lunch off-peak gap). Zero coverage
  loss, half price.
- Gap: cron-cost-tracking DB not deployed on this host (fleet-costs.py:
  "Cost DB not found: ~/.hermes/cron/cron-costs.db") — recommend deploying
  `install-cron-cost-tracking.py` and collecting a week of real spend before
  any frequency trimming.
