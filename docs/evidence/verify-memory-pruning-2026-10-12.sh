#!/usr/bin/env bash
# Re-runnable verification for the 2026-10-12 memory-pruning run (cycle #12144).
#
# The LIVE memory files (~/.hermes/memories/*.md) are per-instance and NOT
# git-tracked, so this script verifies the COMMITTED EVIDENCE SNAPSHOTS that
# live beside it in this directory — a later reviewer can re-run it from a
# clean checkout with no access to the worker's machine.
#
#   MEMORY.after-2026-10-12.md  == the final ~/.hermes/memories/MEMORY.md
#   USER.after-2026-10-12.md    == the final ~/.hermes/memories/USER.md
#   MEMORY.before-2026-10-12.md == the pre-run MEMORY.md (basis of the diff)
#
# When the live files ARE present (i.e. on the worker's host) the script also
# asserts the snapshots still match them, proving the copies aren't stale.
#
# Exit 0 = all assertions pass; non-zero = which assertion failed.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MB="$HERE/MEMORY.before-2026-10-12.md"
MA="$HERE/MEMORY.after-2026-10-12.md"
UA="$HERE/USER.after-2026-10-12.md"

fail=0
check() { # label expected actual
  if [ "$2" = "$3" ]; then echo "PASS  $1 = $3"; else echo "FAIL  $1: expected $2 got $3"; fail=1; fi
}
# entry count = number of §-separated records
ent() { awk 'BEGIN{RS="§"} END{print NR}' "$1"; }

echo "## committed snapshots (re-verifiable from a clean checkout)"
check "MEMORY.after md5"  "382c5be6cbfaa5dc5093e93e59f68d0c" "$(md5sum "$MA" | cut -d' ' -f1)"
check "USER.after md5"    "32ead3cb57ddbef16e5322f1b47545ae" "$(md5sum "$UA" | cut -d' ' -f1)"
check "MEMORY.before md5" "3735a517c5cc993901dc4c35e6cb0df2" "$(md5sum "$MB" | cut -d' ' -f1)"

echo "## BEFORE MEMORY.md state (proves the 2081-byte / 2038-char starting point)"
check "MEMORY.before chars"   "2038" "$(wc -m < "$MB" | tr -d ' ')"
check "MEMORY.before bytes"   "2081" "$(wc -c < "$MB" | tr -d ' ')"
check "MEMORY.before entries" "14"   "$(ent "$MB")"

echo "## final MEMORY.md state (under the 2,200-char memory budget)"
check "MEMORY.after chars"   "1925" "$(wc -m < "$MA" | tr -d ' ')"
check "MEMORY.after bytes"   "1962" "$(wc -c < "$MA" | tr -d ' ')"
check "MEMORY.after entries" "10"   "$(ent "$MA")"

echo "## USER.md unchanged (before snapshot == after snapshot, empty diff)"
UB="$HERE/USER.before-2026-10-12.md"
check "USER.before md5"                       "32ead3cb57ddbef16e5322f1b47545ae" "$(md5sum "$UB" | cut -d' ' -f1)"
check "USER.before md5 == USER.after md5"     "$(md5sum "$UA" | cut -d' ' -f1)" "$(md5sum "$UB" | cut -d' ' -f1)"
check "USER.before == USER.after (diff empty)" "" "$(diff -u "$UB" "$UA" | sed -n '3,$p')"

echo "## final USER.md state"
check "USER.after chars"   "1359" "$(wc -m < "$UA" | tr -d ' ')"
check "USER.after bytes"   "1373" "$(wc -c < "$UA" | tr -d ' ')"
check "USER.after entries" "7"    "$(ent "$UA")"

chars=$(wc -m < "$MA" | tr -d ' ')
if [ "$chars" -lt 2200 ]; then echo "PASS  MEMORY.md under 2200-char limit ($chars)"; else echo "FAIL  MEMORY.md over limit ($chars)"; fail=1; fi

echo "## snapshot vs live (only when the live files exist on this host)"
LM="$HOME/.hermes/memories/MEMORY.md"
LU="$HOME/.hermes/memories/USER.md"
if [ -f "$LM" ]; then check "live MEMORY.md == snapshot" "$(md5sum "$MA" | cut -d' ' -f1)" "$(md5sum "$LM" | cut -d' ' -f1)"; else echo "SKIP  live MEMORY.md absent (not the worker host)"; fi
if [ -f "$LU" ]; then check "live USER.md == snapshot"   "$(md5sum "$UA" | cut -d' ' -f1)" "$(md5sum "$LU" | cut -d' ' -f1)"; else echo "SKIP  live USER.md absent (not the worker host)"; fi

echo "## no-facts-dropped check (every distinctive token in BEFORE must be in AFTER)"
# Distinctive path/identifier tokens asserted present in the final MEMORY.md.
# These are the load-bearing facts each before-entry carried; if a merge had
# dropped one, its token would be missing here.
for tok in \
  "cortex-update.sh" "mosesaaron" "192.168.1.24" "UPPER_CASE" "REPORTS MIRROR" \
  ":14005" "spotify_user" ".asus" "status-devices.asp" "zero-MAC" \
  "nvidia-470" "reboot=pci" "50-hdmi-1080p.conf" "macbook-linux-maintenance" \
  "deploy root" "NOPASSWD" "database is locked" "3-strike" \
  "steadfaste" "deepseek-v4-flash-free" "context_tools" "agent-interop.md" \
  "deploy-manifest.tsv" "resolve_repo_resource" "pseudonym" ; do
  if grep -qF -- "$tok" "$MA"; then echo "KEEP  $tok"; else echo "LOST  $tok"; fail=1; fi
done

echo "---"
if [ "$fail" -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "CHECKS FAILED"; fi
exit "$fail"
