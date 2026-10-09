#!/usr/bin/env bash
# Agent Bus poll — inbox_titus
# Reads credentials from hermes-inbox.conf; never embeds secrets.
# Usage: ./poll-bus-inbox_titus.sh
# Fails (non-zero exit) on any connection error or non-2xx HTTP response.
set -euo pipefail
CONF="${HC_INBOX_CONF:-$HOME/.hermes-cortex/hermes-inbox.conf}"
[ -r "$CONF" ] || { echo "ERROR: cannot read $CONF" >&2; exit 1; }
URL="$(awk -F= '/^CORTEX_BUS_URL=/{print $2}' "$CONF")"
AUTH="$(awk -F= '/^CORTEX_BASIC_AUTH=/{print $2}' "$CONF")"
[ -n "$URL" ] && [ -n "$AUTH" ] || { echo "ERROR: URL/AUTH missing from $CONF" >&2; exit 1; }
echo "== GET $URL/api/pgmq/peek/inbox_titus =="
# -sS: show curl errors; --fail-with-body: non-2xx gets non-zero exit.
BODY="$(curl -sS --fail-with-body -m 25 -u "$AUTH" "$URL/api/pgmq/peek/inbox_titus")"
printf '%s\n' "$BODY"
echo "== HTTP assertion =="
# Fail if the queue read did not return the expected empty-queue payload.
printf '%s' "$BODY" | grep -q '"count":0' && echo "queue_read_ok (count=0, non-2xx would have exited nonzero above)"