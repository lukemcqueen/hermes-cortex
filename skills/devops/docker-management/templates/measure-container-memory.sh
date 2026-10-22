#!/usr/bin/env bash
# Measure the STEADY-STATE memory floor of a containerised service, and fail if any row is not a
# measurement. Copy beside the compose file for the service you are sizing and edit the four
# CONFIG values.
#
# Why this shape (each line was a wrong number first):
#   * waiting for "Up" measures startup; the service can answer at 25 s and be dead at 60 s
#   * a row that never produced a parseable response is NOT a data point — mark it and fail
#   * a plain `sleep` records a startup race as a finding, so poll the real endpoint instead
#   * the process name is the RUNTIME's (`python`, `node`), not the server's package name
#   * both --memory AND --memory-swap, or the container reaches for host swap and survives
set -uo pipefail
cd "$(dirname "$0")" || exit 1

# ---- CONFIG -----------------------------------------------------------------------------------
IMG="your/image:tag"
NAME="measure-me"                       # the container this script owns and cleans up
PORT=18999                              # host port to publish
SETTINGS="settings.yml"                 # relative to THIS directory, or an absolute path
PROBE="http://127.0.0.1:${PORT}/health" # any endpoint whose BODY proves the service works
CAPS=("128m" "192m" "256m" "96m" "64m")  # sweep low enough to find the kill line
# ------------------------------------------------------------------------------------------------
FAILED_ROWS=0
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1; }
trap cleanup EXIT

# Poll until the endpoint returns a body that JSON-parses. Replace the python check with whatever
# "this service is actually serving" means for your probe (an HTTP 200 on a health route that
# returns 503 while warming is NOT proof).
await_ready() {  # <attempts>
  local attempts="$1" i=0
  while [ "$i" -lt "$attempts" ]; do
    if curl -s --max-time 15 "$PROBE" 2>/dev/null \
        | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then
      return 0
    fi
    i=$((i + 1))
    sleep 5
  done
  return 1
}

probe() {  # <cap>
  local cap="$1"
  # Resolve the mount source explicitly: prefixing $PWD to an ALREADY ABSOLUTE path makes Docker
  # create an empty DIRECTORY over the target file, and the container then dies with exit 127 and
  # OOMKilled=false — a row that looks like a memory result and is not one.
  local src="$SETTINGS"
  case "$src" in /*) ;; *) src="$PWD/$src" ;; esac

  docker rm -f "$NAME" >/dev/null 2>&1
  docker run -d --name "$NAME" --memory="$cap" --memory-swap="$cap" \
    -p "127.0.0.1:${PORT}:8080" -v "$src:/app/config:ro" "$IMG" >/dev/null 2>&1

  local ready=yes
  await_ready 8 || ready=no

  local status mem oom steady
  status=$(docker ps -a --filter "name=$NAME" --format '{{.Status}}' | sed -n 1p)
  mem=$(docker stats --no-stream --format '{{.MemUsage}}' "$NAME" 2>/dev/null | sed -n 1p)
  oom=$(docker inspect "$NAME" --format '{{.State.OOMKilled}}' 2>/dev/null)

  if [ "$ready" = "yes" ]; then
    # STEADY STATE, not startup: let it serve, then ask again.
    sleep 20
    if await_ready 2; then steady="ok"; else steady="DEAD after 20s"; FAILED_ROWS=$((FAILED_ROWS + 1)); fi
  else
    steady="UNUSABLE — never answered"; FAILED_ROWS=$((FAILED_ROWS + 1))
  fi

  printf '  cap=%-6s %-26s mem=%-18s OOMKilled=%-6s warm: %s\n' \
    "$cap" "$status" "${mem:-none}" "${oom:-?}" "$steady"
}

echo "== memory floor sweep: image=$IMG =="
for cap in "${CAPS[@]}"; do probe "$cap"; done

echo
if [ "$FAILED_ROWS" -gt 0 ]; then
  echo "FAILED: $FAILED_ROWS row(s) were not measurements — see the warm: column." >&2
  exit 1
fi
# Size the real cap ABOVE the highest steady figure you observed, with headroom for growth — and
# say in the artifact which number you sized against (startup or steady state).
echo "exit: 0"
