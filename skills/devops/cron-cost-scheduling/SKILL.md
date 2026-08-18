---
name: cron-cost-scheduling
version: 1.0.0
category: devops
description: "Schedule LLM crons around provider peak/off-peak windows."
---

# Cron Cost Scheduling

When a provider introduces time-of-use pricing (peak vs off-peak rates) and the
user asks whether LLM crons should be rescheduled to save money. Covers the
verification, classification, and decision procedure. Does NOT cover cost
metering (see `cron-cost-tracking` for the SQLite cost DB) — this is about
scheduling decisions.

## When to Use

- User asks "when are the off-peak hours for <region>?" or "should we move our LLM crons off-peak?"
- A provider announces a pricing change with time-of-use windows
- Reviewing whether existing cron schedules are cost-optimal

## Procedure

### 1. Fetch the LIVE pricing page — never trust search snippets

Search results carry stale windows for months. The old DeepSeek "off-peak
16:30–00:30 UTC" card appeared in search results alongside the live card
(2026-08-18). Always pull the provider's own pricing page and grep the window
text:

```bash
curl -sL <pricing-url> -o /tmp/provider_pricing.html
grep -oiE '.{80}(peak hours|off-peak|UTC|discount).{80}' /tmp/provider_pricing.html
```

Docusaurus/Next.js doc pages render fine as static HTML — no browser needed.
If the pricing table only appears without its footnote, grep for `utc` and
`peak` separately; the footnote is usually below the table.

### 2. Convert the window to the user's local time

Windows are always stated in UTC. Seoul = UTC+9. DeepSeek live card
(2026-08-18): "Peak hours are 01:00 - 04:00 and 06:00 - 10:00 UTC (all other
hours are off-peak)" → Seoul peak = 10:00–13:00 and 15:00–19:00 KST, off-peak
= 19:00–10:00 plus the 13:00–15:00 lunch gap. State the local windows
explicitly in the delivery — don't make the user do the conversion.

### 3. Classify every LLM cron against the windows

Expand each cron's hour/minute fields (ranges `9-17`, lists `18,20,22`,
wildcards) and count peak hits per job. Most night/early-morning crons already
run off-peak — zero change needed; say so instead of proposing mass
rescheduling. Classification table for the DeepSeek case:
`references/deepseek-peak-offpeak-2026-08.md`.

### 4. Decision rule — move only the free wins

- **Do NOT move crons whose purpose is daytime responsiveness** (workday
  auto-remediation: `agent-fixer-workday`, `cortex-bus-workday`,
  `orch-backlog-driver`). Their function beats the pennies (~$0.003–0.007
  extra per peak run at flash rates). Rescheduling them to off-peak-only
  guts the service to save cents.
- **DO move runs sitting just inside the peak boundary** where sliding a few
  minutes costs zero coverage (e.g. 18:50→19:50, 12:00→13:30). These are the
  only free wins.
- Night crons are already off-peak — leave them.

### 5. Quantify before trimming frequency

If `cron-cost-tracking` isn't deployed, deploy it and collect a week of real
spend rather than trimming on estimates. Cron-run spend is often trivial next
to interactive-session spend — the recommendation should say so.

## Pitfalls

- **Stale search snippets outnumber live pages.** A third-party "pricing
  clock" or aggregator blog can keep the old window for months after a rate
  card change. The provider's own page is the only authority.
- **Rate cards change without fanfare.** The DeepSeek peak/off-peak card was
  live by 2026-08-16 while older docs pages still implied the old flat
  pricing. Re-verify the page every time this question comes up.
- **Don't propose moving daytime crons to night.** It reads as cost rigor but
  is actually a service regression — call it out explicitly with the
  per-run cost delta so the user can judge.
- **web_extract may be search-only on some backends** (DDG); if it errors,
  fall back to `curl` + grep as in step 1 — the page is static HTML.

## Verification

- The window quote comes from the provider's own page fetched this session
  (cite the URL and date).
- The local-time conversion is stated explicitly (e.g. "UTC+9 → KST").
- Every LLM cron's peak-hit count is backed by an actual parse of the live
  `cronjob action='list'` output.
- The recommendation names which crons to move, which to keep, and why.

## Related

- `cron-job-management` — naming, install, doctor-sync for any schedule change you do make
- `cron-cost-tracking` — the SQLite cost DB that quantifies the actual spend
