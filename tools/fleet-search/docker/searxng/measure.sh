#!/usr/bin/env bash
# Re-runnable measurement of SearXNG's memory floor ON THIS HOST.
#
# The numbers in docs/design/agent-search.md and README.md are claims about runs; this script is
# the run. For each memory cap it reports whether the container survived, what it actually used,
# whether the kernel OOM-killed it, and whether it served a PARSEABLE result — because a container
# that is "Up" with no usable response is not a working search provider, whatever its memory says.
#
# It exits NON-ZERO if any row failed to produce parseable JSON, so a broken run cannot be filed
# away as a measurement.
#
# Usage: bash tools/fleet-search/docker/searxng/measure.sh      (~5-6 min; needs docker)
set -uo pipefail
cd "$(dirname "$0")" || exit 1

IMG="searxng/searxng:latest"
NAME="srx-measure"
PORT="18899"
FULL="settings.yml"
PRUNED="$(mktemp)"
LIMITED="$(mktemp)"
FAILED_ROWS=0

# The pruned variant exists ONLY to price the pruning tradeoff: same image, three engines.
cat > "$PRUNED" <<'YAML'
use_default_settings:
  engines:
    keep_only: [duckduckgo, wikipedia, wikidata]
server:
  secret_key: "measure-only-placeholder"
  limiter: false
  public_instance: false
  image_proxy: false
search:
  formats: [html, json]
valkey:
  url: false
YAML

# The limiter ON with NO Valkey configured: this is the dependency claim under test.
cat > "$LIMITED" <<'YAML'
use_default_settings: true
server:
  secret_key: "measure-only-placeholder"
  limiter: true
  public_instance: false
  image_proxy: false
search:
  formats: [html, json]
valkey:
  url: false
YAML

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1
  rm -f "$PRUNED" "$LIMITED"
}
trap cleanup EXIT

# Wait until the instance answers with PARSEABLE JSON — not merely until it reports "Up". A fixed
# sleep records a startup race as a result: an earlier version of this script measured "no JSON
# body" for a pruned container that answered fine a few seconds later.
await_json() {  # <attempts>
  local attempts="$1" i=0
  while [ "$i" -lt "$attempts" ]; do
    if curl -s --max-time 15 "http://127.0.0.1:${PORT}/search?q=searxng&format=json" 2>/dev/null \
        | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then
      return 0
    fi
    i=$((i + 1))
    sleep 5
  done
  return 1
}

probe() {  # <cap> <settings-file> <label> [extra docker args...]
  local cap="$1" settings="$2" label="$3"
  shift 3
  # A settings path may be relative (settings.yml) or absolute (the mktemp variants). Prefixing
  # $PWD unconditionally produces a path that does not exist, which Docker silently turns into an
  # EMPTY DIRECTORY mounted over /etc/searxng/settings.yml — the container then dies with exit 127
  # and OOMKilled=false, which looks like a memory result and is not one.
  local src="$settings"
  case "$src" in /*) ;; *) src="$PWD/$src" ;; esac

  docker rm -f "$NAME" >/dev/null 2>&1
  docker run -d --name "$NAME" --memory="$cap" --memory-swap="$cap" \
    -p "127.0.0.1:${PORT}:8080" \
    -v "$src:/etc/searxng/settings.yml:ro" \
    -e GRANIAN_WORKERS=1 "$@" "$IMG" >/dev/null 2>&1

  local answered=yes warm=?
  await_json 8 || answered=no

  local status mem oom procs summary
  status=$(docker ps -a --filter "name=$NAME" --format '{{.Status}}' | sed -n 1p)
  mem=$(docker stats --no-stream --format '{{.MemUsage}}' "$NAME" 2>/dev/null | sed -n 1p)
  oom=$(docker inspect "$NAME" --format '{{.State.OOMKilled}}' 2>/dev/null)
  # The process name is `python`, not `granian`: granian is a Python package, so counting by the
  # package name reports 0 for a perfectly healthy instance. (An earlier version of this script did
  # exactly that and printed granian-procs=0 on every row.)
  procs=$(docker exec "$NAME" sh -c 'ps -eo comm | grep -ci python' 2>/dev/null || echo "?")

  if [ "$answered" = "yes" ]; then
    summary=$(curl -s --max-time 25 "http://127.0.0.1:${PORT}/search?q=searxng&format=json" 2>/dev/null \
      | python3 -c '
import json, sys
d = json.load(sys.stdin)
r = d.get("results", [])
bad = d.get("unresponsive_engines") or []
names = sorted({(b[0] if isinstance(b, list) else b) for b in bad})
print(f"{len(r)} results | {len(names)} unresponsive {names[:6]}")
' 2>/dev/null)
    # STEADY STATE, not startup. An instance can answer at 25 s and be dead at 60 s: measured on
    # 2026-10-13, a 128 MB cap served results early and then grew to 125.2 MiB and stopped
    # answering. The cold number alone would have been quoted as the footprint.
    sleep 20
    if curl -s --max-time 25 "http://127.0.0.1:${PORT}/search?q=searxng&format=json" 2>/dev/null \
        | python3 -c 'import json,sys; json.load(sys.stdin)' 2>/dev/null; then
      warm="ok"
    else
      warm="DEAD after 20s"
      FAILED_ROWS=$((FAILED_ROWS + 1))
    fi
    summary="$summary | warm: $warm"
  else
    # "Up" with no parseable response is NOT a usable provider. Mark the row and fail the script at
    # the end, so such a row cannot be quoted as evidence of anything.
    summary="UNUSABLE — no parseable JSON after 8 attempts"
    FAILED_ROWS=$((FAILED_ROWS + 1))
  fi

  printf '  %-32s cap=%-6s %-26s mem=%-18s OOMKilled=%-6s granian-procs=%-3s %s\n' \
    "$label" "$cap" "$status" "${mem:-none}" "${oom:-?}" "$procs" "$summary"
}

echo "== the sweep: how small can it run STABLY, and what does that cost in results =="
echo "  image=$IMG  GRANIAN_WORKERS=1  loopback only  no Valkey"
echo "  each row reports the cold answer and a warm answer 20 s later — a cap that only survives"
echo "  startup is not a working provider"
probe 128m "$FULL"   "full engine set"
probe 192m "$FULL"   "full engine set"
probe 256m "$FULL"   "full engine set"
probe 128m "$PRUNED" "pruned to 3 engines"

echo
echo "== is UWSGI_WORKERS inert on this image, or is that a guess? =="
echo "   setting it to 4 while GRANIAN_WORKERS stays 1: if the process count and the memory are"
echo "   unchanged from the rows above, the variable is not consulted by this image's entrypoint."
probe 192m "$FULL"   "full set + UWSGI_WORKERS=4" -e UWSGI_WORKERS=4

echo
echo "== the claim that the limiter requires Valkey: limiter=true, valkey.url=false =="
docker rm -f "$NAME" >/dev/null 2>&1
docker run -d --name "$NAME" --memory=192m -p "127.0.0.1:${PORT}:8080" \
  -v "$LIMITED:/etc/searxng/settings.yml:ro" \
  -e GRANIAN_WORKERS=1 "$IMG" >/dev/null 2>&1
await_json 8 || true
echo "  settings actually in force (limiter must appear as true):"
docker exec "$NAME" sed -n '/^server:/,/^search:/p' /etc/searxng/settings.yml 2>/dev/null | sed 's/^/    /'
echo "  and what the container says about valkey/limiter:"
docker logs "$NAME" 2>&1 | grep -iE "valkey|limiter|redis" | sed -n '1,6p' | sed 's/^/    /'

echo
if [ "$FAILED_ROWS" -gt 0 ]; then
  echo "FAILED: $FAILED_ROWS row(s) produced no parseable JSON — those rows are NOT measurements." >&2
  exit 1
fi
echo "exit: 0"
