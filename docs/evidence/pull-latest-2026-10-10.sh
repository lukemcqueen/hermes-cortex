#!/usr/bin/env bash
# Evidence for governance cycle pull-latest-hc-update-cortex (2026-10-10).
# Reproduces, with actual output:
#   1. Upstream has nothing new (local main ahead, 0 behind, empty HEAD..@{u})
#   2. cortex-update deployed HEAD (state/update-commit == git rev-parse HEAD)
#   3. Repo-local ~/hermes-cortex/.hermes-cortex is absent (removed; durable
#      because agent-auto-save-sessions.py main() skips projects without
#      .hermes-cortex)
#   4. Doctor: only remaining FAIL is AGENTS.md (steadfaste) — pre-existing
#      issue #57, not caused by this update.
set -u
REPO="${HOME}/hermes-cortex"
echo "=== 1. UPSTREAM STATE ==="
git -C "$REPO" fetch origin 2>&1
git -C "$REPO" rev-list --left-right --count HEAD...@{u}
echo "--- new upstream commits (empty = nothing to pull) ---"
git -C "$REPO" log --oneline HEAD..@{u}
echo
echo "=== 2. DEPLOY SYNC (update-commit vs HEAD) ==="
cat "${HOME}/.hermes-cortex/state/update-commit"
git -C "$REPO" rev-parse HEAD
echo
echo "=== 3. REPO-LOCAL .hermes-cortex ABSENT ==="
if [ -e "$REPO/.hermes-cortex" ]; then
  echo "PRESENT (FAIL)"
  ls -la "$REPO/.hermes-cortex"
else
  echo "absent — OK"
fi
echo
echo "=== 4. DOCTOR FAIL/WARN LINES ==="
python3 "$REPO/ops/scripts/manage/cortex-doctor.py" --quiet 2>&1 | grep -E "❌|⚠️|Overall" || true
