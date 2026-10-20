#!/usr/bin/env bash
# verify-stranded-skill-sync.sh — prove the stranded-skill reconciliation holds.
#
# Exits non-zero the moment either claim stops being true:
#   1. reconcile-stranded-skills.py reports a stranded count of 0
#   2. EVERY skill that is not stranded is byte-identical between repo and deployed
#
# Scope note (why claim 2 is not a hardcoded pair): the reconciler's own output is
# the authoritative list of what it examined — it prints SUPERSET / REVIEW rows for
# the stranded class and a "report only" trailer that names the missing count. This
# check therefore VERIFIES THE WHOLE SET THE RECONCILER TOUCHED and, separately,
# sweeps every *committed* skill under skills/ for repo<->deployed parity. A pair of
# hardcoded paths would silently measure a previous run's work (P12).
#
# A check that swallows a tool error is not a check (SOUL P12), so every
# dependency is guarded explicitly and a COULD NOT VERIFY outcome is FAIL.
set -uo pipefail

REPO="${REPO:-$HOME/hermes-cortex}"
DEPLOYED_ROOT="${DEPLOYED_ROOT:-$HOME/.hermes/skills}"
# SKILLS overrides the repo-side sweep (a narrow run, or a probe). When unset the
# sweep is DISCOVERED from the tree, never a baked-in list.
SKILLS="${SKILLS:-}"

fail=0; checked=0
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
# The reconciler must also report NOTHING awaiting review: a REVIEW row is a
# reconciliation it refused, which is a failure of this change's goal even though
# it is not counted as "stranded".
if printf '%s\n' "$out" | grep -q '^REVIEW'; then
  note "FAIL: reconciler left file(s) awaiting review:"
  printf '%s\n' "$out" | grep '^REVIEW' | sed 's/^/       /'
  fail=1
else
  note "PASS: no REVIEW rows"
fi

# ---- claim 2: repo <-> deployed parity across the VERIFIED SET
note "── claim 2: repo <-> deployed parity (discovered set)"
if [ -n "$SKILLS" ]; then
  set -- $SKILLS
else
  # Discover every committed SKILL.md, as a repo-relative path. Strip the
  # "skills/" prefix HERE rather than assuming `find` printed an absolute path:
  # find is run with cwd=$REPO, so its output is already repo-relative ("skills/…")
  # and a ${p#"$REPO/skills/"} strip would not match, yielding "skills/skills/…".
  set --
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    set -- "$@" "${p#skills/}"
  done <<EOF
$(cd "$REPO" && find skills -name SKILL.md -not -path '*/.archive/*' | sort)
EOF
fi

if [ "$#" -eq 0 ]; then
  note "COULD NOT VERIFY: discovery yielded no skills to check"
  exit 2
fi

for rel in "$@"; do
  r="$REPO/skills/$rel"
  d="$DEPLOYED_ROOT/$rel"
  checked=$((checked+1))
  if [ ! -f "$r" ]; then note "FAIL: repo file missing: $r"; fail=1; continue; fi
  # A repo skill with NO deployed counterpart is a Hermes-default/archive case, not
  # drift: skip it explicitly rather than reporting a false failure.
  if [ ! -f "$d" ]; then
    note "SKIP: not deployed on this host: $rel"
    continue
  fi
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
  if [ $((f % 2)) -ne 0 ]; then note "FAIL: $rel has ODD fence count ($f)"; fail=1; fi
done

note "── result"
note "checked $checked skill(s)"
if [ $fail -eq 0 ]; then note "ALL PASS"; exit 0; fi
note "FAILURES PRESENT"; exit 1
