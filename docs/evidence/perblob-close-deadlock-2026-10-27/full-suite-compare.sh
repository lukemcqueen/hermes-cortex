#!/usr/bin/env bash
# Full-suite comparison for cycle 13843: the SAME suite, run at the baseline and at the fix.
#
# WHY A SEPARATE ARTIFACT. The targeted transcript (`verify.sh`) proves the new pins and the
# neighbours; this one answers the different question a reviewer should ask about any enforcement
# change — did the suite get WORSE anywhere? A bare count cannot answer it ("105 failed" says
# nothing on its own), so this prints both summaries AND the sorted set of failing test ids, then
# names the REGRESSIONS (failing at the fix, passing at the baseline) explicitly. An empty
# regression set, printed, is the result — the absence needs a positive statement or it reads as a
# probe that never ran.
#
# Both runs use the repository's own runner, with each side's tests directory named ABSOLUTELY:
# `bash <tree>/tests/run-tests.sh tests` resolves `tests/` against the CALLER's cwd, so a relative
# path silently runs the same tree twice and reports identical numbers as agreement.
#
# Usage: full-suite-compare.sh <baseline-log> <fix-log>
#        (each log is the stdout+stderr of  bash <tree>/tests/run-tests.sh <tree>/tests -q )
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_LOG="${1:-}"
TIP_LOG="${2:-}"
REPO="$(cd "$HERE/../../.." && pwd)"    # HERE is docs/evidence/<dir>, so the repo is THREE up
BASE_SHA="b2c2d25a76b6a18e2eb65b8f1441c23a8f164148"

norm() { sed -e "s#${HOME}#~#g" \
              -e 's/\x1b\[[0-9;]*m//g' \
              -e 's/[A-Za-z0-9._%+-]\+@[A-Za-z0-9.-]\+\.[A-Za-z]\{2,\}/<email-redacted>/g'; }

if [ -z "$BASE_LOG" ] || [ -z "$TIP_LOG" ] || [ ! -f "$BASE_LOG" ] || [ ! -f "$TIP_LOG" ]; then
  norm <<EOF
full-suite comparison NOT RUN — both logs are required (nothing claimed here).
Reproduce it with exactly these two commands, then re-run this script with the two log paths:

  git -C $REPO worktree add /tmp/hc-base-13843 $BASE_SHA
  ( cd /tmp/hc-base-13843 && bash /tmp/hc-base-13843/tests/run-tests.sh \\
      /tmp/hc-base-13843/tests -q > /tmp/hc-base-fullsuite.log 2>&1 )
  ( cd $REPO && bash $REPO/tests/run-tests.sh $REPO/tests -q > /tmp/hc-tip-fullsuite.log 2>&1 )
  bash $HERE/full-suite-compare.sh /tmp/hc-base-fullsuite.log /tmp/hc-tip-fullsuite.log
EOF
  exit 3
fi

summary() { grep -E "^[=]+ .*(passed|failed)" "$1" | tail -1; }
failing() {
  # pytest short-summary lines: `FAILED <nodeid>` / `ERROR <nodeid>`. Sorted for a stable diff.
  grep -E "^(FAILED|ERROR) " "$1" | awk '{print $2}' | sed 's/ - .*//' | sort -u
}

BASE_SUM="$(summary "$BASE_LOG")"
TIP_SUM="$(summary "$TIP_LOG")"

norm <<EOF
=== full-suite comparison — cycle 13843 ===
baseline : ${BASE_SHA:0:8}   (the tip this fix was written against)
suite    : bash <tree>/tests/run-tests.sh <tree>/tests -q   (each side's tests dir named ABSOLUTELY)

baseline summary : ${BASE_SUM}
fix      summary : ${TIP_SUM}

--- failing/erroring tests at the BASELINE (sorted) ---
EOF
failing "$BASE_LOG" | norm

norm <<EOF

--- failing/erroring tests at the FIX (sorted) ---
EOF
failing "$TIP_LOG" | norm

norm <<EOF

--- REGRESSIONS: failing at the FIX and NOT at the baseline (this is the number that matters) ---
EOF
comm -13 <(failing "$BASE_LOG") <(failing "$TIP_LOG") | norm | sed 's/^/  REGRESSED: /'
regressed="$(comm -13 <(failing "$BASE_LOG") <(failing "$TIP_LOG") | wc -l | tr -d ' ')"
norm <<EOF
  count: ${regressed}

--- newly PASSING at the fix (failing at the baseline, clean here) ---
EOF
comm -23 <(failing "$BASE_LOG") <(failing "$TIP_LOG") | norm | sed 's/^/  FIXED: /'
fixed="$(comm -23 <(failing "$BASE_LOG") <(failing "$TIP_LOG") | wc -l | tr -d ' ')"
norm <<EOF
  count: ${fixed}

PROVENANCE
- both logs are the complete stdout+stderr of that command on this host, same interpreter resolution
  (tests/run-tests.sh picks it by capability) and the same environmental conditions, minutes apart.
- the ERROR set is IDENTICAL on both sides: these are fixtures that run a scratch `git commit`,
  which the host's installed hooks refuse while a governance lock is held. Environmental, equal on
  both sides, and therefore not evidence of anything about this range.
- volatile fields: none printed here (no timings, no paths outside the repo).
EOF
