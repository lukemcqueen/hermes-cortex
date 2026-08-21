#!/usr/bin/env bash
# git-main-sync.sh — return a hermes-cortex repo to origin/main and pull latest.
#
# Doctor "Repo branch" WARN remediation ("Run: git checkout main"): a repo
# left on a feature/detached branch (e.g. a titus/* PR branch) silently
# ignores `git pull origin main` in the UPDATE_REQUEST handler, so fleet
# updates never land on that host. This opt-in tool fixes the branch state
# on demand — run it via the bus EXEC protocol (hc exec <agent> git-main-sync.sh)
# rather than changing daily sync behaviour (a fleet-wide auto-checkout
# would yank dev agents off their work branches).
#
# After the pull, the repo's post-merge hook auto-runs cortex-update.sh, so
# the new commit is deployed in the same pass.
#
# Usage:
#   git-main-sync.sh [REPO]        # default: $HOME/hermes-cortex
#   git-main-sync.sh --check       # report-only: branch + behind/ahead, no changes
#
# Exit: 0 = on main and current (or --check clean), 1 = error (left untouched).
set -euo pipefail

REPO="${1:-$HOME/hermes-cortex}"
CHECK_ONLY=0
if [ "${1:-}" = "--check" ]; then
  CHECK_ONLY=1
  REPO="${2:-$HOME/hermes-cortex}"
fi

[ -d "$REPO/.git" ] || { echo "ERROR: not a git repo: $REPO" >&2; exit 1; }

ts() {
  if [[ -n "${HERMES_TIMEZONE:-}" ]]; then
    TZ="${HERMES_TIMEZONE}" date '+%Y-%m-%d %H:%M %Z'
  else
    date '+%Y-%m-%d %H:%M %Z'
  fi
}

cd "$REPO"

CUR="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo detached)"
echo "[$(ts) git-main-sync] repo: $REPO"
echo "[$(ts) git-main-sync] current branch: ${CUR}"

# How far is the current HEAD from origin/main? (fetch first so the ref is fresh)
git fetch origin 2>/dev/null || { echo "ERROR: git fetch origin failed" >&2; exit 1; }
BEHIND="$(git rev-list --count HEAD..origin/main 2>/dev/null || echo 0)"
AHEAD="$(git rev-list --count origin/main..HEAD 2>/dev/null || echo 0)"
echo "[$(ts) git-main-sync] HEAD is ${BEHIND} behind, ${AHEAD} ahead of origin/main"

if [ "$CHECK_ONLY" -eq 1 ]; then
  if [ "$CUR" = "main" ] && [ "$BEHIND" -eq 0 ]; then
    echo "[$(ts) git-main-sync] OK: on main, up to date"
    exit 0
  fi
  echo "[$(ts) git-main-sync] ACTION NEEDED: not on main or ${BEHIND} behind — run without --check"
  exit 0
fi

if [ "$CUR" != "main" ]; then
  # Detached HEAD or feature branch — move to main. Stash first so no work is lost.
  DIRTY=0
  git diff --quiet 2>/dev/null && git diff --cached --quiet 2>/dev/null || DIRTY=1
  if [ "$DIRTY" -eq 1 ]; then
    echo "[$(ts) git-main-sync] stashing local changes"
    git stash push -m "git-main-sync auto-stash $(date -u +%Y%m%dT%H%M%SZ)" >/dev/null || true
  fi
  echo "[$(ts) git-main-sync] checking out main"
  git checkout main || { echo "ERROR: git checkout main failed" >&2; exit 1; }
  if [ "$DIRTY" -eq 1 ]; then
    # Restore the stash onto main — conflicts are surfaced to the operator.
    git stash pop 2>&1 | sed 's/^/[git-main-sync] /' || true
  fi
fi

if [ "$BEHIND" -gt 0 ]; then
  echo "[$(ts) git-main-sync] pulling origin main (post-merge hook deploys)"
  git pull --rebase origin main || { echo "ERROR: git pull --rebase failed" >&2; exit 1; }
else
  echo "[$(ts) git-main-sync] already up to date"
fi

echo "[$(ts) git-main-sync] now on $(git rev-parse --abbrev-ref HEAD) at $(git rev-parse --short HEAD)"
echo "[$(ts) git-main-sync] done"
