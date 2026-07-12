#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  test-inbox.sh — Functional tests for Agent Inbox
#
#  Tests: internal API endpoints (MCP backend), MCP server
#
#  The agent inbox is now MCP-only. No external API endpoint.
#  The API server runs on 127.0.0.1:8903 as MCP backend only.
#
#  Usage: bash test-inbox.sh
#  Exit:  0 if all pass, 1 if any fail
# ─────────────────────────────────────────────────────────────
set -euo pipefail
PASS=0
FAIL=0
API="http://127.0.0.1:8903"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

pass() { PASS=$((PASS+1)); echo "  ✅ $1"; }
fail() { FAIL=$((FAIL+1)); echo "  ❌ $1"; }

echo "━━━ Agent Inbox Tests (MCP Backend) ━━━"
echo ""

# ── 1. API endpoint: health ──
echo "── 1. API — Health ──"
HEALTH=$(curl -sk "$API/health" 2>/dev/null || echo '{"status":"error"}')
echo "$HEALTH" | grep -q '"status":"ok"' && pass "Health endpoint returns OK" || fail "Health endpoint failed"

# ── 2. API endpoint: inbox ──
echo ""
echo "── 2. API — Inbox ──"
INBOX=$(curl -sk "$API/api/inbox" 2>/dev/null || echo '{}')
echo "$INBOX" | grep -q '"count"' && pass "Inbox API returns count" || fail "Inbox API missing count"
echo "$INBOX" | grep -q '"unread"' && pass "Inbox API returns unread" || fail "Inbox API missing unread"

# ── 3. API: send + read ──
echo ""
echo "── 3. API — Send & Read ──"
SEND_RESULT=$(curl -sk -X POST "$API/send" \
  -d "from=tester" \
  -d "topic=general" \
  -d "subject=Test message (MCP-only test)" \
  -d "body=This is a test from the automated test suite." \
  -o /dev/null -w '%{http_code}' 2>/dev/null || echo "fail")
[ "$SEND_RESULT" = "303" ] && pass "Send message returns 303 redirect" || fail "Send returned $SEND_RESULT"

# Verify message appears in inbox
sleep 1
INBOX_AFTER=$(curl -sk "$API/api/inbox?unread_only=true" 2>/dev/null || echo '{}')
UNREAD=$(echo "$INBOX_AFTER" | grep -o '"unread":[0-9]*' | grep -o '[0-9]*' || echo "0")
[ "$UNREAD" -gt "0" ] && pass "Unread count increased after sending" || fail "Unread count still 0 after sending"

# Mark the test message as read
TEST_ID=$(echo "$INBOX_AFTER" | grep -o '"id":"[^"]*"' | grep tester | head -1 | sed 's/"id":"//;s/"//')
if [ -n "$TEST_ID" ]; then
  READ_RESULT=$(curl -sk "$API/read/${TEST_ID}.md" -o /dev/null -w '%{http_code}' 2>/dev/null || echo "fail")
  [ "$READ_RESULT" = "303" ] && pass "Mark read returns 303" || fail "Mark read returned $READ_RESULT"
fi

# ── 4. XSS Protection ──
echo ""
echo "── 4. XSS Protection ──"
grep -q 'html.escape(msg' ~/hermes-cortex/runtime/mcp-servers/agent-inbox/server.py && pass "Message body is HTML-escaped (server-side)" || fail "Missing html.escape in source"
grep -q 'import html' ~/hermes-cortex/runtime/mcp-servers/agent-inbox/server.py && pass "html module imported" || fail "Missing import html"

# ── 5. MCP server registration ──
echo ""
echo "── 5. MCP Server Registration ──"
cd ~/hermes-cortex
MCP_LIST=$(python3 -c "import json, subprocess; r=subprocess.run(['hermes','mcp','list'], capture_output=True, text=True, timeout=10); print(r.stdout)" 2>/dev/null || echo "")
echo "$MCP_LIST" | grep -q "agent-inbox" && pass "agent-inbox MCP server is registered" || fail "agent-inbox MCP server not registered"
echo "$MCP_LIST" | grep -q "enabled" && pass "agent-inbox MCP server is enabled" || fail "agent-inbox MCP server not enabled"

# ── Summary ──
echo ""
echo "━━━ Results: ${PASS} passed, ${FAIL} failed ━━━"
[ "$FAIL" -eq 0 ] || echo "FAILURES DETECTED"
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
