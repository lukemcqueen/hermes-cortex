#!/usr/bin/env bash
# Re-run every claim behind the reclaim path (reclaim_dead_locks).
#
# Prints each command above its own output with the command's OWN rc (measured on the
# command, never through a pipe) and exits non-zero on any failed claim:
#
#   1. the behavioural probe against the REAL module, in a THROWAWAY state dir + DB;
#   2. the source-level contract tests (registration, one staleness rule, report-only default);
#   3. the wider governance selection, so a regression outside the new file shows up;
#   4. a LIVE report (apply=false) — what the tool sees on THIS host right now, read-only;
#   5. the other half of the discrimination: the capability is ABSENT in the pre-fix revision,
#      so it is genuinely an addition rather than an assertion about nothing.
#
# Read-only outside the scratch dir it creates. Usage:
#   bash docs/evidence/reclaim-dead-locks-verify.sh [repo-path] [pre-fix-ref]
set -uo pipefail

REPO="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PREFIX_REF="${2:-origin/main}"
cd "$REPO" || { echo "no such repo: $REPO"; exit 2; }

FAILED=0
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/reclaim-dead-locks.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT
norm() { sed -e "s|$HOME|~|g"; }

run() {
  local label="$1"; shift
  echo "--- $label"
  echo "\$ $*" | norm
  local out rc
  out="$("$@" 2>&1)"; rc=$?
  printf '%s\n' "$out" | norm
  echo "rc=$rc"
  [ "$rc" -eq 0 ] || FAILED=$((FAILED + 1))
  echo
}

echo "repo: $(pwd | norm)"
echo "pre-fix ref for the discrimination: $PREFIX_REF"
echo "NOTE: the probe runs under plain python3 on purpose — the module guards its own 'mcp'"
echo "      import, so its stdio-server warning is expected here and does not affect the checks."
echo

run "1. behavioural probe (throwaway state dir + DB) against the working copy" \
    python3 docs/evidence/reclaim-dead-locks-probe.py "$(pwd)"

run "2. source-level contract tests" \
    bash tests/run-tests.sh tests/test_reclaim_dead_locks_tool.py -q

run "3. wider governance selection" \
    bash tests/run-tests.sh tests/ -q -k "reclaim or lock or govern or cycle or mcp or closeout"

git show "$PREFIX_REF:mcp-servers/loop-gov-mcp.py" > "$SCRATCH/pre-fix.py" 2>/dev/null
echo "--- 4. LIVE report on this host (apply=false — read-only)"
echo "\$ python3 - <repo> <scratch>/pre-fix.py   # inline program below: imports the module"
echo "  from the repo under test and calls _reclaim_dead_locks({\"apply\": False}) — report"
echo "  mode mutates nothing, so running it against the live state dir is safe."
python3 - "$(pwd)" "$SCRATCH/pre-fix.py" <<'PY' 2>&1 | norm
import importlib.util
import sys
from pathlib import Path

repo = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("loopgov_live", repo / "mcp-servers/loop-gov-mcp.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
res = mod._reclaim_dead_locks({"apply": False})
text = "\n".join(getattr(c, "text", "") for c in res.content)
print(text)
PY
rc=$?; echo "rc=$rc"; [ "$rc" -eq 0 ] || FAILED=$((FAILED + 1)); echo

echo "--- 5. the other half: the capability is ABSENT in the pre-fix revision"
if grep -q "def _reclaim_dead_locks(" "$SCRATCH/pre-fix.py"; then
  echo "FAIL  the pre-fix revision already carries the tool — not an addition"
  FAILED=$((FAILED + 1))
else
  echo "PASS  def _reclaim_dead_locks( is ABSENT from $PREFIX_REF — this is a new capability"
fi
echo

echo "=== VERDICT ==="
echo "failed steps: $FAILED"
[ "$FAILED" -eq 0 ] && echo "ALL CLAIMS RE-VERIFIED (rc=0)" || echo "FAILED (rc=$FAILED)"
exit "$([ "$FAILED" -eq 0 ] && echo 0 || echo 1)"
