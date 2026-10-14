#!/usr/bin/env bash
# capture.sh — REGENERATE docs/evidence/stranded-skill-cleanup/AFTER.txt
#
# Why this exists (review finding ADV-12620-1): a commit message claimed the
# parity count went "8 -> 0", but the tracked artifact's own preimage recorded
# "2 -> 0". Both numbers were real of DIFFERENT MOMENTS, and neither could be
# checked from the material:
#   * the tracked docs/evidence/skill-drift-parity.txt is REGENERATED every time
#     the checker runs WITHOUT --check, so it is a point-in-time capture that any
#     run overwrites — it recorded 2 stranded when it was last regenerated;
#   * the live reconcile run at the start of that cycle read 8, because the
#     lesson pipeline writes to DEPLOYED copies continuously and more files
#     strand between runs. That live reading left no committed trace.
#
# So this artifact cites only what git can produce, and uses the checker's
# READ-ONLY mode. The "8" is claimed nowhere here.
#
#   cd ~ && bash hermes-cortex/docs/evidence/stranded-skill-cleanup/capture.sh \
#       > hermes-cortex/docs/evidence/stranded-skill-cleanup/AFTER.txt
set -u

CLEANUP_COMMIT="5d09a6a2"   # the commit that landed the stranded content

body() {
  cd "$HOME" || exit 1
  local PY
  PY=$(command -v python3)
  local REPO="hermes-cortex"
  local EV="$REPO/docs/evidence/stranded-skill-cleanup"

  echo "STRANDED SKILL FILES — cleanup evidence (generated, not hand-written)"
  echo "Produced by: bash $EV/capture.sh   (paths normalised to ~)"
  echo "Generated at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo

  echo "═══ 1. The tracked artifact's BEFORE value, read from git (not from a run) ═══"
  echo "\$ git -C $REPO show ${CLEANUP_COMMIT}^:docs/evidence/skill-drift-parity.txt | grep -E 'stranded|in sync|Verdict'"
  git -C "$REPO" show "${CLEANUP_COMMIT}^:docs/evidence/skill-drift-parity.txt" \
    | grep -E 'stranded|in sync|Verdict'
  echo "  -> the tracked artifact recorded 2 stranded at its last regeneration. It is"
  echo "     STALE: the checker rewrites it on every run without --check, so it is a"
  echo "     point-in-time capture rather than a live count."
  echo

  echo "═══ 2. What the cleanup commit actually landed (its own file list) ═══"
  echo "\$ git -C $REPO show --name-only --format= $CLEANUP_COMMIT | grep -c 'SKILL.md'"
  git -C "$REPO" show --name-only --format= "$CLEANUP_COMMIT" | grep -c 'SKILL.md'
  echo "\$ git -C $REPO show --name-only --format= $CLEANUP_COMMIT | grep 'SKILL.md'"
  git -C "$REPO" show --name-only --format= "$CLEANUP_COMMIT" | grep 'SKILL.md'
  echo "  (--name-only, not --stat: git TRUNCATES long paths in --stat with a leading"
  echo "   '...', so a stat-based count silently under-reports and a claim read off it"
  echo "   is unsupported — which is the same class of error section 5 disclaims.)"
  echo

  echo "═══ 3. The AFTER state, from the checker's READ-ONLY mode ═══"
  echo "(--check compares against the committed artifact and WRITES NOTHING. Running"
  echo " it without --check is what rewrote the artifact mid-cycle last time.)"
  echo "\$ python3 $REPO/ops/scripts/manage/check-skill-drift-parity.py --check"
  "$PY" "$REPO/ops/scripts/manage/check-skill-drift-parity.py" --check 2>&1 | tail -10
  echo "rc=${PIPESTATUS[0]}"
  echo

  echo "═══ 4. The artifact was not rewritten by the read-only run ═══"
  echo "\$ git -C $REPO status --short -- docs/evidence/skill-drift-parity.txt"
  local st
  st=$(git -C "$REPO" status --short -- docs/evidence/skill-drift-parity.txt)
  if [[ -z "$st" ]]; then
    echo "(clean — the read-only mode left the tracked artifact untouched)"
  else
    echo "$st"
  fi
  echo

  echo "═══ 5. What this does NOT establish ═══"
  echo "- It does NOT claim 8 files were stranded. The live reconcile count at the"
  echo "  start of the cleanup cycle was 8, which is higher than the tracked"
  echo "  artifact's 2 because more files strand between runs; that reading is not"
  echo "  reproducible now the cleanup is done, so it is offered as nothing."
  echo "- The parity reading is a snapshot: the lesson pipeline keeps writing to"
  echo "  deployed copies, so files can strand again after this run. Re-run section 3."
}

body | sed "s|$HOME|~|g"
