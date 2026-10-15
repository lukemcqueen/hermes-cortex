#!/usr/bin/env bash
# verify-pi-skill-load-2026-10-15.sh — re-runnable evidence for the Pi
# skill-load fix.
#
# WHAT IT PROVES, in order, and why each part is needed:
#
#   1. PI'S OWN MECHANISM. The installed Pi package is driven through its own
#      factory: it has NO `skill_view` tool, its `read` tool's schema is
#      {path, offset, limit}, and Pi's system-prompt text tells the model to load
#      a skill by READING its file. Without this, "Pi has no skill_view" is an
#      assertion; with it, the fix's premise is executable.
#
#   2. THE WRITER. The real extension is executed through Pi's own TS loader and
#      the skill-load handler is DRIVEN: a read of a SKILL.md records evidence,
#      a read of anything else does not, and the row is keyed to the session the
#      gate queries.
#
#   3. THE GUARD DISCRIMINATES. The SAME guard is run against the PRE-FIX
#      extension (extracted from git at the revision this change starts from) and
#      MUST FAIL. A guard that has never failed on the broken revision proves
#      nothing. The extraction is ASSERTED to be pre-change (it must not mention
#      the new symbol), so a baseline that silently resolves to the fixed code
#      cannot pass quietly.
#
#   4. THE CHECKER + THE SEAM. The predicate accepts both mechanisms, the real
#      store round-trips a Pi read, and the id the writer is handed is the id the
#      gate asks with.
#
# Read-only against the fleet: every store fixture is namespaced and deleted, and
# no governance lock, cron or service is touched.
#
# Run:  bash docs/evidence/verify-pi-skill-load-2026-10-15.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_REV="${BASE_REV:-$(git -C "$REPO" log -1 --format=%H -- ops/install/harnesses/pi/extensions/cortex-context.ts)}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

fails=0
step() { printf '\n=== %s ===\n' "$1"; }
check() { if eval "$2"; then printf 'PASS  %s\n' "$1"; else printf 'FAIL  %s\n' "$1"; fails=$((fails + 1)); fi; }

echo "repo:      $REPO"
echo "base rev:  $BASE_REV  (the extension revision this change starts from)"
echo "date:      $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# ── 1. Pi's own mechanism ───────────────────────────────────────────────────
step "1. Pi's installed package: no skill_view, read loads a skill file"
PI_OUT="$WORK/pi-probe.txt"
node "$REPO/ops/install/harnesses/pi/probe-pi-skill-mechanism.mjs" > "$PI_OUT" 2>&1
PROBE_RC=$?
cat "$PI_OUT"
echo "probe rc=$PROBE_RC"
check "the probe RAN (rc 0) — a probe that could not run is not a negative result" \
  "[ $PROBE_RC -eq 0 ]"
check "Pi's read tool takes 'path' (the parameter the handler must read)" \
  "grep -q 'read parameter keys: path, offset, limit' '$PI_OUT'"
check "Pi's own prompt says the READ tool loads a skill's file" \
  "grep -q 'Use the read tool to load a skill.s file' '$PI_OUT'"
check "the installed Pi bundle mentions skill_view: false (NO such tool)" \
  "grep -q 'pi bundle mentions skill_view: false' '$PI_OUT'"

# ── 2. the writer, executed ─────────────────────────────────────────────────
step "2. The real extension records Pi's mechanism"
node "$REPO/ops/install/harnesses/pi/verify-extension.mjs" > "$WORK/ext-post.txt" 2>&1
POST_RC=$?
tail -30 "$WORK/ext-post.txt"
echo "post-fix guard rc=$POST_RC"
check "post-fix: the extension guard PASSES (rc 0)" "[ $POST_RC -eq 0 ]"
check "post-fix: a read of a SKILL.md recorded evidence" \
  "grep -q 'a read of a SKILL.md records skill-load evidence (recorded 1)' '$WORK/ext-post.txt'"
check "post-fix: it recorded the TRUE tool name 'read'" \
  "grep -q \"TRUE tool name 'read'\" '$WORK/ext-post.txt'"
check "post-fix: it was keyed to the session the gate queries" \
  "grep -q 'keyed to the session the GATE queries' '$WORK/ext-post.txt'"
check "post-fix: a non-skill read records nothing" \
  "grep -q 'a read of a NON-skill file records nothing' '$WORK/ext-post.txt'"

# ── 3. the guard discriminates: PRE-FIX must FAIL ───────────────────────────
step "3. The same guard against the PRE-FIX extension must FAIL"
PRE="$WORK/cortex-context.prefix.ts"
git -C "$REPO" show "$BASE_REV:ops/install/harnesses/pi/extensions/cortex-context.ts" > "$PRE" 2>/dev/null
check "the pre-fix revision was extracted (non-empty)" "[ -s '$PRE' ]"
check "the extracted file really IS pre-change (no session_identity)" \
  "! grep -q 'session_identity' '$PRE'"
PI_EXTENSION_UNDER_TEST="$PRE" node "$REPO/ops/install/harnesses/pi/verify-extension.mjs" \
  > "$WORK/ext-pre.txt" 2>&1
PRE_RC=$?
grep -E '^(✅|❌)' "$WORK/ext-pre.txt"
echo "pre-fix guard rc=$PRE_RC"
check "pre-fix: the guard FAILS (rc non-zero) — the defect is real and the guard sees it" \
  "[ $PRE_RC -ne 0 ]"
check "pre-fix: it fails on the load-recording case specifically" \
  "grep -q 'a read of a SKILL.md records skill-load evidence (recorded 0)' '$WORK/ext-pre.txt'"

# ── 4. the checker and the seam ─────────────────────────────────────────────
step "4. Checker: both mechanisms, the seam, and the real store round trip"
python3 "$REPO/tests/test_pi_skill_load_evidence.py" > "$WORK/checker.txt" 2>&1
CHK_RC=$?
grep -vE '^\[mcp-server\]' "$WORK/checker.txt"
echo "checker rc=$CHK_RC"
check "checker suite PASSES (rc 0)" "[ $CHK_RC -eq 0 ]"
check "checker: a Pi read is honoured by the REAL store" \
  "grep -q 'test_real_store_round_trip_accepts_a_pi_read_and_refuses_an_unrelated_read' '$WORK/checker.txt'"
check "checker: no fixture debris left behind" \
  "! grep -q 'NOT cleaned up' '$WORK/checker.txt'"

step "Summary"
echo "step groups failed: $fails"
if [ "$fails" -gt 0 ]; then
  echo "RESULT: FAILING ($fails check(s) failed)"
  exit 1
fi
echo "RESULT: ALL PASS"
