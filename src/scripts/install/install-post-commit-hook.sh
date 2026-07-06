#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  install-post-commit-hook.sh — Install post-commit git hook
#
#  Installs scripts/post-commit-notify.sh as a git post-commit
#  hook in the hermes-cortex repo, so every commit auto-notifies
#  all agents via inbox broadcast.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
HOOK_DIR="${REPO_DIR}/.git/hooks"
HOOK_PATH="${HOOK_DIR}/post-commit"
NOTIFY_SCRIPT="${REPO_DIR}/src/scripts/post-commit-notify.sh"

if [ ! -d "$HOOK_DIR" ]; then
  echo "✗ No .git/hooks directory at ${HOOK_DIR}"
  echo "  Are you inside the hermes-cortex repo?"
  exit 1
fi

if [ ! -f "$NOTIFY_SCRIPT" ]; then
  echo "✗ Notification script not found at ${NOTIFY_SCRIPT}"
  exit 1
fi

cat > "$HOOK_PATH" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="$(cd "$(git rev-parse --git-dir 2>/dev/null)/.." && pwd 2>/dev/null)"
if [ -n "$REPO_DIR" ] && [ -f "${REPO_DIR}/src/scripts/post-commit-notify.sh" ]; then
  bash "${REPO_DIR}/src/scripts/post-commit-notify.sh" &
fi
HOOK

chmod +x "$HOOK_PATH"
echo "✓ Installed post-commit hook at ${HOOK_PATH}"
echo "  → Runs src/scripts/post-commit-notify.sh after every commit"