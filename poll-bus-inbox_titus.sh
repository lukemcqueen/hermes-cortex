#!/usr/bin/env bash
# Agent Bus poll — inbox_titus
# Reads credentials from hermes-inbox.conf; never embeds secrets.
# Usage: ./poll-bus-inbox_titus.sh
set -uo pipefail
CONF="${HC_INBOX_CONF:-$HOME/.hermes-cortex/hermes-inbox.conf}"
[ -r "$CONF" ] || { echo "ERROR: cannot read $CONF" >&2; exit 1; }
URL="$(awk -F= '/^CORTEX_BUS_URL=/{print $2}' "$CONF")"
AUTH="$(awk -F= '/^CORTEX_BASIC_AUTH=/{print $2}' "$CONF")"
[ -n "$URL" ] && [ -n "$AUTH" ] || { echo "ERROR: URL/AUTH missing from $CONF" >&2; exit 1; }
echo "== GET $URL/api/pgmq/peek/inbox_titus =="
curl -sk -m 25 -u "$AUTH" "$URL/api/pgmq/peek/inbox_titus"
echo
echo "== HTTP status inline above (curl -w suffix) =="
curl -sk -m 25 -u "$AUTH" -o /dev/null -w "HTTP:%{http_code}\n" "$URL/api/pgmq/peek/inbox_titus"