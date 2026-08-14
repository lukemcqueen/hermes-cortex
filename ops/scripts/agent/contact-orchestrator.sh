#!/bin/bash
# contact-orchestrator.sh — send a message to the shared ORCHESTRATOR inbox via the bus.
# Formerly known as: contact-moses.sh (renamed 2026-08-04 — agents send to the shared
# orchestrator inbox, not to Moses specifically; see docs/bus-architecture.md).
#
# Usage: contact-orchestrator.sh "subject" "body" [priority]
#   priority: normal (default), urgent, critical
#
# FALLBACK (2026-08-05): this script now uses lib.cortex_bus (bus_send) instead of a
# hand-rolled curl. The library resolves CORTEX_BUS_URL from env or cortex-bus.conf
# and AUTOMATICALLY falls back to CORTEX_BUS_FALLBACK_URL when the primary bus is
# unreachable (per-call failover — same mechanism the rest of the fleet uses). It
# fails with a clear message only when BOTH buses are unreachable. Previously this
# script had no fallback at all: with the primary bus down it just failed, which is
# what stranded agent reports during the 2026-08-05 outage.
#
# Target queue resolution order:
#   1. CORTEX_INBOX_TARGET env var
#   2. CORTEX_INBOX_TARGET in ~/.hermes-cortex/cortex-bus.conf
#   3. Default: inbox_orchestrator (shared orchestrator inbox — seen by BOTH
#      orchestrators, Moses and Esther, so whichever is available handles it)
#
# NOTE: body should be a single line. Multi-line bodies are flattened by the
# JSON builder in lib.cortex_bus.

set -euo pipefail

# Source agent.env for AGENT_NAME when unset (else sends misattribute to OS user).
# ⚠️ MUST precede the AGENT_NAME fallback below — placing it after the CONF line
# would be dead code (AGENT_NAME is never empty by then). Titus proposal 2026-08-06.
if [ -z "${AGENT_NAME:-}" ] && [ -f "${HOME}/.hermes-cortex/agent.env" ]; then
  . "${HOME}/.hermes-cortex/agent.env"
fi
# NEVER fall back to USER/hostname — a missing identity must fail loudly
# instead of misattributing the message (Luke directive 2026-08-14).
if [ -z "${AGENT_NAME:-}" ] || [ "$AGENT_NAME" = "unknown" ]; then
  echo "❌ AGENT_NAME not configured — set AGENT_NAME= in ~/.hermes-cortex/agent.env / ~/hermes-cortex/.env or export AGENT_NAME" >&2
  exit 1
fi
SUBJECT="${1:-}"
BODY="${2:-}"
PRIORITY="${3:-normal}"

CONF="${CORTEX_BUS_CONF:-${HOME}/.hermes-cortex/cortex-bus.conf}"

_read_conf() {
  local key="$1"
  if [ -f "$CONF" ]; then
    sed -n "s/^${key}=//p" "$CONF" 2>/dev/null | head -1 | tr -d '"'
  fi
}

TARGET_QUEUE="${CORTEX_INBOX_TARGET:-}"
if [ -z "$TARGET_QUEUE" ]; then
  TARGET_QUEUE="$(_read_conf "CORTEX_INBOX_TARGET")"
fi
if [ -z "$TARGET_QUEUE" ]; then
  TARGET_QUEUE="inbox_orchestrator"
fi

if [ -z "$SUBJECT" ] || [ -z "$BODY" ]; then
  echo "Usage: contact-orchestrator.sh \"subject\" \"body\" [priority]" >&2
  echo "  priority: normal (default), urgent, critical" >&2
  exit 1
fi

# lib.cortex_bus is deployed alongside this script (~/.hermes-cortex/scripts/lib/).
LIB_DIR="${CORTEX_DEPLOY_HOME:-${HOME}/.hermes-cortex}/scripts"

echo "📤 Sending to ${TARGET_QUEUE} (primary bus, fallback automatic)..."
RESULT=$(AGENT_NAME="$AGENT_NAME" SUBJECT="$SUBJECT" BODY="$BODY" PRIORITY="$PRIORITY" \
  TARGET_QUEUE="$TARGET_QUEUE" LIB_DIR="$LIB_DIR" \
  python3 -c '
import json, os, sys
sys.path.insert(0, os.environ["LIB_DIR"])
from lib.cortex_bus import bus_send

message = {
    "from": os.environ["AGENT_NAME"],
    "to": "orchestrator",
    "subject": os.environ["SUBJECT"],
    "body": os.environ["BODY"],
    "priority": os.environ["PRIORITY"],
}
result = bus_send(os.environ["TARGET_QUEUE"], message)
# bus_send returns the API response dict on success, None when the bus (and
# its fallback) are unreachable after all retries.
print(json.dumps(result) if result else "")
' 2>&1 || true)

if [ -n "$RESULT" ] && echo "$RESULT" | grep -q '"msg_id"'; then
  MSG_ID=$(echo "$RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("msg_id","?"))' 2>/dev/null || echo "?")
  echo "✅ Delivered. Message ID: ${MSG_ID}"
else
  echo "❌ Failed: both the primary bus and its fallback are unreachable." >&2
  echo "   Message was NOT sent. Retry when a bus returns." >&2
  echo "   Config: ${CONF} (CORTEX_BUS_URL / CORTEX_BUS_FALLBACK_URL)" >&2
  [ -n "$RESULT" ] && echo "   Detail: $(echo "$RESULT" | head -c 300)" >&2
  exit 1
fi
