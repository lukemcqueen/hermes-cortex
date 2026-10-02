#!/usr/bin/env bash
# Full-suite evidence — run the repo's test suite and record a REPRODUCIBLE artifact.
#
# Why this exists: a pasted test transcript cannot be re-executed by a later
# reviewer, so "the suite is green" stayed an unverifiable claim (self-adversarial
# review ADV-10514-1). This script regenerates the evidence from the repo with one
# command, names the exact revision it ran against, and exits non-zero on any
# failure so it can gate CI.
#
# Usage: bash ops/scripts/quality/full-suite-evidence.sh [output-file]
# Exit:  0 = suite green (0 failed) · 1 = failures (listed in the artifact)
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
OUT="${1:-$REPO/docs/evidence/full-suite-results.txt}"
# History ledger: the detailed artifact is per-run and gets overwritten, so a
# FAILING run's evidence used to vanish the moment a later run passed. The
# ledger keeps one durable line per run — a failure cannot be erased by time.
HIST="$REPO/docs/evidence/full-suite-results-history.txt"
LOG="$(mktemp "${TMPDIR:-/tmp}/full-suite-XXXXXX.log")"
trap 'rm -f "$LOG"' EXIT

cd "$REPO" || exit 1

echo "▶ running the full suite (this takes a few minutes)…"
python3 -m pytest tests/ -q -p no:cacheprovider >"$LOG" 2>&1
_rc=$?

# sed (not tail) reads ALL input, so nothing upstream can die of SIGPIPE.
_summary="$(grep -E '[0-9]+ (passed|failed)' "$LOG" | sed -n '$p')"
_failed="$(grep -c '^FAILED ' "$LOG")"
_sha="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
_dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
_total="$(wc -l < "$LOG" | tr -d ' ')"
_tail_start=$(( _total > 20 ? _total - 20 : 1 ))

{
  echo "# Full repo test suite — measured evidence"
  echo
  echo "command: python3 -m pytest tests/ -q -p no:cacheprovider"
  echo "regenerate: bash ops/scripts/quality/full-suite-evidence.sh"
  echo "date (UTC): $(date -u '+%Y-%m-%d %H:%M:%S')"
  echo "host: $(hostname)"
  echo "revision: ${_sha} (${_branch}), uncommitted paths: ${_dirty}"
  echo
  echo "measured: ${_summary}"
  echo "failures: ${_failed}"
  echo
  echo "Tail of the run:"
  sed -n "${_tail_start},\$p" "$LOG"
  echo
  if (( _failed > 0 )); then
    echo "Failing tests:"
    grep '^FAILED ' "$LOG"
  else
    echo "Failing tests: none"
  fi
} >"$OUT"

echo "✅ wrote $OUT"
echo "   ${_summary}"

# Durable ledger line (append-only) — the detailed artifact is overwritten by the
# next run, so the failure record must live somewhere that does not get recycled.
printf '%s | rev=%s (%s) | %s | failures=%s\n' \
  "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$_sha" "$_branch" "$_summary" "$_failed" >>"$HIST"
echo "   ledger: $HIST"

if (( _rc != 0 || _failed > 0 )); then
  echo "❌ suite is NOT green (${_failed} failing) — see ${OUT} and ${HIST}" >&2
  exit 1
fi
echo "✅ suite green"
exit 0
