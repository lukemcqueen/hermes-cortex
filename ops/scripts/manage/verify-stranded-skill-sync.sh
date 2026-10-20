#!/usr/bin/env bash
# verify-stranded-skill-sync.sh — prove the stranded-skill reconciliation holds.
#
# Exits non-zero the moment either claim stops being true:
#   1. reconcile-stranded-skills.py reports a stranded count of 0
#   2. each reconciled skill is byte-identical between repo source and deployed copy
#
# A check that swallows a tool error is not a check (SOUL P12), so every
# dependency is guarded explicitly and a COULD NOT VERIFY outcome is FAIL.
set -uo pipefail

REPO="${REPO:-$HOME/hermes-cortex}"
SKILLS="${SKILLS:-devops/governance-closeout/SKILL.md devops/shell-scripting/SKILL.md}"
DEPLOYED_ROOT="${DEPLOYED_ROOT:-$HOME/.hermes/skills}"

fail=0
note() { printf '%s\n' "$*"; }

# ---- claim 1: the detector's own stranded COUNT is 0 (not its verdict line)
note "── claim 1: stranded count"
if [ ! -f "$REPO/ops/scripts/manage/reconcile-stranded-skills.py" ]; then
  note "COULD NOT VERIFY: reconciler missing at $REPO/ops/scripts/manage/"
  exit 2
fi
out="$(cd "$REPO" && python3 ops/scripts/manage/reconcile-stranded-skills.py 2>&1)"
rc=$?
if [ $rc -ne 0 ]; then
  note "COULD NOT VERIFY: reconciler exited rc=$rc"
  printf '%s\n' "$out" | sed -n '1,10p'
  exit 2
fi
count="$(printf '%s\n' "$out" | grep -o 'stranded: [0-9]\+' | head -1 | grep -o '[0-9]\+')"
if [ -z "$count" ]; then
  note "COULD NOT VERIFY: no 'stranded: N' line in reconciler output"
  exit 2
fi
if [ "$count" != "0" ]; then
  note "FAIL: stranded=$count (expected 0)"
  fail=1
else
  note "PASS: stranded=0"
fi

# ---- claim 2: repo and deployed copies are byte-identical, per skill
note "── claim 2: repo <-> deployed parity"
for rel in $SKILLS; do
  r="$REPO/skills/$rel"
  d="$DEPLOYED_ROOT/$rel"
  if [ ! -f "$r" ]; then note "FAIL: repo file missing: $r"; fail=1; continue; fi
  if [ ! -f "$d" ]; then note "FAIL: deployed file missing: $d"; fail=1; continue; fi
  rm="$(md5sum "$r" | awk '{print $1}')"
  dm="$(md5sum "$d" | awk '{print $1}')"
  if [ "$rm" = "$dm" ]; then
    note "PASS: $rel ($rm)"
  else
    note "FAIL: $rel differs — repo=$rm deployed=$dm"
    fail=1
  fi
  # fence balance: an odd count means the body is structurally broken
  f="$(grep -c '^```' "$r")"
  if [ $((f % 2)) -ne 0 ]; then note "FAIL: $rel has ODD fence count ($f)"; fail=1
  else note "PASS: $rel fences even ($f)"; fi
done

note "── result"
if [ $fail -eq 0 ]; then note "ALL PASS"; exit 0; fi
note "FAILURES PRESENT"; exit 1
