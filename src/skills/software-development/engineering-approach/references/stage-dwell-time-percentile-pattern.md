# Stage Dwell-Time Percentile (P95) Computation

## Problem

You have entities that move through a state machine (calculated → reviewed → approved → confirmed → settled). Each state transition is logged as a separate record. You need to compute the P95 time an entity spends **at each stage** across all completed entities.

## Data Model

```
DistributionRun (id, calculated_at, reviewed_at, ...)
DistributionRunTransition (run_id, from_status, to_status, created_at, actor)
```

Each run can have N transitions. Transitions are ordered by `created_at` per run.

## Algorithm

```python
def compute_stage_p95s(db: Session) -> dict[str, float | None]:
    """P95 dwell time (hours) per stage across completed runs."""

    # 1. Get all runs that have at least one transition
    run_ids = [r[0] for r in db.query(Transition.run_id).distinct().all()]
    runs = db.query(Run).filter(Run.id.in_(run_ids)).all()

    # 2. For each run, measure time spent at each stage
    dwells: dict[str, list[float]] = defaultdict(list)
    for run in runs:
        trans = (
            db.query(Transition)
            .filter(Transition.run_id == run.id)
            .order_by(Transition.created_at)
            .all()
        )
        if len(trans) < 2:
            continue

        # Gap from run start to first transition → first transition's *destination* stage
        if run.calculated_at and trans[0].created_at:
            gap = (trans[0].created_at - run.calculated_at).total_seconds() / 3600
            if gap > 0:
                dwells[trans[0].to_status].append(gap)

        # Gaps between consecutive transitions → destination of the *later* transition
        for i in range(1, len(trans)):
            if trans[i-1].created_at and trans[i].created_at:
                gap = (trans[i].created_at - trans[i-1].created_at).total_seconds() / 3600
                if gap > 0:
                    dwells[trans[i].to_status].append(gap)

    # 3. Compute P95 per status
    result = {}
    for status, values in dwells.items():
        if len(values) < 2:  # need at least 2 data points for meaningful percentile
            continue
        values.sort()
        idx = int(len(values) * 0.95)
        result[status] = round(values[min(idx, len(values) - 1)], 1)

    return result
```

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Group by run_id, **not** by transition type | Transitions from different runs are parallel, not sequential. Mixing them produces meaningless gaps. |
| Attribute gap to the **destination** status | The time between transition A→B and B→C is the time spent in status B. So the gap between transitions goes to `trans[i].to_status`. |
| Minimum 2 data points per stage | Fewer than 2 produces meaningless percentiles. Return `None` which the frontend handles by showing "Insufficient data". |
| Hours, not seconds | Hours are the right unit for distribution cycles that span days. Convert to days or minutes as appropriate for your domain. |

## Health Color Thresholds (for frontend visualization)

Compare each run's current dwell time against the P95 for that stage:

| Condition | Color | Label |
|---|---|---|
| Elapsed time < 50% of P95 | Green | "On track" |
| Elapsed time 50–90% of P95 | Yellow | "Slowing" |
| Elapsed time > 90% of P95 | Red | "Stalled" |
| No P95 data available | Gray | — |

If a stage has multiple runs, use the worst (reddest) color across all runs at that stage.

## Pitfalls

- **P95 requires enough transitions.** With sparse data (<2 transitions per stage per run), return `None` rather than a misleading number. Frontend should show "Insufficient data".
- **Run IDs must be stable.** If runs can be deleted or re-created with different IDs between calculation cycles, the historical P95 drifts. Only consider completed/settled runs for the calculation.
- **Timezone alignment.** All timestamps must be in the same timezone (preferably UTC) to avoid negative gaps from DST transitions.
- **Bulk vs real-time.** This pattern is best computed on demand or cached every few minutes. Do not compute P95 on every page load if there are thousands of runs — cache it.
