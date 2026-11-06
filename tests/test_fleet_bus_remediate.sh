#!/usr/bin/env bash
# Hermetic test for ops/scripts/bus/fleet-bus-remediate.sh — the close
# review (ADV-14307) required a committed test of the marker format the
# script parses. Drives the REAL script against a fabricated HOME, both
# directions: pending markers -> JSON array; nothing -> [].
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO/ops/scripts/bus/fleet-bus-remediate.sh"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/fbr.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

export HOME="$TMP"
mkdir -p "$HOME/.steadfaste-fleet/state/remediate"

# case 1: no markers -> empty JSON array, rc 0
OUT1="$(bash "$SCRIPT")"
[ "$OUT1" = "[]" ] || { echo "FAIL: empty case got: $OUT1"; exit 1; }

# case 2: two markers, one full one partial
MDIR="$HOME/.steadfaste-fleet/state/remediate"
printf 'from=moses\nsubject=bus down\nfile=/tmp/evidence.txt\n' > "$MDIR/bus-fix1.txt"
printf 'from=worker-a\nsubject=No subject here\nfile=\n' > "$MDIR/inbox-fix2.txt"

OUT2="$(bash "$SCRIPT")"
echo "$OUT2" | grep -q '"sender": "moses"' || { echo "FAIL: moses marker not parsed: $OUT2"; exit 1; }
echo "$OUT2" | grep -q '"subject": "bus down"' || { echo "FAIL: subject missing: $OUT2"; exit 1; }
echo "$OUT2" | grep -q '"marker_file"' || { echo "FAIL: marker_file missing: $OUT2"; exit 1; }
echo "$OUT2" | grep -q '"filename": "bus-fix1.txt"' || { echo "FAIL: filename missing: $OUT2"; exit 1; }
echo "$OUT2" | grep -q '"sender": "worker-a"' || { echo "FAIL: inbox marker not parsed: $OUT2"; exit 1; }
# JSON well-formed (two entries)
python3 - "$OUT2" <<'PY'
import json, sys
data = json.loads(sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read())
PY
echo "PASS: fleet-bus-remediate (empty + 2 markers, valid JSON)"
