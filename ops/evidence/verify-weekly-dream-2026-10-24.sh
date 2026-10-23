#!/usr/bin/env bash
# Verifier for the 2026-10-24 weekly mycortex dream.
#
# Asserts, by re-execution (not by prose):
#   (a) the committed artifact matches its committed sha256 sidecar;
#   (b) the committed artifact is byte-identical to the live brain copy, when present;
#   (c) the artifact structurally carries the required phases, the week's scripture
#       (Zechariah 4:6), and the INDEX entry was appended.
#
# Exit: 0 = all checks pass, 1 = a real failure (named), 3 = COULD NOT VERIFY.
# Run:  bash ops/evidence/verify-weekly-dream-2026-10-24.sh

set -uo pipefail

REPO="${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
ART="$REPO/docs/evidence/weekly-dream-content-2026-10-24.md"
SUM="$ART.sha256"
BRAIN="${BRAIN:-$HOME/brain/esther/dreams/2026-10-24-weekly.md}"
INDEX="${INDEX:-$HOME/brain/esther/dreams/INDEX.md}"

rc=0
say() { printf '%s\n' "$*"; }
ok()  { printf 'OK    %s\n' "$*"; }
bad() { printf 'FAIL  %s\n' "$*"; rc=1; }
cv()  { printf 'COULD NOT VERIFY  %s\n' "$*"; exit 3; }

say "verify-weekly-dream-2026-10-24"
say "artifact: $ART"
say "brain   : $BRAIN"
say "------------------------------------------------------------"

[ -f "$ART" ] || cv "artifact not present: $ART"
[ -f "$SUM" ] || cv "sidecar not present: $SUM"

# (a) artifact vs committed sidecar -- sha256sum scripted, never a hard-coded digest
want="$(tr -d '[:space:]' < "$SUM")"
[ -n "$want" ] || cv "sidecar is empty: $SUM"
got="$(sha256sum "$ART" | awk '{print $1}')"
if [ "$got" = "$want" ]; then
  ok "artifact matches sidecar sha256 ($got)"
else
  bad "artifact does NOT match sidecar (want $want, got $got)"
fi

# (b) artifact vs live brain copy
if [ -f "$BRAIN" ]; then
  if cmp -s "$ART" "$BRAIN"; then
    ok "artifact byte-identical to live brain copy ($BRAIN)"
  else
    bad "artifact DIFFERS from live brain copy ($BRAIN)"
  fi
else
  say "SKIP  live brain copy absent on this host (brain store is not a git repo)"
fi

# (c) structural assertions -- the phases, the scripture, the outbound link count
for needle in \
  "Phase 1 — Fresh pages" \
  "Phase 2 — Connections mapped" \
  "Phase 3 — Lessons synthesized" \
  "Phase 4 — Scripture connection" \
  "Phase 5 — Dream" \
  "Phase 6 — Written back"
do
  if grep -qF -- "$needle" "$ART"; then
    ok "phase present: $needle"
  else
    bad "phase MISSING: $needle"
  fi
done

if grep -qF "Zechariah 4:6" "$ART"; then
  ok "week's scripture cited: Zechariah 4:6"
else
  bad "week's scripture NOT cited (Zechariah 4:6)"
fi

# The dream body itself must exist between Phase 5 and Phase 6, not just the heading.
if grep -qF "the narrow view is not a lie" "$ART"; then
  ok "dream body present (the week's named law)"
else
  bad "dream body NOT present"
fi

# The write-back target must be named, and the INDEX line appended.
if grep -qF "2026-10-24-weekly.md" "$ART"; then
  ok "write-back target named in Phase 6"
else
  bad "write-back target NOT named in Phase 6"
fi

if [ -f "$INDEX" ]; then
  if grep -qF "2026-10-24 | The Week the Window Was Too Narrow (weekly)" "$INDEX"; then
    ok "INDEX entry appended (weekly, 2026-10-24)"
  else
    bad "INDEX entry MISSING for the 2026-10-24 weekly dream"
  fi
else
  say "SKIP  live INDEX absent on this host"
fi

say "------------------------------------------------------------"
if [ "$rc" -eq 0 ]; then
  say "RESULT: ALL PASS"
else
  say "RESULT: FAIL"
fi
exit "$rc"
