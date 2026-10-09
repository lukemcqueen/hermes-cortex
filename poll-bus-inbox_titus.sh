#!/usr/bin/env bash
# Agent Bus poll — inbox_titus
# Reads credentials from hermes-inbox.conf; never embeds secrets.
# Usage: ./poll-bus-inbox_titus.sh
# Correct behavior: exits 0 on ANY successful authenticated queue read (2xx),
# regardless of message count. Fails (non-zero) only on connection error or
# non-2xx. Prints the message count so callers/crons can branch on it.
set -euo pipefail
CONF="${HC_INBOX_CONF:-$HOME/.hermes-cortex/hermes-inbox.conf}"
[ -r "$CONF" ] || { echo "ERROR: cannot read $CONF" >&2; exit 1; }
# Parse key=value taking everything after the first '=' (values may contain '=').
URL="$(awk -F= '/^CORTEX_BUS_URL=/{sub(/^[^=]*=/,""); print}' "$CONF")"
AUTH="$(awk -F= '/^CORTEX_BASIC_AUTH=/{sub(/^[^=]*=/,""); print}' "$CONF")"
[ -n "$URL" ] && [ -n "$AUTH" ] || { echo "ERROR: URL/AUTH missing from $CONF" >&2; exit 1; }
echo "RUN $(date -u +'%Y-%m-%d %H:%M:%S') UTC"
echo "== GET $URL/api/pgmq/peek/inbox_titus =="
# -sS: show curl errors; --fail-with-body: non-2xx -> nonzero exit (real failure).
BODY="$(curl -sS --fail-with-body -m 25 -u "$AUTH" "$URL/api/pgmq/peek/inbox_titus")"
printf '%s\n' "$BODY"
# Assert the payload has a well-formed message-count (does NOT require it be 0).
python3 -c 'import sys,json; d=json.load(sys.stdin); assert "count" in d and isinstance(d.get("messages"), list), "unexpected payload shape"; print("queue_read_ok count=%d (any 2xx read is success)" % d["count"])' <<<"$BODY"
echo "EXIT:0"