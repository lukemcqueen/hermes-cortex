#!/usr/bin/env bash
# ClickHouse merge watchdog — silent when healthy, alerts on merge failure loops.
# Designed for no_agent=True cron: stdout is delivered verbatim as the message.
# State file tracks failure count between runs to detect increases.
set -euo pipefail

STATE_FILE="${HOME}/.hermes-cortex/scripts/state/clickhouse-merge-watchdog.state"
CONTAINER="langfuse-clickhouse-1"
QUERY="SELECT value FROM system.metrics WHERE metric = 'TotalMergeFailures'"
DETAILS_QUERY="SELECT
    (SELECT value FROM system.metrics WHERE metric = 'TotalMergeFailures') AS total_failures,
    (SELECT value FROM system.metrics WHERE metric = 'NonAbortedMergeFailures') AS non_aborted,
    (SELECT value FROM system.metrics WHERE metric = 'Merge') AS active_merges,
    (SELECT value FROM system.metrics WHERE metric = 'BackgroundMergesAndMutationsPoolTask') AS pool_tasks,
    (SELECT value FROM system.metrics WHERE metric = 'MergeTreeBackgroundExecutorThreadsActive') AS bg_active
FORMAT TSV"

# Ensure state directory exists
mkdir -p "$(dirname "$STATE_FILE")"

# Query ClickHouse
if ! FAILURES=$(docker exec "$CONTAINER" clickhouse-client --query "$QUERY" 2>/dev/null); then
    echo "⚠️  ClickHouse merge watchdog: cannot reach container $CONTAINER"
    exit 1
fi

FAILURES="${FAILURES%%[[:space:]]*}"
FAILURES="${FAILURES:-0}"

# Read last known value
LAST_FAILURES=0
if [[ -f "$STATE_FILE" ]]; then
    LAST_FAILURES=$(<"$STATE_FILE")
fi

# Check for increase
if [[ "$FAILURES" -gt "$LAST_FAILURES" ]]; then
    NEW=$((FAILURES - LAST_FAILURES))
    DETAILS=$(docker exec "$CONTAINER" clickhouse-client --query "$DETAILS_QUERY" 2>/dev/null || echo "query failed")

    echo "🔴 ClickHouse merge failure loop detected"
    echo ""
    echo "TotalMergeFailures: $FAILURES (+${NEW} since last check)"
    echo ""
    echo "Details:"
    echo "$DETAILS"
    echo ""
    echo "Fix: identify and drop the corrupt part(s) via"
    echo "  docker exec $CONTAINER clickhouse-client"
    echo "  → ALTER TABLE <database>.<table> DROP PART '<part_name>'"
    echo "  then docker restart $CONTAINER"
    echo ""
    echo "Run: systemctl --user restart clickhouse-merge-watchdog (or crontab -e) to reset state."

    # Also alert on sustained high failures
    if [[ "$FAILURES" -gt 1000 ]]; then
        echo ""
        echo "⚠️  More than 1,000 total failures — persistent corruption."
    fi

    # Update state so we track next run's delta
    echo "$FAILURES" > "$STATE_FILE"
    exit 0
fi

# Also alert if there's a suspicious state: all bg threads active, no merges, no pool tasks
# but only if failures > 0 (indicates prior failures with stuck threads)
if [[ "$FAILURES" -gt 0 ]]; then
    DETAILS=$(docker exec "$CONTAINER" clickhouse-client --query "$DETAILS_QUERY" 2>/dev/null || echo "query failed")
    BG_ACTIVE=$(echo "$DETAILS" | awk '{print $5}')
    ACTIVE_MERGES=$(echo "$DETAILS" | awk '{print $3}')
    POOL_TASKS=$(echo "$DETAILS" | awk '{print $4}')

    if [[ "$BG_ACTIVE" -gt 0 && "$ACTIVE_MERGES" -eq 0 && "$POOL_TASKS" -eq 0 ]]; then
        echo "🟡 ClickHouse: $BG_ACTIVE bg threads active but no merges running (${FAILURES} prior failures)"
        echo ""
        echo "$DETAILS"
    fi
fi

# Update state silently on healthy runs too (baseline tracking)
echo "$FAILURES" > "$STATE_FILE"
exit 0
