#!/usr/bin/env bash
# land-when-clean-probe.sh — deterministic state probe for a "land when clean"
# cron monitor.
#
# WHY: on a host where several sessions share ONE checkout, `git merge origin/main`
# is refused while a PEER holds uncommitted changes to a file the merge must
# update ("Your local changes to the following files would be overwritten by
# merge"). The correct response is to WAIT for the owner — never stash, clean or
# commit another session's work — so the landing needs a cheap watcher. Paired
# with a cron job's `monitor:` this probe runs every tick with NO LLM cost:
# the scheduler hashes its output and only wakes the agent when the text CHANGES
# (blockers cleared, or the landing already happened).
#
# The output must be STABLE while nothing changes — no timestamps, no volatile
# fields — or every tick looks changed and the agent runs needlessly.
#
# Usage (all paths are relative to the repository root):
#   land-when-clean-probe.sh [--repo DIR] [--landed-commit SHA] PATH [PATH...]
#
# Output:
#   blockers=<n> head=<short-sha> origin_tip=<short-sha> origin_integrated=<yes|no> landed=<yes|no|n/a>
#
#   blockers          = uncommitted (staged or unstaged) entries among PATH...,
#                       i.e. exactly the entries that will block an integration
#   origin_integrated = is origin/<default-branch> already an ancestor of HEAD
#   landed            = --landed-commit present in origin's default branch
#
# Exit codes: 0 printed a state (always), 2 usage error.
#
# Deliberately NOT `set -e`: a probe must always print a line; a failing git call
# degrades to an "unknown" field instead of aborting the tick silently.
set -u

REPO=""
LANDED_COMMIT=""
PATHS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2 ;;
    --landed-commit) LANDED_COMMIT="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) PATHS+=("$1"); shift ;;
  esac
done

if [[ ${#PATHS[@]} -eq 0 ]]; then
  echo "usage: $0 [--repo DIR] [--landed-commit SHA] PATH [PATH...]" >&2
  exit 2
fi

REPO="${REPO:-$PWD}"
cd "$REPO" 2>/dev/null || { echo "repo=missing blockers=unknown head=unknown origin_tip=unknown origin_integrated=unknown landed=unknown"; exit 0; }

git fetch -q origin 2>/dev/null || true

# Count the entries that block an integration — one line per dirty path.
blockers=$(git status --porcelain -- "${PATHS[@]}" 2>/dev/null | wc -l | tr -d ' ')
blockers=${blockers:-unknown}

head=$(git rev-parse --short HEAD 2>/dev/null || echo unknown)
tip=$(git rev-parse --short origin/HEAD 2>/dev/null || echo unknown)
base_branch=$(git symbolic-ref --short -q refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)

if git merge-base --is-ancestor "$base_branch" HEAD 2>/dev/null; then
  integrated=yes
else
  integrated=no
fi

if [[ -z "$LANDED_COMMIT" ]]; then
  landed=n/a
elif git branch -r --contains "$LANDED_COMMIT" 2>/dev/null | grep -q "^  ${base_branch}\$"; then
  landed=yes
else
  landed=no
fi

echo "blockers=${blockers} head=${head} origin_tip=${tip} origin_integrated=${integrated} landed=${landed}"
