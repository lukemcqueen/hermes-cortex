#!/usr/bin/env bash
# ch-truncate-system-logs.sh — Truncate ClickHouse verbose system log tables
# that have exceeded their size threshold. Silent on success (empty stdout =
# no delivery). Designed for weekly cron schedule.
set -euo pipefail

CONTAINER="langfuse-clickhouse-1"
CH_CLIENT="docker exec $CONTAINER clickhouse-client"

# Thresholds in bytes — table only truncated when it exceeds this size
THRESHOLD_10MB=$((10 * 1024 * 1024))
THRESHOLD_25MB=$((25 * 1024 * 1024))

# Parallel arrays: tables and their thresholds (bash 3.x compat — no associative arrays)
TABLES=("asynchronous_metric_log" "trace_log" "query_log" "processors_profile_log" "metric_log" "text_log")
THRESHOLDS=("$THRESHOLD_25MB" "$THRESHOLD_10MB" "$THRESHOLD_10MB" "$THRESHOLD_10MB" "$THRESHOLD_10MB" "$THRESHOLD_25MB")

# Note: latency_log (Langfuse SDK data) and error_log (diagnostic) are excluded
# intentionally — they're small and useful.
# text_log added 2026-08-09: the merge-failure MEMORY_LIMIT_EXCEEDED storm
# filled text_log to 2.78 GB — it must be truncated like the others.

TRUNCATED=0
for i in "${!TABLES[@]}"; do
  TABLE=${TABLES[$i]}
  THRESHOLD=${THRESHOLDS[$i]}
  BYTES=$($CH_CLIENT --query "
    SELECT sum(bytes_on_disk)
    FROM system.parts
    WHERE active=1 AND table='${TABLE}' AND database='system'
  " 2>/dev/null | tr -d ' \n')

  BYTES=${BYTES:-0}

  if [ "$BYTES" -gt "$THRESHOLD" ]; then
    MB=$((BYTES / 1048576))
    $CH_CLIENT --query "TRUNCATE TABLE system.${TABLE}" 2>/dev/null
    echo "🧹 Truncated system.${TABLE} (${MB} MB)"
    TRUNCATED=1
  fi
done

# Silent exit = no delivery when healthy. Exit 0 in ALL cases — the
# truncation messages above are informational, not errors. A non-zero
# exit here makes the cron report "Script exited with code 1" every
# time a table was actually truncated (false failure).
exit 0