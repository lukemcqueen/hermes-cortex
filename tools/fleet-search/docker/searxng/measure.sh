#!/usr/bin/env bash
# Re-runnable measurement of SearXNG's memory floor ON THIS HOST.
#
# The numbers in docs/design/agent-search.md and README.md are claims about runs; this script is
# the run. It starts the image under successively smaller memory caps and, for each, reports
# whether it survived, what it actually used, whether the kernel OOM-killed it, and how many
# results it returned for a real query.
#
# Usage: bash tools/fleet-search/docker/searxng/measure.sh      (~3-4 min; needs docker)
set -uo pipefail
cd "$(dirname "$0")" || exit 1

IMG="searxng/searxng:latest"
NAME="srx-measure"
PORT="18899"
FULL="settings.yml"
PRUNED="$(mktemp)"
LIMITED="$(mktemp)"

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

probe() {  # <cap> <settings-file> <label>
  local cap="$1" settings="$2" label="$3"
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
    -e GRANIAN_WORKERS=1 "$IMG" >/dev/null 2>&1

  # A freshly started instance is not a settled one: engines need a moment before a query means
  # anything, and sampling too early measures startup cost, not the steady-state footprint.
  sleep 25

  local status mem oom answer
  status=$(docker ps -a --filter "name=$NAME" --format '{{.Status}}' | sed -n 1p)
  mem=$(docker stats --no-stream --format '{{.MemUsage}}' "$NAME" 2>/dev/null | sed -n 1p)
  oom=$(docker inspect "$NAME" --format '{{.State.OOMKilled}}' 2>/dev/null)
  answer=$(curl -s --max-time 25 "http://127.0.0.1:${PORT}/search?q=searxng%20memory&format=json" 2>/dev/null)

  local summary
  summary=$(printf '%s' "$answer" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    r = d.get("results", [])
    bad = d.get("unresponsive_engines") or []
    names = sorted({(b[0] if isinstance(b, list) else b) for b in bad})
    print(f"{len(r)} results | {len(names)} unresponsive {names[:6]}")
except Exception as e:
    print(f"no JSON body ({e})")
' 2>/dev/null)

  printf '  %-22s cap=%-6s %-26s mem=%-18s OOMKilled=%-6s %s\n' \
    "$label" "$cap" "$status" "${mem:-none}" "${oom:-?}" "$summary"
}

echo "== the sweep: how small can it run, and what does that cost in results =="
echo "  image=$IMG  GRANIAN_WORKERS=1  loopback only  no Valkey"
probe 96m  "$FULL"   "full engine set"
probe 128m "$FULL"   "full engine set"
probe 64m  "$FULL"   "full engine set"
probe 84m  "$PRUNED" "pruned to 3 engines"
probe 96m  "$PRUNED" "pruned to 3 engines"

echo
echo "== the claim that the limiter requires Valkey: limiter=true, valkey.url=false =="
docker rm -f "$NAME" >/dev/null 2>&1
docker run -d --name "$NAME" --memory=192m -p "127.0.0.1:${PORT}:8080" \
  -v "$LIMITED:/etc/searxng/settings.yml:ro" \
  -e GRANIAN_WORKERS=1 "$IMG" >/dev/null 2>&1
sleep 25
echo "  settings actually in force (limiter must appear as true):"
docker exec "$NAME" sed -n '/^server:/,/^search:/p' /etc/searxng/settings.yml 2>/dev/null | sed 's/^/    /'
echo "  and what the container says about valkey/limiter:"
docker logs "$NAME" 2>&1 | grep -iE "valkey|limiter|redis" | sed -n '1,6p' | sed 's/^/    /'
echo "  (if the settings show limiter: true and NO valkey error appears, the limiter runs without it)"

echo
echo "exit: 0"
