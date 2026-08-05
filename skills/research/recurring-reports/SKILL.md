---
name: recurring-reports
version: 1.0.0
description: "Design and run recurring automated reports: define cadence, metrics, sources, and delivery; wire to cron; verify delivery."
triggers:
  - "recurring report"
  - "automated report"
  - "scheduled report"
  - "report cron"
  - "weekly digest"
---

## When to Use
Use when designing a report that must run on a schedule — define what it measures, where data comes from, how often it runs, and how it's delivered — and when wiring it to cron or verifying delivery.

## Report Spec
Write a one-page spec before building anything:
- **Metrics**: exact definitions with formulas (e.g. engagement rate = engagements/impressions × 100). Every number must be reproducible.
- **Period**: lookback window (daily = last 24h, weekly = last 7 days, monthly = calendar month) with an explicit timezone.
- **Audience**: who reads it and the decision each section supports; put the reader's goal first.
- **Format**: markdown/HTML/PDF/CSV attachment; max length (e.g. one screen for daily digests).

## Data Sources
- **SQL**: read-only queries against the warehouse; parameterize the period; add LIMITs and index hints; snapshot timestamps.
- **APIs**: REST/GraphQL with pagination (see the shopify skill for cursor patterns); handle rate limits with retry/backoff.
- **CSVs**: exported files or bucket paths; validate headers and row counts on every run.
- Log the source and query version in the report footer so numbers can be traced.

## Scheduling (cron)
- Daily: `0 7 * * *` (07:00); weekly: `0 7 * * 1` (Monday); monthly: `0 7 1 * *` (1st).
- In Hermes, create the job with `cronjob action='create'` using a unique, descriptive name; keep the uninstall/cleanup list in sync.
- Never run heavy reports more often than hourly; cache intermediate results.
- Make runs idempotent — re-running the same period must produce the same output.

## Delivery
- **Email**: SMTP with a stable subject prefix (e.g. "[Daily] Revenue Digest"); report as body or attachment.
- **Telegram**: send as a message or file; keep daily digests under message limits.
- **Files**: write to a dated path (`reports/2026-08-05/`) with a rolling retention policy (e.g. 90 days).
- Store recipients, channels, and the failure contact with the job, not inside the script.

## Drift Detection
- Compare key numbers against trailing averages; flag deviations > 2× or outside expected bounds (e.g. revenue down 30% WoW).
- Detect data-source drift: missing columns, zero rows, schema changes, date gaps — log a warning naming the source.
- Detect audience drift: report opens/engagement declining — question whether the metrics still serve the reader.

## Failure Handling
- On failure: retry once with backoff, then notify the failure contact with the error and a partial report if available.
- Log every run: start time, duration, rows processed, success/failure, delivery status.
- A report that silently fails for 3 runs is worse than no report — add a heartbeat/health check to the job.
- When a cron job is renamed or removed, update both the create and uninstall references in the same commit (see AGENTS.md Rule 5).

## Pitfalls
- Don't hardcode dates — derive the period from run time.
- Don't email raw SQL dumps to executives; summarize with a link to detail.
- Don't delete old reports without a retention policy.
- Always verify one real delivery end-to-end before trusting the schedule.
