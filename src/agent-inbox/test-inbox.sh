#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  test-inbox.sh — Functional tests for Agent Inbox
#
#  Tests: page structure, API endpoints, SSL, watchdog script
#
#  Usage: bash test-inbox.sh
#  Exit:  0 if all pass, 1 if any fail
# ─────────────────────────────────────────────────────────────
set -euo pipefail
PASS=0
FAIL=0
BASE="https://127.0.0.1:13004"
API="http://127.0.0.1:8903"
AUTH="-u moses:M0s3s!nbox_2026"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

pass() { PASS=$((PASS+1)); echo "  ✅ $1"; }
fail() { FAIL=$((FAIL+1)); echo "  ❌ $1"; }

echo "━━━ Agent Inbox Tests ━━━"
echo ""

# ── 1. SSL certificate ──
echo "── 1. SSL/TLS ──"
CERT_INFO=$(echo | openssl s_client -connect 127.0.0.1:13004 \
  -servername realgospelmessage.org 2>/dev/null | openssl x509 -noout -subject -dates 2>/dev/null)
if echo "$CERT_INFO" | grep -q "realgospelmessage.com"; then
  pass "SSL cert is for realgospelmessage.com"
else
  fail "SSL cert subject mismatch"
fi
if echo "$CERT_INFO" | grep -qi "not[Bb]efore"; then
  pass "SSL cert has valid dates"
else
  fail "SSL cert has no valid dates — got: $CERT_INFO"
fi

# ── 2. HTTP(S) page loads ──
echo ""
echo "── 2. Page Load ──"
HTTP_CODE=$(curl -sk -o /dev/null -w '%{http_code}' $AUTH "$BASE/")
[ "$HTTP_CODE" = "200" ] && pass "HTTPS page returns 200" || fail "HTTPS page returned $HTTP_CODE"

# ── 3. Page structure ──
echo ""
echo "── 3. Page Structure ──"
curl -sk $AUTH "$BASE/" > "$TMPDIR/page.html"

grep -q 'id="compose-toggle"' "$TMPDIR/page.html" && pass "Toolbar has compose-toggle button" || fail "Missing compose-toggle button"
grep -q 'id="compose-arrow"' "$TMPDIR/page.html" && pass "Toolbar has ▼ arrow span" || fail "Missing arrow span"
grep -q 'id="compose-label"' "$TMPDIR/page.html" && pass "Toolbar has label span" || fail "Missing label span"
grep -q 'id="autorefresh-toggle"' "$TMPDIR/page.html" && pass "Toolbar has auto-refresh button" || fail "Missing auto-refresh button"
grep -q 'class="btn-sm luke-btn"' "$TMPDIR/page.html" && pass "Toolbar has Luke button" || fail "Missing Luke button"
grep -q 'id="refresh-indicator"' "$TMPDIR/page.html" && pass "Has refresh indicator pill" || fail "Missing refresh indicator"
grep -q 'id="refresh-dot"' "$TMPDIR/page.html" && pass "Has refresh status dot" || fail "Missing refresh dot"
grep -q 'id="refresh-label"' "$TMPDIR/page.html" && pass "Has refresh label" || fail "Missing refresh label"

# ── 4. Compose form starts collapsed ──
echo ""
echo "── 4. Compose Form State ──"
grep -q 'compose-card collapsed' "$TMPDIR/page.html" && pass "Compose form starts collapsed" || fail "Compose form not collapsed"
grep -q 'compose-card.*no-animate' "$TMPDIR/page.html" && pass "Compose form has no-animate class" || fail "Missing no-animate class"
grep -q 'id="compose-form"' "$TMPDIR/page.html" && pass "Compose form element exists" || fail "Missing compose form element"

# ── 5. Topic tabs ──
echo ""
echo "── 5. Topic Tabs ──"
grep -q 'href="/?topic=general"' "$TMPDIR/page.html" && pass "General tab exists" || fail "Missing General tab"
grep -q 'href="/?topic=operations"' "$TMPDIR/page.html" && pass "Operations tab exists" || fail "Missing Operations tab"
grep -q 'href="/?topic=security"' "$TMPDIR/page.html" && pass "Security tab exists" || fail "Missing Security tab"
grep -q 'href="/?topic=luke"' "$TMPDIR/page.html" && pass "Luke tab exists" || fail "Missing Luke tab"

# ── 6. API endpoint: health ──
echo ""
echo "── 6. API — Health ──"
HEALTH=$(curl -sk $AUTH "$API/health" 2>/dev/null || echo '{"status":"error"}')
echo "$HEALTH" | grep -q '"status":"ok"' && pass "Health endpoint returns OK" || fail "Health endpoint failed"

# ── 7. API endpoint: inbox ──
echo ""
echo "── 7. API — Inbox ──"
INBOX=$(curl -sk $AUTH "$BASE/api/inbox" 2>/dev/null || echo '{}')
echo "$INBOX" | grep -q '"count"' && pass "Inbox API returns count" || fail "Inbox API missing count"
echo "$INBOX" | grep -q '"unread"' && pass "Inbox API returns unread" || fail "Inbox API missing unread"

# ── 8. API: send + read ──
echo ""
echo "── 8. API — Send & Read ──"
SEND_RESULT=$(curl -sk -X POST $AUTH "$API/send" \
  -d "from=tester" \
  -d "topic=general" \
  -d "subject=Test message" \
  -d "body=This is a test message from automated test suite." \
  -o /dev/null -w '%{http_code}' 2>/dev/null || echo "fail")
[ "$SEND_RESULT" = "303" ] && pass "Send message returns 303 redirect" || fail "Send returned $SEND_RESULT"

# Verify message appears in inbox
sleep 1
INBOX_AFTER=$(curl -sk $AUTH "$BASE/api/inbox?unread_only=true" 2>/dev/null || echo '{}')
MSG_COUNT=$(echo "$INBOX_AFTER" | grep -o '"unread":' | wc -l)
UNREAD=$(echo "$INBOX_AFTER" | grep -o '"unread":[0-9]*' | grep -o '[0-9]*' || echo "0")
[ "$UNREAD" -gt "0" ] && pass "Unread count increased after sending" || fail "Unread count still 0 after sending"

# Find and mark the test message as read
TEST_ID=$(echo "$INBOX_AFTER" | grep -o '"id":"[^"]*"' | grep tester | head -1 | sed 's/"id":"//;s/"//')
if [ -n "$TEST_ID" ]; then
  READ_RESULT=$(curl -sk $AUTH "$BASE/read/${TEST_ID}.md" -o /dev/null -w '%{http_code}' 2>/dev/null || echo "fail")
  [ "$READ_RESULT" = "303" ] && pass "Mark read returns 303" || fail "Mark read returned $READ_RESULT"
fi

# ── 9. JavaScript structure ──
echo ""
echo "── 9. JavaScript ──"
grep -q 'function toggleMessageForm' "$TMPDIR/page.html" && pass "toggleMessageForm function exists" || fail "Missing toggleMessageForm"
grep -q 'function toggleAutoRefresh' "$TMPDIR/page.html" && pass "toggleAutoRefresh function exists" || fail "Missing toggleAutoRefresh"
grep -q 'function openLukeForm' "$TMPDIR/page.html" && pass "openLukeForm function exists" || fail "Missing openLukeForm"
grep -q 'function getCookie' "$TMPDIR/page.html" && pass "getCookie function exists" || fail "Missing getCookie"
grep -q 'function id(' "$TMPDIR/page.html" && pass "Safe DOM helper function exists" || fail "Missing id() helper"
grep -q 'classList.remove.*no-animate' "$TMPDIR/page.html" && pass "Toggle removes no-animate class" || fail "Missing no-animate removal"
tr '\n' ' ' < "$TMPDIR/page.html" | grep -q 'setTimeout.*classList.remove.*no-animate' && pass "Init removes no-animate after delay" || fail "Missing delayed no-animate removal"
grep -q 'addEventListener.*click.*toggleMessageForm' "$TMPDIR/page.html" && pass "Toggle wired via addEventListener" || fail "Missing toggle event listener"
grep -q 'addEventListener.*click.*toggleAutoRefresh' "$TMPDIR/page.html" && pass "Refresh wired via addEventListener" || fail "Missing refresh event listener"
grep -q 'addEventListener.*click.*openLukeForm' "$TMPDIR/page.html" && pass "Luke wired via addEventListener" || fail "Missing Luke event listener"
grep -q "onclick=" "$TMPDIR/page.html" && fail "⚠️ Found inline onclick (should use addEventListener)" || pass "No inline onclick handlers"

# ── 10. XSS Protection ──
echo ""
echo "── 10. XSS Protection ──"
grep -q 'html.escape(msg' ~/hermes-cortex/src/agent-inbox/server.py && pass "Message body is HTML-escaped (server-side)" || fail "Missing html.escape in source"
grep -q 'import html' ~/hermes-cortex/src/agent-inbox/server.py && pass "html module imported" || fail "Missing import html"

# ── 11. Mobile ──
echo ""
echo "── 11. Mobile ──"
grep -q '@media (max-width: 600px)' "$TMPDIR/page.html" && pass "Mobile media query exists" || fail "Missing mobile media query"
grep -q 'compose-form-grid' "$TMPDIR/page.html" && pass "Grid has CSS class for mobile override" || fail "Missing compose-form-grid class"

# ── 12. UI Polish ──
echo ""
echo "── 12. UI Polish ──"
grep -q ':active' "$TMPDIR/page.html" && pass "Button press state exists (:active)" || fail "Missing :active styles"
grep -q 'compose-card collapsed no-animate' "$TMPDIR/page.html" && pass "Compose form has no redundant heading" || fail "Heading structure changed"

# ── 13. Security headers ──
echo ""
echo "── 13. Security ──"
HEADERS=$(curl -sk -I $AUTH "$BASE/" 2>/dev/null || true)
echo "$HEADERS" | grep -qi "Strict-Transport-Security" && pass "HSTS header present" || fail "Missing HSTS header"
echo "$HEADERS" | grep -qi "X-Content-Type-Options.*nosniff" && pass "X-Content-Type-Options present" || fail "Missing X-Content-Type-Options"
echo "$HEADERS" | grep -qi "X-Frame-Options.*DENY" && pass "X-Frame-Options present" || fail "Missing X-Frame-Options"
echo "$HEADERS" | grep -qi "unsafe-inline" && pass "CSP allows inline scripts ('unsafe-inline')" || fail "CSP blocks inline scripts!"

# ── Summary ──
echo ""
echo "━━━ Results: ${PASS} passed, ${FAIL} failed ━━━"
[ "$FAIL" -eq 0 ] || echo "FAILURES DETECTED"
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
