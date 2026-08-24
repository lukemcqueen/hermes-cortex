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
- **Block condition**: `today_spend(job_id) >= cap`.
- **Fails open**: guard error, missing DB, or insufficient history → the
  run proceeds (a guard failure never silently kills a job).
- **Exempt**: overnight orchestrator jobs (`orch-*` name prefix).
- Preflight marker: `("max_cost", lambda: _preflight_check_max_cost(job))`
  in the scheduler's preflight chain.

## Consequences

- **Protects the $10/day target**: a re-firing job can't blow through its
  budget repeatedly.
- **Self-tuning**: the cap derives from the job's OWN history — no manual
  per-job budgets. A job that never ran has no cap (fails open).
- **Blocker alert**: when blocked, the job stays blocked until config is
  fixed — the alert is sent once (see Gisu's `agent-inbox-workday` MAX_COST
  block, 2026-08-24, where today-spend $0.0116 ≥ cap $0.0089 = p95×2.0).
- **Headroom tuning**: a job that legitimately exceeds p95×2 (price hikes,
  new behavior) needs its headroom raised — not a bypass flag.

## References

- `~/.hermes-cortex/scripts/max_cost_guard.py` (implementation)
- `~/.hermes-cortex/scripts/install-cron-cost-tracking.py` (installer,
  preflight registration)
- ADR-0001 (pricing basis for the cost numbers)
