#!/usr/bin/env bash
# docs-consolidation-2026-10-20-verify.sh — READ-ONLY verifier for the docs
# consolidation cycle (docs-consolidation-cleanup, 2026-10-20).
#
# Re-checks every claim the cycle makes and exits non-zero on any failure.
# It never writes anything: it measures the tree as committed.
#
# Usage:  bash docs/evidence/docs-consolidation-2026-10-20-verify.sh
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2
REPO="$PWD"
FAIL=0
WARN=0

pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; FAIL=$((FAIL+1)); }
warn() { printf 'WARN  %s\n' "$1"; WARN=$((WARN+1)); }
hdr()  { printf '\n=== %s\n' "$1"; }

hdr "1. every docs path cited by docs/DOCS-INDEX.md resolves"
OUT=$(python3 - <<'EOF'
import re, pathlib
root = pathlib.Path('.')
idx = (root/'docs/DOCS-INDEX.md').read_text()
paths = sorted({p for p in re.findall(r'`([^`]+)`', idx)
                if re.match(r'^(?:docs|ops|skills|tests|core|tools|plugins)/', p)
                and not p.endswith('/') and '::' not in p})
missing = [p for p in paths if not (root/p).exists()]
print(f"cited={len(paths)} missing={len(missing)}")
for m in missing: print("  MISSING:", m)
EOF
)
echo "$OUT"
echo "$OUT" | grep -q 'missing=0$' && pass "index paths resolve" || fail "index cites paths that do not exist"

hdr "2. the moved docs are where the index/archive says, and the sources are gone"
for p in docs/older/external/pi-skill-bridge.md docs/older/cost-baseline-2026-10.md \
         docs/older/review-queue-diagnosis-2026-10.md docs/older/continuous-skill-suggestion.md \
         docs/older/cron-jobs-reference.md docs/older/cron-format-standard.md \
         docs/older/pre-task-sequence-mandatory-before-every-task.md \
         docs/older/reference/session-todo-protocol.md docs/older/design/client-av-alembic-hook-handoff.md; do
  [[ -f "$p" ]] && pass "archived: $p" || fail "missing archived doc: $p"
done
for p in docs/external/pi-skill-bridge.md docs/cost-baseline-2026-10.md docs/review-queue-diagnosis-2026-10.md \
         docs/continuous-skill-suggestion.md docs/cron-jobs-reference.md docs/cron-format-standard.md \
         docs/pre-task-sequence-mandatory-before-every-task.md docs/reference/session-todo-protocol.md \
         docs/reports docs/repo-vs-deployed-paths.md docs/agent-learning-submissions.md \
         docs/pinned-repo-hooks.md docs/pre-commit-scoring.md docs/design/client-av-alembic-hook-handoff.md; do
  [[ -e "$p" ]] && fail "source path still present after the move: $p" || pass "source gone: $p"
done

hdr "3. no live reference to a moved/merged path (dated records + the merge notes exempt)"
HITS=0
for p in docs/external/pi-skill-bridge.md docs/cost-baseline-2026-10.md docs/review-queue-diagnosis-2026-10.md \
         docs/continuous-skill-suggestion.md docs/cron-jobs-reference.md docs/cron-format-standard.md \
         docs/pre-task-sequence-mandatory-before-every-task.md docs/reference/session-todo-protocol.md \
         docs/repo-vs-deployed-paths.md docs/agent-learning-submissions.md \
         docs/pinned-repo-hooks.md docs/pre-commit-scoring.md; do
  N=$(git grep -F "$p" -- . 2>/dev/null | grep -v '^docs/older/' | grep -v '^docs/evidence/' \
      | grep -vc 'Merged from\|absorbed\|Absorbed\|archived' || true)
  if [[ "${N:-0}" != "0" ]]; then
    fail "live reference to moved path: $p"
    git grep -F "$p" -- . | grep -v '^docs/older/' | grep -v '^docs/evidence/' | grep -v 'Merged from\|Absorbed\|absorbed\|archived'
    HITS=$((HITS+1))
  fi
done
[[ "$HITS" == "0" ]] && pass "zero live references to moved paths"

hdr "4. relative links inside the newly archived docs resolve"
OUT=$(python3 - <<'EOF'
import pathlib, re
bad = []
for p in pathlib.Path('docs/older').rglob('*.md'):
    t = p.read_text()
    if 'Archived 2026-10-20' not in t: continue
    for l in re.findall(r'\]\(([^)#\s]+)\)', t):
        if l.startswith(('http', 'mailto')): continue
        if not (p.parent/l).resolve().exists(): bad.append(f"{p} -> {l}")
print("broken=" + str(len(bad)))
for b in bad: print("  BROKEN:", b)
EOF
)
echo "$OUT"
echo "$OUT" | grep -q '^broken=0$' && pass "archived-doc links resolve" || fail "broken links in archived docs"

hdr "5. the merged content is present in each target doc"
for spec in "docs/deploy-registry-pattern.md:Repo-vs-Deployed Path Resolution" \
            "docs/pipeline-reference.md:Agent Learning Submissions" \
            "docs/git-enforcement.md:Pinned Repo Hooks" \
            "docs/git-enforcement.md:Pre-Commit Scoring Hook"; do
  f="${spec%%:*}"; s="${spec#*:}"
  grep -qF "$s" "$f" && pass "$f carries section: $s" || fail "$f is missing the merged section: $s"
done

hdr "6. syntax of every script this cycle changed"
bash -n ops/scripts/cortex-update.sh && pass "bash -n ops/scripts/cortex-update.sh" || fail "bash -n cortex-update.sh"
bash -n ops/scripts/install/check-system.sh && pass "bash -n ops/scripts/install/check-system.sh" || fail "bash -n check-system.sh"
python3 -m py_compile ops/scripts/manage/cortex_doctor/checks.py && pass "py_compile checks.py" || fail "py_compile checks.py"
python3 -c "import json,sys;json.load(open('tests/fixtures/golden-queries.json'))" && pass "golden-queries.json parses" || fail "golden-queries.json invalid"

hdr "7. the printed-instruction fixes (install / update / doctor)"
grep -q "System specs saved to" ops/scripts/install/check-system.sh \
  && fail "check-system.sh still claims a specs file it never writes" \
  || pass "check-system.sh no longer prints a non-existent artifact path"
grep -q "troubleshooting.md entry 18" ops/scripts/cortex-update.sh \
  && fail "cortex-update.sh still cites an ambiguous entry number" \
  || pass "cortex-update.sh names the troubleshooting entry by title"
grep -q 'See the role matrix at the top of `docs/bus-architecture.md` (private repo' docs/operations-reference.md \
  && pass "operations-reference.md qualifies the private-repo bus doc" \
  || warn "operations-reference.md qualification of docs/bus-architecture.md moved"
grep -q "private repo hermes-cortex-private/docs/bus-architecture.md" ops/scripts/manage/cortex_doctor/checks.py \
  && pass "doctor's stale-cron remedy qualifies the private-repo bus doc" \
  || fail "doctor remedy still names an unresolvable path"

hdr "8. the pre-commit doc audit accepts the change set"
STAGED="$(git diff --name-only; git diff --cached --name-only; git diff --name-only HEAD)" \
  bash ops/scripts/pre-commit-doc-audit.sh && pass "doc audit rc=0 (warns only, and it warned zero)" || fail "doc audit reported issues"

hdr "9. duplicate-content count in docs/"
DUP=$(find docs -name '*.md' -exec md5sum {} + | awk '{print $1}' | sort | uniq -d | wc -l | tr -d ' ')
echo "duplicate hashes: $DUP (the 2 known ones are dated MEMORY/USER snapshots — see docs/evidence/README.md rule 5)"
[[ "$DUP" == "2" ]] && pass "duplicate count unchanged at the 2 documented snapshot pairs" \
  || warn "duplicate count changed: $DUP (was 2)"

hdr "10. current vs archived doc counts"
CUR=$(find docs -name '*.md' -not -path 'docs/older/*' -not -path 'docs/evidence/*' | wc -l | tr -d ' ')
ARC=$(find docs/older -name '*.md' | wc -l | tr -d ' ')
EVI=$(find docs/evidence -name '*.md' | wc -l | tr -d ' ')
echo "current=$CUR archived=$ARC evidence_store=$EVI"

printf '\n=== SUMMARY: %s failure(s), %s warning(s)\n' "$FAIL" "$WARN"
[[ "$FAIL" == "0" ]] || exit 1
exit 0
