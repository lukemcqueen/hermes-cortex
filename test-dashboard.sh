#!/usr/bin/env bash
set -eu
P=0; F=0
pass() { P=$((P+1)); echo "  ✅ $1"; }
fail() { F=$((F+1)); echo "  ❌ $1${2:+ — $2}"; }

echo "═══ 1. Server Health ═══"
PID=$(ss -tlnp | grep 8901 | grep -oP 'pid=\K\d+' || true)
if [ -n "$PID" ]; then pass "Dashboard on port 8901 (PID: $PID)"; else fail "Dashboard NOT on 8901"; fi

echo ""
echo "═══ 2. API Endpoints ═══"

# /api/bus
BUS=$(curl -sf http://localhost:8901/api/bus 2>/dev/null || true)
if [ -z "$BUS" ]; then fail "/api/bus no response"; else
  pass "/api/bus responds"
  KEYS=$(echo "$BUS" | python3 -c "import sys,json;d=json.load(sys.stdin);print(','.join(d.keys()))" 2>/dev/null || echo "FAIL")
  [ "$KEYS" = "FAIL" ] && { fail "/api/bus not JSON"; } || {
    pass "/api/bus keys: $KEYS"
    Q=$(echo "$BUS" | python3 -c "import sys,json;print(len(json.load(sys.stdin)['queues']))" 2>/dev/null || echo "0")
    [ "$Q" -gt 0 ] 2>/dev/null && pass "$Q queues" || fail "0 queues"
    for k in queues processing stuck dlq; do
      echo "$BUS" | python3 -c "import sys,json;d=json.load(sys.stdin);assert '$k' in d" 2>/dev/null && pass "bus.$k" || fail "bus.$k missing"
    done
  }
fi

# /api/agents
AGENTS=$(curl -sf http://localhost:8901/api/agents 2>/dev/null || true)
[ -n "$AGENTS" ] && pass "/api/agents responds" || fail "/api/agents no response"

# /api/all
ALL=$(curl -sf http://localhost:8901/api/all 2>/dev/null || true)
[ -z "$ALL" ] && fail "/api/all no response" || pass "/api/all responds"
for key in health langfuse bus agents crons sessions config; do
  echo "$ALL" | python3 -c "import sys,json;d=json.load(sys.stdin);assert '$key' in d" 2>/dev/null && pass "/api/all.$key" || fail "/api/all.$key missing"
done

echo ""
echo "═══ 3. HTML Pages ═══"

HTML=$(curl -sf http://localhost:8901/ 2>/dev/null || echo "")
[ -z "$HTML" ] && { fail "Main page: empty"; HTML=" "; }

for id in view-dashboard view-bus view-langfuse bus-content-single nav-timestamp; do
  echo "$HTML" | grep -qF "id=\"$id\"" && pass "#$id" || fail "#$id missing"
done
echo "$HTML" | grep -qF 'id="nav-dash"' && pass "nav-dash id exists" || fail "nav-dash missing"
echo "$HTML" | grep -qF 'id="nav-bus"' && pass "nav-bus id exists" || fail "nav-bus missing"
echo "$HTML" | grep -qF 'id="nav-langfuse"' && pass "nav-langfuse id exists" || fail "nav-langfuse missing"
INLINE_EVENTS=$(echo "$HTML" | grep -cP ' onclick=' 2>/dev/null || true)
[ "$INLINE_EVENTS" -eq 0 ] && pass "0 onclick attributes (CSP safe)" || fail "$INLINE_EVENTS onclick attributes"
echo "$HTML" | grep -qF 'src="/dashboard.js"' && pass "dashboard.js" || fail "dashboard.js missing"
for cid in lf-metrics lf-cost lf-traces lf-sessions lf-scores; do
  echo "$HTML" | grep -qF "id=\"$cid\"" && pass "Langfuse #$cid" || fail "Langfuse #$cid missing"
done

# /bus standalone
BHTML=$(curl -sf http://localhost:8901/bus 2>/dev/null || true)
[ -z "$BHTML" ] && fail "/bus: no response" || {
  echo "$BHTML" | grep -qF 'src="/bus.js"' && pass "/bus: external bus.js" || fail "/bus: missing bus.js"
  INLINE=$(grep -cP '<script>(?!\s*src)' ~/.hermes-cortex/dashboard/static/bus.html 2>/dev/null || true)
  [ "$INLINE" -eq 0 ] 2>/dev/null && pass "/bus: 0 inline scripts" || fail "/bus: $INLINE inline scripts"
}

# /langfuse standalone
LHTML=$(curl -sf http://localhost:8901/langfuse 2>/dev/null || true)
[ -z "$LHTML" ] && fail "/langfuse: no response" || {
  echo "$LHTML" | grep -qF 'src="/langfuse.js"' && pass "/langfuse: external langfuse.js" || fail "/langfuse: missing langfuse.js"
  INLINE=$(grep -cP '<script>(?!\s*src)' ~/.hermes-cortex/dashboard/static/langfuse.html 2>/dev/null || true)
  [ "$INLINE" -eq 0 ] 2>/dev/null && pass "/langfuse: 0 inline scripts" || fail "/langfuse: $INLINE inline scripts"
}

echo ""
echo "═══ 4. CSS Classes ═══"
for cls in grid-2 grid-3 metric-grid metric-card trace-item session-item score-item bar-chart proc-row nav-tab bar-fill bar-col; do
  echo "$HTML" | grep -qF "$cls" && pass ".$cls" || fail ".$cls missing"
done
echo "$HTML" | grep -qF '@media (max-width:800px)' && pass "Responsive 800px" || fail "Responsive 800px missing"
echo "$HTML" | grep -qF '@media (max-width: 640px)' && pass "Responsive 640px" || fail "Responsive 640px missing"

echo ""
echo "═══ 5. JS Structure ═══"
JS=$(cat ~/.hermes-cortex/dashboard/static/dashboard.js 2>/dev/null || echo "")
[ -z "$JS" ] && { fail "dashboard.js not found"; JS=" "; }
for fn in switchView renderBusView renderLangfuseView prefetchBus formatCost; do
  echo "$JS" | grep -qF "function $fn" && pass "function $fn()" || fail "function $fn() missing"
done
for var in 'let busData = null' 'let allData = null' currentView; do
  echo "$JS" | grep -qF "$var" && pass "JS var: $var" || fail "JS var: $var missing"
done
echo "$JS" | grep -qF "fetch('/api/bus').then" && pass "Bus refresh on click" || fail "Bus refresh on click missing"
echo "$JS" | grep -qF "Connection error" && pass "Error state" || fail "Error state missing"
echo "$JS" | grep -qF "All queues idle" && pass "Empty bus state" || fail "Empty bus state missing"
# Regression: bus fetch must fire REGARDLESS of cache state (not guarded by && busData)
echo "$JS" | grep -qF "if (view === 'bus')" && pass "Bus tab: unconditional fetch (not guarded by cache)" || fail "Bus tab: missing unconditional branch"
echo "$JS" | grep -qF "if (view === 'langfuse')" && pass "Langfuse tab: unconditional fetch" || fail "Langfuse tab: missing unconditional branch"

echo ""
echo "═══ 6. DOM ID Cross-Reference ═══"
# Extract getElementById IDs from JS that reference DOM elements
MISSING=""
while IFS= read -r id; do
  [ -z "$id" ] && continue
  if ! echo "$HTML" | grep -qF "id=\"$id\""; then
    MISSING="$MISSING $id"
  fi
done < <(echo "$JS" | grep -oP "\$\(['\"](\w+)['\"]\)" | sed "s/^..//;s/..$//" | sort -u)
[ -z "$MISSING" ] && pass "All DOM IDs match" || fail "DOM IDs missing from HTML:$MISSING"

echo ""
echo "═══ 8. Gap Coverage (Runtime / Edge Cases) ═══"

# HTTP status codes
echo "   HTTP status codes..."
for p in / /bus /langfuse /api/bus /api/healthy; do
  CODE=$(curl -so /dev/null -m 3 -w '%{http_code}' http://localhost:8901$p 2>/dev/null || echo "FAIL")
  [ "$CODE" = "200" ] && pass "$p → 200" || fail "$p → $CODE"
done

# JS syntax check
node --check ~/.hermes-cortex/dashboard/static/dashboard.js 2>/dev/null && pass "dashboard.js syntax valid" || fail "dashboard.js syntax INVALID"

# CSP header allows our resources
CSP=$(curl -skI -m 5 https://bus.example.org:13001/ 2>/dev/null | grep -i "content-security-policy" || echo "")
[ -n "$CSP" ] && pass "CSP header present" || fail "CSP header missing"

# Bus tab has error state in catch block
echo "$JS" | grep -qF "Connection error" && pass "Bus tab: error state in catch" || fail "Bus tab: missing error state"

# Bus tab has periodic refresh  
echo "$JS" | grep -qF "currentView === 'bus'" && pass "Bus tab: periodic refresh" || fail "Bus tab: missing periodic refresh"

# All inline scripts and event handlers removed from HTML
echo "$HTML" | grep -cP ' onclick=' 2>/dev/null && INLINE_EVENTS=$(echo "$HTML" | grep -cP ' onclick=' 2>/dev/null || echo 0) || INLINE_EVENTS=0
[ "$INLINE_EVENTS" -eq 0 ] && pass "Zero onclick attributes" || fail "$INLINE_EVENTS onclick attributes"
echo "$HTML" | grep -cP '<script>(?!\s*src)' 2>/dev/null && INLINE_SCRIPTS=$(echo "$HTML" | grep -cP '<script>(?!\s*src)' 2>/dev/null || echo 0) || INLINE_SCRIPTS=0
[ "$INLINE_SCRIPTS" -eq 0 ] && pass "Zero inline scripts in main page" || fail "$INLINE_SCRIPTS inline scripts"
[ -f ~/.hermes-cortex/dashboard/static/bus.js ] && pass "bus.js exists" || fail "bus.js missing"
[ -f ~/.hermes-cortex/dashboard/static/langfuse.js ] && pass "langfuse.js exists" || fail "langfuse.js missing"
BS=$(wc -c < ~/.hermes-cortex/dashboard/static/bus.js 2>/dev/null || echo 0)
LS=$(wc -c < ~/.hermes-cortex/dashboard/static/langfuse.js 2>/dev/null || echo 0)
[ "$BS" -gt 1000 ] && pass "bus.js $BS bytes" || fail "bus.js $BS bytes"
[ "$LS" -gt 1000 ] && pass "langfuse.js $LS bytes" || fail "langfuse.js $LS bytes"

echo ""
echo "═══════════════════════════════════════"
echo "  $P passed, $F failed"
echo "═══════════════════════════════════════"
exit $F
