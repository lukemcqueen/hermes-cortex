#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  prod-watchdog.sh — Check production sites, auto-remediate
#                     on repeated failure
#
#  Silent when all healthy (watchdog pattern — only output on
#  issues). Designed for no_agent cron (every 2h at :47).
#
#  Auto-remediation: if a container is UNHEALTHY for 2+
#  consecutive checks, the script restarts the container via
#  docker compose, discovers the project directory dynamically
#  from Docker labels.
#
#  State: persistent counter in ~/.hermes/state/watchdog-*.count
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SITES=(
  "example.com|puma"
  "site2.com|static"
)

STATE_DIR="${HOME}/.hermes/state"
mkdir -p "$STATE_DIR"

ERRORS=""
REMEDIATED=""

for entry in "${SITES[@]}"; do
  IFS='|' read -r domain type container <<< "$entry"
  issues=""

  if [ "$type" = "puma" ]; then
    status=$(docker ps --filter "name=^/${container}$" --format "{{.Status}}" 2>/dev/null)
    service="${container%%-*}"

    if [ -z "$status" ]; then
      issues+="  ❌ Container $container -- NOT RUNNING\n"
    elif echo "$status" | grep -q "(unhealthy)"; then
      # ── Auto-remediation ──────────────────────────────────
      state_file="${STATE_DIR}/watchdog-${container}.count"
      fail_count=0
      [ -f "$state_file" ] && fail_count=$(cat "$state_file" 2>/dev/null || echo 0)
      fail_count=$((fail_count + 1))
      echo "$fail_count" > "$state_file"

      issues+="  ⚠️ Container $container -- UNHEALTHY ($status) [fail #${fail_count}]\n"

      if [ "$fail_count" -ge 2 ]; then
        REMEDIATED+="  🔄 Restarting $container (unhealthy for ${fail_count} consecutive checks)...\n"
        echo 0 > "$state_file"
        project_dir=$(docker inspect "$container" \
          --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null || true)
        if [ -n "$project_dir" ] && [ -f "$project_dir/docker-compose.yml" ]; then
          (cd "$project_dir" && docker compose restart "$service" 2>&1) || true
          REMEDIATED+="  ✅ Restart issued for $container\n"
        fi
      fi
    else
      rm -f "${STATE_DIR}/watchdog-${container}.count"
    fi
  fi

  http_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 15 "https://$domain/" 2>&1)
  if [ -z "$http_code" ] || [ "$http_code" = "000" ]; then
    issues+="  ❌ https://$domain/ -- no response\n"
  elif [ "$http_code" = "502" ] || [ "$http_code" = "503" ]; then
    issues+="  ⚠️ https://$domain/ -- HTTP $http_code (backend down?)\n"
  fi

  [ -n "$issues" ] && ERRORS+="🔻 $domain\n$issues"
done

output=""
[ -n "$ERRORS" ] && output+="━━━ Production Site Watchdog ━━━\n\n$ERRORS"
[ -n "$REMEDIATED" ] && output+="━━━ Auto-Remediation ━━━\n$REMEDIATED"

if [ -n "$output" ]; then
  echo -e "$output\n\n━━━\nNext check: 47th minute of every 2nd hour"
  exit 1
fi
exit 0
