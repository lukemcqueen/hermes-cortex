#!/usr/bin/env bash
# git-stalled-rebase.sh — fail-safe cleanup for an interrupted `git pull --rebase`.
#
# Why this exists (measured 2026-10-18): a sync that runs `git pull --rebase` and hits
# a conflict (or a timeout) LEAVES THE REPOSITORY STOPPED MID-REBASE. The conflicted
# index then refuses every commit ("Committing is not possible because you have
# unmerged files") AND every push on the host until someone cleans it up by hand — an
# entire host is blocked by one failed pull, with no signal other than the refusal.
#
# `abort_stalled_rebase` restores the PRE-PULL state. The contract has two halves, and the
# second one is the easy one to forget: `git rebase --abort` returns the branch to its
# ORIGINAL local tip, so every local commit that existed before the pull is preserved, while
# the in-progress rebase is DISCARDED — an upstream commit that was being applied is NOT
# carried onto this branch by the abort. A failed sync is thereby inert instead of host-wide
# blocking.
#
# Usage:
#   source .../git-stalled-rebase.sh
#   abort_stalled_rebase        # run with the CWD inside the repository
#
# Contract:
#   stdout — ONE line when a stopped rebase is aborted, NOTHING when there is nothing
#            to do (callers use empty stdout as their silence signal)
#   rc 0   — the repository is usable (nothing to do, or the abort succeeded)
#   rc 1   — a rebase was in progress and could NOT be aborted (needs manual attention)
abort_stalled_rebase() {
  local git_dir
  git_dir="$(git rev-parse --git-dir 2>/dev/null)" || return 1
  if [ ! -d "$git_dir/rebase-merge" ] && [ ! -d "$git_dir/rebase-apply" ]; then
    return 0
  fi
  # Capture the abort's OWN output instead of discarding it: with `>/dev/null 2>&1` a FAILED
  # abort told the operator nothing about why — the one case where the reason is the
  # actionable part. stdout is captured as well, which leaves the silence contract below
  # intact (the abort-success line is still the only thing ever written to stdout).
  local abort_output
  if abort_output="$(git rebase --abort 2>&1)"; then
    echo "aborted a stopped rebase — pre-pull state restored (local commits preserved)"
    return 0
  fi
  local first_line="${abort_output%%$'\n'*}"
  echo "could NOT abort the stopped rebase — the repository needs manual attention${first_line:+ — ${first_line}}" >&2
  return 1
}
