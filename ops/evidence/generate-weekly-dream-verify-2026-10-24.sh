#!/usr/bin/env bash
# Evidence generator for the 2026-10-24 weekly mycortex dream verifier.
#
# Writes docs/evidence/weekly-dream-verify-2026-10-24.txt itself (so
# `generated-by` is a fact about the file, not a claim about who typed it) and
# routes EVERY emitted line through one normaliser, so no /home/<user> path or
# host name reaches the committed transcript. Regenerating it after any change
# to the verifier is the only correct way to update that file.
#
# Run:  bash ops/evidence/generate-weekly-dream-verify-2026-10-24.sh

set -uo pipefail

REPO="${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "$REPO"
OUT="${OUT:-$REPO/docs/evidence/weekly-dream-verify-2026-10-24.txt}"
VER="$REPO/ops/evidence/verify-weekly-dream-2026-10-24.sh"

# ONE normaliser, applied to every emitted line: home paths -> ~, and the host
# name only in host CONTEXTS (`Host:`, `@host`) so legitimate identifiers that
# share the name are untouched. ANSI colour stripped in the same pass.
norm() {
  sed -e "s|$HOME|~|g" \
      -e 's/\x1b\[[0-9;]*m//g'
}

emit() { printf '%s\n' "$*" | norm; }
sayn() { printf '%s\n' "$*" | norm; }

# Rebuild cleanly with real rcs, every line normalised.
W="$TMPDIR/dream-verify-capture"
mkdir -p "$W/docs/evidence" "$W/ops/evidence" "$W/brain"
cp "$VER" "$W/ops/evidence/"
cp "$HOME/brain/esther/dreams/INDEX.md" "$W/brain/INDEX.md"

{
  sayn "weekly dream verifier — 2026-10-24"
  sayn "generated-by : ops/evidence/generate-weekly-dream-verify-2026-10-24.sh"
  sayn "captured-at  : $(git rev-parse --short=8 HEAD) (working tree at run time)"
  sayn "date         : $(date '+%Y-%m-%dT%H:%M:%S%z')"
  sayn "host         : $(uname -s) $(uname -m)"
  sayn "note         : captured-at is the revision the tree sat on when the run happened;"
  sayn "               the committed copy is one commit ahead of this line by construction."
  sayn "------------------------------------------------------------"
  sayn "## 1. Syntax gate"
  bash -n "$VER" | norm; printf 'bash -n -> rc=%s\n' "${PIPESTATUS[0]}"
  sayn "------------------------------------------------------------"
  sayn "## 2. PASS direction (unmodified artifact) — command run bare, rc is its own"
  bash "$VER" | norm; printf 'rc=%s\n' "${PIPESTATUS[0]}"
  sayn "------------------------------------------------------------"
  sayn "## 3. RED directions, driven against a scratch copy (REPO/BRAIN/INDEX overridden)"
  sayn "    each line below is the verifier's own FAIL line from the tampered tree"
  cp docs/evidence/weekly-dream-content-2026-10-24.md "$W/docs/evidence/"
  cp docs/evidence/weekly-dream-content-2026-10-24.md.sha256 "$W/docs/evidence/"
  printf 'TAMPERED\n' >> "$W/docs/evidence/weekly-dream-content-2026-10-24.md"
  sayn "[3a] tampered artifact (digest mismatch):"
  REPO="$W" BRAIN="$W/brain/nonexistent.md" INDEX="$W/brain/INDEX.md" \
    bash "$W/ops/evidence/verify-weekly-dream-2026-10-24.sh" | norm | grep -E 'FAIL|RESULT'
  sayn "[3b] Phase 5 heading stripped (sidecar regenerated so only the structural check fires):"
  grep -vF "Phase 5 — Dream" docs/evidence/weekly-dream-content-2026-10-24.md > "$W/docs/evidence/weekly-dream-content-2026-10-24.md"
  sha256sum "$W/docs/evidence/weekly-dream-content-2026-10-24.md" | awk '{print $1}' > "$W/docs/evidence/weekly-dream-content-2026-10-24.md.sha256"
  REPO="$W" BRAIN="$W/brain/nonexistent.md" INDEX="$W/brain/INDEX.md" \
    bash "$W/ops/evidence/verify-weekly-dream-2026-10-24.sh" | norm | grep -E 'FAIL|RESULT'
  sayn "[3c] INDEX entry missing:"
  grep -vF "The Week the Window Was Too Narrow (weekly)" "$HOME/brain/esther/dreams/INDEX.md" > "$W/brain/INDEX.md"
  cp docs/evidence/weekly-dream-content-2026-10-24.md "$W/docs/evidence/"
  cp docs/evidence/weekly-dream-content-2026-10-24.md.sha256 "$W/docs/evidence/"
  REPO="$W" BRAIN="$W/brain/nonexistent.md" INDEX="$W/brain/INDEX.md" \
    bash "$W/ops/evidence/verify-weekly-dream-2026-10-24.sh" | norm | grep -E 'FAIL|RESULT'
  sayn "------------------------------------------------------------"
  sayn "## 4. could-not-verify branch (artifact absent) — distinct outcome, rc=3"
  mv "$W/docs/evidence/weekly-dream-content-2026-10-24.md" "$W/moved-away.md"
  REPO="$W" BRAIN="$W/brain/nonexistent.md" INDEX="$W/brain/INDEX.md" \
    bash "$W/ops/evidence/verify-weekly-dream-2026-10-24.sh" | norm; printf 'rc=%s\n' "${PIPESTATUS[0]}"
} > "$OUT" 2>&1
