# Schedule-Aware Stale Cron Detection

## Problem

The original stale-cron check used a hardcoded 86400s (24h) threshold. This
caused **false positives** on weekly crons like `package-integrity-scan` and
`session-cache-build` (both on `0 6 * * 1` / Monday-only schedules). After
48h of no run (Tuesday/Wednesday), they were flagged as "stale" despite being
exactly on schedule.

## Solution: `_estimate_interval()`

Added to both `health-server.py` and `health-vector.py`. Computes the
expected interval from the cron expression, then flags stale when
`elapsed > 2 × expected`.

### Logic priority (most significant field wins)

1. **Day-of-month** constrained → monthly (30d)
2. **Weekday** constrained → weekly (7d) or max-gap for multi-day schedules
   - Single weekday (e.g. `1` for Monday) → 7d
   - Multi-day (e.g. `1-5` for Mon-Fri) → max gap between days (3d for Fri→Mon)
3. **Hour** constrained (no weekday) → daily or sub-daily
   - Single hour → 24h
   - Comma-separated (e.g. `14,20`) → **max** gap including overnight wrap
     (e.g. `14,20` → gaps `[6, 18]` → max=18h, so stale after 36h)
   - Range (e.g. `9-18`) → 1h
   - Step (e.g. `*/6`) → step × 1h
4. **Only minute** constrained → sub-hourly
   - `*/15` → 15min, `*/5` → 5min
5. **Everything wildcarded** → 24h fallback

### Why max-gap, not min-gap

For comma-separated hour fields, using min-gap is wrong:

```
0 14,20 * * *   # runs at 2pm and 8pm daily
```

- Gaps between runs: 6h (14→20) and 18h (20→14 next day)
- **min-gap (6h)**: 2× = 12h → flags as stale 12h after last 20:00 run,
  even though the next scheduled run at 14:00 is still 6h away
- **max-gap (18h)**: 2× = 36h → correctly allows the overnight gap

### Dict vs string schedules in jobs.json

Hermes stores cron schedules in `~/.hermes/cron/jobs.json` as *dicts*,
not strings:

```json
{
  "schedule": {
    "kind": "cron",
    "expr": "0 6 * * 1",
    "display": "0 6 * * 1"
  }
}
```

When reading `j.get("schedule", "")`, the result is a dict, not a string.
Calling `.strip()` on it raises `AttributeError: 'dict' object has no attribute 'strip'`.

**Fix:** Handle both formats:
```python
if isinstance(schedule, dict):
    s = (schedule.get("expr") or schedule.get("display") or "").strip()
else:
    s = str(schedule).strip()
```

The `'every N'` format (e.g. `"every 360m"`) IS stored as a plain string.

### Testing matrix

| Schedule | Expected interval | Stale after (2×) |
|----------|-----------------|-------------------|
| `0 9 * * *` (daily) | 24h | 48h |
| `0 6 * * 1` (weekly Mon) | 7d | 14d |
| `0 9,18 * * 1-5` (Mon-Fri) | 3d (Fri→Mon gap) | 6d |
| `0 14,20 * * *` (twice daily) | 18h (overnight) | 36h |
| `*/15 * * * *` (every 15min) | 15min | 30min |
| `0 */6 * * *` (every 6h) | 6h | 12h |
| `every 360m` | 6h | 12h |
