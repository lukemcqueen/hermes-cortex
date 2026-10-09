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
#   land-when-clean-probe.sh [--repo DIR] [--landed-commit SHA]
#                            [--fixed-marker PATH:MARKER:MIN] PATH [PATH...]
#
# Output:
#   blockers=<n> head=<short-sha> origin_tip=<short-sha> origin_integrated=<yes|no>
#   fix_in_origin=<n> landed=<yes|no|n/a>
#
#   blockers          = uncommitted (staged or unstaged) entries among PATH...,
#                       i.e. exactly the entries that will block an integration
#   origin_integrated = is origin/<default-branch> already an ancestor of HEAD
#   fix_in_origin     = occurrences of MARKER in origin's copy of PATH (0 when
#                       --fixed-marker is absent)
#   landed            = yes when EITHER test passes: --landed-commit is present in
#                       origin's default branch, OR --fixed-marker's marker
#                       appears at least MIN times in origin's copy of PATH.
#
# WHY the content test exists (--fixed-marker): a SHA is rewritten whenever another
# session rebases a shared branch (observed 2026-10-09: a commit was rewritten
# 120758c2 -> 09d27193 with byte-identical content), so a SHA test can silently
# never fire again; and a commit-SUBJECT test can match an unrelated commit with
# the same message. File CONTENT cannot be rebased away or faked by a message —
# ask origin's copy of the file whether it actually contains the change.
#
# Exit codes: 0 printed a state (always), 2 usage error.
#
# Deliberately NOT `set -e`: a probe must always print a line; a failing git call
# degrades to an "unknown" field instead of aborting the tick silently.
set -u

REPO=""
LANDED_COMMIT=""
FIXED_MARKER_SPEC=""
PATHS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2 ;;
    --landed-commit) LANDED_COMMIT="${2:-}"; shift 2 ;;
    --fixed-marker) FIXED_MARKER_SPEC="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,44p' "$0"; exit 0 ;;
    *) PATHS+=("$1"); shift ;;
  esac
done

USAGE="usage: $0 [--repo DIR] [--landed-commit SHA] [--fixed-marker PATH:MARKER:MIN] PATH [PATH...]"
if [[ ${#PATHS[@]} -eq 0 ]]; then
  echo "$USAGE" >&2
  exit 2
fi

REPO="${REPO:-$PWD}"
cd "$REPO" 2>/dev/null || {
  echo "repo=missing blockers=unknown head=unknown origin_tip=unknown origin_integrated=unknown fix_in_origin=unknown landed=unknown"
  exit 0
}

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

# Test 1 — the commit is on origin (SHA; breaks when a rebase rewrites it).
sha_landed=no
if [[ -n "$LANDED_COMMIT" ]]; then
  if git branch -r --contains "$LANDED_COMMIT" 2>/dev/null | grep -q "^  ${base_branch}\$"; then
    sha_landed=yes
  fi
fi

# Test 2 — origin's copy of the file CONTAINS the change (content; survives rebases).
fix_in_origin=0
marker_landed=no
if [[ -n "$FIXED_MARKER_SPEC" ]]; then
  # SPEC is PATH:MARKER:MIN. A malformed spec is a usage error, not a silent "no".
  mfile="${FIXED_MARKER_SPEC%%:*}"
  rest="${FIXED_MARKER_SPEC#*:}"
  mmarker="${rest%%:*}"
  mmin="${rest#*:}"
  if [[ -z "$mfile" || -z "$mmarker" || "$mmin" == "$rest" || ! "$mmin" =~ ^[0-9]+$ ]]; then
    echo "$USAGE (--fixed-marker wants PATH:MARKER:MIN)" >&2
    exit 2
  fi
  fix_in_origin=$(git show "${base_branch}:${mfile}" 2>/dev/null | grep -c "$mmarker")
  fix_in_origin=${fix_in_origin:-0}
  if [[ "$fix_in_origin" -ge "$mmin" ]]; then
    marker_landed=yes
  fi
fi

landed=n/a
if [[ -n "$LANDED_COMMIT" || -n "$FIXED_MARKER_SPEC" ]]; then
  landed=no
  if [[ "$sha_landed" == "yes" || "$marker_landed" == "yes" ]]; then
    landed=yes
  fi
fi

echo "blockers=${blockers} head=${head} origin_tip=${tip} origin_integrated=${integrated} fix_in_origin=${fix_in_origin} landed=${landed}"
