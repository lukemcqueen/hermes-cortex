#!/usr/bin/env bash
# ch-truncate-system-logs.sh — Truncate ClickHouse verbose system log tables.
set -euo pipefail
CH_CLIENT="docker exec langfuse-clickhouse-1 clickhouse-client"
TABLES=("asynchronous_metric_log" "metric_log" "latency_log" "processors_profile_log" "trace_log" "query_log" "error_log" "part_log")
TRUNCATED=0; SKIPPED=0
for table in "${TABLES[@]}"; do
  if $CH_CLIENT --query "EXISTS system.$table" 2>/dev/null | grep -q 1; then
    $CH_CLIENT --query "TRUNCATE TABLE system.$table" 2>/dev/null && ((TRUNCATED++)) || ((SKIPPED++))
  else
    ((SKIPPED++))
  fi
done
echo "[$(date '+%H:%M')] [ch-truncate] Truncated $TRUNCATED system log tables ($SKIPPED skipped)"
