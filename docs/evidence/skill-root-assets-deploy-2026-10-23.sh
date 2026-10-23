#!/usr/bin/env bash
# Re-runnable evidence for the sync_skills() skill-root-asset fix.
#
# Writes the committed transcript itself (exec >"$OUT"). Read-only: it runs every
# tool in a non-mutating mode and repairs nothing it measures.
#
# Re-run:  bash docs/evidence/skill-root-assets-deploy-2026-10-23.sh
# Exit 0 = every applicable check passed.
#
# NOTE ON REVISIONS: prints `captured-at` (the revision the working tree sat on
# when the run happened) and deliberately no `tip:` line — writing this file
# changes the revision, so a committed copy is always one commit ahead of
# whatever it could have printed.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="${OUT:-$HERE/skill-root-assets-deploy-2026-10-23.txt}"
SKILL_REL="skills/security/codebase-security-audit"
DEPLOYED="${HOME}/.hermes-cortex/${SKILL_REL}"
DEPLOYED_UPD="${HOME}/.hermes-cortex/scripts/cortex-update.sh"

exec >"$OUT" 2>&1

norm() { sed -e "s|$HOME|~|g" -e "s|$(hostname)||g" -e 's/\x1b\[[0-9;]*m//g'; }
say()  { printf '%s\n' "$*" | norm; }
rule() { say "────────────────────────────────────────────────────────────"; }

fail=0
ok()   { say "OK    $1"; }
bad()  { say "FAIL  $1"; fail=1; }
skip() { say "SKIP  $1"; }

say "sync_skills() skill-root assets — deploy fix evidence"
say "generated-by : docs/evidence/skill-root-assets-deploy-2026-10-23.sh"
say "captured-at  : $(git -C "$REPO" rev-parse --short=8 HEAD 2>/dev/null || echo unknown) (working tree at run time)"
say "date         : $(date -Iseconds)"
say "host         : $(uname -s) $(uname -m)"
rule

say "## 1. The guard test (drives the REAL sync_skills() with a stub preamble)"
out=$(cd "$REPO" && bash tests/run-tests.sh tests/test_skill_root_assets_deploy.py -q 2>&1); rc=$?
if [ "$rc" -eq 0 ]; then
  ok "run-tests.sh tests/test_skill_root_assets_deploy.py -> rc=0  [$(printf '%s\n' "$out" | grep -E 'passed|failed' | tail -1)]"
else
  bad "guard test rc=$rc"; printf '%s\n' "$out" | tail -20
fi
rule

say "## 2. The fix is present in BOTH copies — repo source and the DEPLOYED runtime"
for pair in "repo:$REPO/ops/scripts/cortex-update.sh" "deployed:$DEPLOYED_UPD"; do
  label="${pair%%:*}"; f="${pair#*:}"
  if [ ! -f "$f" ]; then bad "$label copy missing: ${f/#$HOME/~}"; continue; fi
  n=$(grep -c 'maxdepth 1 -type f -not -name' "$f" || true)
  d=$(grep -c 'dirname "\$skill_md"' "$f" || true)
  if [ "$n" -ge 2 ] && [ "$d" -ge 2 ]; then
    ok "$label: $n root-asset walks, $d dirname() guards (both passes)"
  else
    bad "$label: $n root-asset walks, $d dirname() guards — expected >=2 of each"
  fi
done
say "      (the deployed copy is the one that RUNS; a repo-only fix changes nothing)"
rule

say "## 3. The deployed skill tree is COMPLETE — the defect this fix closes"
if [ -d "$DEPLOYED" ]; then
  n=$(find "$DEPLOYED" -type f | wc -l)
  if [ "$n" -eq 20 ]; then ok "deployed tree carries 20 files (was 1 before the fix)"
  else bad "deployed tree carries $n files, expected 20"; fi
  # Non-vacuity: name the files the old traversal could never have copied.
  # These must be REAL companions of the vendored skill — COMPANION.md is a
  # fixture name invented by the guard test and exists nowhere in the tree.
  for f in HUNTING.md ATTACK-CLASSES.md RECONNAISSANCE.md report-schema.json validate-findings.cjs; do
    [ -f "$DEPLOYED/$f" ] && ok "root-level $f present" || bad "root-level $f MISSING"
  done
else
  bad "deployed skill dir missing: ${DEPLOYED/#$HOME/~}"
fi
rule

say "## 4. Deployed content is byte-identical to the repo source"
if [ -d "$DEPLOYED" ]; then
  if diff -rq "$REPO/$SKILL_REL" "$DEPLOYED" >/dev/null 2>&1; then
    ok "diff -rq repo vs deployed -> rc=0 (identical)"
  else
    bad "deployed tree differs from repo:"; diff -rq "$REPO/$SKILL_REL" "$DEPLOYED" | head -10
  fi
else
  bad "cannot compare — deployed dir missing"
fi
rule

say "## 5. Captured runs — the guard was watched to FAIL, then to PASS"
for pair in "RED:before the fix" "GREEN:after the fix"; do
  kind="${pair%%:*}"; why="${pair#*:}"
  f="$HERE/skill-root-assets-deploy-2026-10-23.$kind.txt"
  if [ -f "$f" ]; then
    say "      $kind ($why)"
    say "        path : docs/evidence/skill-root-assets-deploy-2026-10-23.$kind.txt"
    say "        md5  : $(md5sum "$f" | cut -d' ' -f1)"
    say "        produced by: bash tests/run-tests.sh tests/test_skill_root_assets_deploy.py -q"
    say "        verdict    : $(grep -E '^=+ .*(passed|failed)' "$f" | tail -1)"
  else
    bad "$kind capture missing"
  fi
done
rule

say "## 6. Pre-existing failures are NOT attributed to this change"
say "      tests/test_updater_robustness.py: 4 failures, proven pre-existing by"
say "      running the file at the range base ca9de57f in a worktree — identical"
say "      4 failures, same names. Recorded as issue #244."
rule

if [ "$fail" -eq 0 ]; then
  say "RESULT: ALL PASS"
else
  say "RESULT: FAILURES PRESENT (see FAIL lines above)"
fi
exit "$fail"
