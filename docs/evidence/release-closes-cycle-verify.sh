#!/usr/bin/env bash
# Re-run every claim behind "release-first paths close their cycle" (2026-10-14).
#
# One command, exits non-zero on any failed claim, printing each command above its own
# output and the command's OWN exit code (measured on the command, never through a pipe).
#
#   1. the behavioural probe against the REAL module, with a THROWAWAY state dir and DB;
#   2. the three governance suites pinning the source-level contract;
#   3. the same probe's other half: the DEFECTS are present in the pre-fix revision
#      extracted from git history, so both sides of the discrimination are re-runnable;
#   4. the wider governance selection, so a regression outside the three files shows up.
#
# Read-only outside the scratch dir it creates. Plain python3 (the module guards its own
# `mcp` import), so a Pi / Claude Code / plain-shell session can run it too.
#
# Usage: bash docs/evidence/release-closes-cycle-verify.sh [repo-path] [pre-fix-ref]
set -uo pipefail

REPO="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
PREFIX_REF="${2:-origin/main}"
cd "$REPO" || { echo "no such repo: $REPO"; exit 2; }

FAILED=0
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/release-closes-cycle.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT

# Everything the tools print goes through this, so the committed transcript carries no
# home directory of this host (the redaction is at the GENERATOR, never hand-patched in).
norm() { sed -e "s|$HOME|~|g"; }

run() {
  local label="$1"; shift
  echo "--- $label"
  echo "\$ $*" | norm
  local out rc
  out="$("$@" 2>&1)"; rc=$?          # rc is the COMMAND's own, not a pipe's last stage
  printf '%s\n' "$out" | norm
  echo "rc=$rc"
  [ "$rc" -eq 0 ] || FAILED=$((FAILED + 1))
  echo
}

echo "repo: $(pwd | norm)"
echo "pre-fix ref for the discrimination: $PREFIX_REF"
echo "module under test: mcp-servers/loop-gov-mcp.py (working copy)"
if command -v sha256sum >/dev/null 2>&1; then
  echo "  sha256 $(sha256sum mcp-servers/loop-gov-mcp.py | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  echo "  sha256 $(shasum -a 256 mcp-servers/loop-gov-mcp.py | awk '{print $1}')"
else
  echo "  sha256: could not verify (no sha256sum/shasum on this host)"
fi
echo "NOTE: this host's cron also regenerates docs/evidence/briefings/*, so the working"
echo "      tree may carry that artifact beside this change. It is not part of this change"
echo "      and neither the probe nor the suites read it."
echo "NOTE: the probe runs under plain python3 on purpose — the module guards its own 'mcp'"
echo "      import, so its warning about the stdio server is expected here and does not"
echo "      affect the checks (all of which are exercised through the module's helpers)."
echo

git show "$PREFIX_REF:mcp-servers/loop-gov-mcp.py" > "$SCRATCH/pre-fix.py" 2>/dev/null
echo "pre-fix module written to: $SCRATCH/pre-fix.py" | norm
echo

run "1. behavioural probe (throwaway state + DB) against the working copy" \
    python3 docs/evidence/release-closes-cycle-probe.py "$(pwd)"

run "2a. governance suites (file alone)" \
    bash tests/run-tests.sh \
      tests/test_release_after_refusal_closes_cycle.py \
      tests/test_metadata_refusal_releases_lock.py \
      tests/test_blocked_releases_lock.py -q

run "2b. wider governance selection (regressions outside the three files)" \
    bash tests/run-tests.sh tests/ \
      -q -k "release or lock or govern or mcp or cycle or closeout"

run "3. the other half: the defects ARE present in the pre-fix revision" \
    python3 docs/evidence/release-closes-cycle-prefix-check.py "$SCRATCH/pre-fix.py"

echo "=== VERDICT ==="
echo "failed steps: $FAILED"
[ "$FAILED" -eq 0 ] && echo "ALL CLAIMS RE-VERIFIED (rc=0)" || echo "FAILED (rc=$FAILED)"
exit "$([ "$FAILED" -eq 0 ] && echo 0 || echo 1)"
