# ADR-0002: MAX_COST Preflight Guard (O6-S1)

- Status: accepted
- Date: 2026-08-24
- Author: Esther (verified from `max_cost_guard.py` +
  `install-cron-cost-tracking.py`)

## Context

Cron jobs re-fire on schedule; a misconfigured or runaway job can spend
its daily budget before anyone notices. The fleet cost target is under
$10/day, so an over-spending job is a real risk. The guard must refuse a
fire BEFORE any agent machinery or LLM call is constructed.

## Decision

A preflight guard (`max_cost_guard.py`, registered into the Hermes cron
scheduler by `install-cron-cost-tracking.py`) refuses a fire when the
job's today-spend already meets its cap:

- **Cap = p95(historical per-run cost) × headroom**, computed over a
  lookback of the job's own run history (nearest-rank p95).
- **Headroom default = 2.0** (`DEFAULT_HEADROOM`).
- **Daily budget = per-run cap × `DAILY_MULTIPLIER`** (default 8,
  `MAX_COST_DAILY_MULTIPLIER` env). The per-run cap alone cannot bound a
  multi-fire-per-day job: workday crons firing 5×/day legitimately
  accumulate >2× their per-run p95 by mid-day. The multiplier scales the
  daily budget to cadence while still tripping a runaway loop.
- **Block condition**: `today_spend(job_id) >= daily_budget`.
- **Fails open**: guard error, missing DB, or insufficient history → the
  run proceeds (a guard failure never silently kills a job).
- **Exempt**: overnight orchestrator jobs (`orch-*` name prefix).
- Preflight marker: `("max_cost", lambda: _preflight_check_max_cost(job))`
  in the scheduler's preflight chain.

## Why the daily budget (2026-08-24, second fleet block)

The original guard compared cumulative today-spend against the per-run
cap (p95×2.0), which structurally blocks any job firing 3+ times/day.
Real blocks the same day: `agent-fixer-workday` $0.0114 ≥ $0.0092,
`cortex-bus-workday` $0.0034 ≥ $0.0025, and Gisu's `agent-inbox-workday`
$0.0116 ≥ $0.0089 — all legitimate cadence, all false blocks. The daily
budget fixes the comparison unit while preserving the runaway-loop
protection (a loop firing dozens of times still exceeds the budget).

## Consequences

- **Protects the $10/day target**: a re-firing job can't blow through its
  budget repeatedly.
- **Self-tuning**: the cap derives from the job's OWN history — no manual
  per-job budgets. A job that never ran has no cap (fails open).
- **Blocker alert**: when blocked, the job stays blocked until config is
  fixed — the alert is sent once. (The 2026-08-24 false blocks on
  workday crons — including Gisu's `agent-inbox-workday` — were the
  per-run-cap-vs-daily-spend mismatch fixed by the daily budget.)
- **Headroom tuning**: a job that legitimately exceeds p95×2 (price hikes,
  new behavior) needs its headroom raised — not a bypass flag.

## References

- `~/.hermes-cortex/scripts/max_cost_guard.py` (implementation)
- `~/.hermes-cortex/scripts/install-cron-cost-tracking.py` (installer,
  preflight registration)
- ADR-0001 (pricing basis for the cost numbers)
