#!/usr/bin/env bash
# Re-runnable verification for the 2026-10-19 memory-pruning run (cycle #13327).
#
# The LIVE memory files (~/.hermes/memories/*.md) are per-instance and NOT
# git-tracked, so this script verifies the COMMITTED EVIDENCE SNAPSHOTS that
# live beside it in this directory — a later reviewer can re-run it from a
# clean checkout with no access to the worker's machine.
#
#   MEMORY.after-2026-10-19.md  == the final ~/.hermes/memories/MEMORY.md
#   USER.after-2026-10-19.md    == the final ~/.hermes/memories/USER.md
#   *.before-*.md               == the pre-run state (basis of the diff)
#
# When the live files ARE present (i.e. on the worker's host) the script also
# asserts the snapshots still match them, proving the copies aren't stale.
#
# This script is READ-ONLY: it never writes or repairs anything it measures.
#
# Exit 0 = all applicable assertions pass; non-zero = at least one failed.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MB="$HERE/MEMORY.before-2026-10-19.md"
MA="$HERE/MEMORY.after-2026-10-19.md"
UB="$HERE/USER.before-2026-10-19.md"
UA="$HERE/USER.after-2026-10-19.md"

fail=0
check() { # label expected actual
  if [ "$2" = "$3" ]; then echo "PASS  $1 = $3"; else echo "FAIL  $1: expected $2 got $3"; fail=1; fi
}
# entry count = number of §-separated records
ent() { awk 'BEGIN{RS="§"} END{print NR}' "$1"; }
# chars/bytes measured the same way for both sides
ch() { wc -m < "$1" | tr -d ' '; }
by() { wc -c < "$1" | tr -d ' '; }

echo "## committed snapshots exist (re-verifiable from a clean checkout)"
for f in "$MB" "$MA" "$UB" "$UA"; do
  if [ -f "$f" ]; then echo "PASS  present: $(basename "$f")"; else echo "FAIL  missing: $(basename "$f")"; fail=1; fi
done

echo "## final MEMORY.md state (under the 2,200-char memory budget)"
check "MEMORY.after chars"   "2126" "$(ch "$MA")"
check "MEMORY.after bytes"   "2160" "$(by "$MA")"
check "MEMORY.after entries" "11"   "$(ent "$MA")"

echo "## final USER.md state (under the 1,375-char profile budget)"
check "USER.after chars"   "1359" "$(ch "$UA")"
check "USER.after bytes"   "1373" "$(by "$UA")"
check "USER.after entries" "7"    "$(ent "$UA")"

echo "## NO-CHANGE claim: before == after on both files (byte-identical)"
check "MEMORY md5 before == after" "$(md5sum "$MA" | cut -d' ' -f1)" "$(md5sum "$MB" | cut -d' ' -f1)"
check "USER   md5 before == after" "$(md5sum "$UA" | cut -d' ' -f1)" "$(md5sum "$UB" | cut -d' ' -f1)"
check "MEMORY diff empty" "" "$(diff -u "$MB" "$MA" | sed -n '3,$p')"
check "USER   diff empty" "" "$(diff -u "$UB" "$UA" | sed -n '3,$p')"

mc=$(ch "$MA"); uc=$(ch "$UA")
if [ "$mc" -lt 2200 ]; then echo "PASS  MEMORY.md under 2200-char limit ($mc)"; else echo "FAIL  MEMORY.md over limit ($mc)"; fail=1; fi
if [ "$uc" -lt 1375 ]; then echo "PASS  USER.md under 1375-char limit ($uc)"; else echo "FAIL  USER.md over limit ($uc)"; fail=1; fi

echo "## snapshot vs live (only when the live files exist on this host)"
LM="$HOME/.hermes/memories/MEMORY.md"
LU="$HOME/.hermes/memories/USER.md"
if [ -f "$LM" ]; then check "live MEMORY.md == snapshot" "$(md5sum "$MA" | cut -d' ' -f1)" "$(md5sum "$LM" | cut -d' ' -f1)"; else echo "SKIP  live MEMORY.md absent (not the worker host)"; fi
if [ -f "$LU" ]; then check "live USER.md == snapshot"   "$(md5sum "$UA" | cut -d' ' -f1)" "$(md5sum "$LU" | cut -d' ' -f1)"; else echo "SKIP  live USER.md absent (not the worker host)"; fi

echo "## no-facts-dropped check (every distinctive token in BEFORE must be in AFTER)"
# These are the load-bearing facts each entry carries. Because this run made NO
# change, a LOST token here means the snapshot pair is not a true no-change pair.
for tok in \
  "cortex-update.sh" "mosesaaron" "192.168.1.24" "UPPER_CASE" "REPORTS MIRROR" \
  ":14005" "spotify_user" ".asus" "status-devices.asp" "zero-MAC" \
  "nvidia-470" "reboot=pci" "50-hdmi-1080p.conf" "macbook-linux-maintenance" \
  "deploy root" "NOPASSWD" "database is locked" \
  "steadfaste" "deepseek-v4-flash-free" "agent-interop.md" \
  "deploy-manifest.tsv" "resolve_repo_resource" "pseudonym" "reflexion-check" \
  "adversarial-review.py" "adversarial_reviews" ; do
  if grep -qF -- "$tok" "$MA"; then echo "KEEP  $tok"; else echo "LOST  $tok"; fail=1; fi
done

echo "---"
if [ "$fail" -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "CHECKS FAILED"; fi
exit "$fail"
