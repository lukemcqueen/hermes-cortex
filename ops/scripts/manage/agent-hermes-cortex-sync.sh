#!/usr/bin/env bash
# hermes-cortex-sync.sh — no_agent watchdog: pull latest hermes-cortex + re-sync tools
#
# Watchdog pattern:
#   Empty stdout → silent (already up-to-date)

# Timezone-aware timestamp: honors HERMES_TIMEZONE (IANA), else system TZ.
ts() {
  if [[ -n "${HERMES_TIMEZONE:-}" ]]; then
    TZ="${HERMES_TIMEZONE}" date '+%Y-%m-%d %H:%M %Z'
  else
    date '+%Y-%m-%d %H:%M %Z'
  fi
}
#   Text output  → delivered (updated or error)
#
# Schedule: daily (recommended 22:33 KST, 10 min after hermes-update)
set -euo pipefail

CORTEX_REPO="$HOME/hermes-cortex"

# timeout: linux=timeout, mac=gtimeout (brew coreutils). Never assume the
# binary exists — fail with a clear message instead of a cryptic 127.
TIMEOUT_CMD=""
for _cmd in timeout gtimeout; do
  if command -v "$_cmd" >/dev/null 2>&1; then TIMEOUT_CMD="$_cmd"; break; fi
done
if [ -z "$TIMEOUT_CMD" ]; then
  echo "[$(ts) cortex-sync] FATAL: neither 'timeout' nor 'gtimeout' found — install coreutils (brew install coreutils on macOS)"
  exit 1
fi

if [ ! -d "$CORTEX_REPO" ]; then
    echo "[$(ts) cortex-sync] Repo not found at $CORTEX_REPO"
    exit 1
fi

cd "$CORTEX_REPO"

# Fail-safe cleanup for an interrupted rebase (added 2026-10-18). A `git pull
# --rebase` that hits a conflict leaves the repository STOPPED MID-REBASE; every
# commit and push on the host is then refused ("Committing is not possible
# because you have unmerged files") until someone cleans it up by hand. Sourced,
# not required-if-present: a deploy that ships one without the other must fail
# loudly here rather than silently drop the guard.
# shellcheck source=ops/scripts/lib/git-stalled-rebase.sh
source "$CORTEX_REPO/ops/scripts/lib/git-stalled-rebase.sh"

# Use the same strategy as the working monitor script - assert repo exists and log what's happening
log()  { echo "[$(ts) cortex-sync] $*"; }
stash_pop() {
    if $STASHED; then
        # `... | while ...; done || true` used to swallow a FAILED `git stash pop` — a conflict
        # leaves the changes STASHED — so a restore that never happened looked identical to one
        # that did (adversarial finding ADV-12971-4, 2026-10-18). `set -o pipefail` is on above,
        # so the status captured here is the pop's own. It is REPORTED loudly, and deliberately
        # NOT returned: every caller is already on a failure path that ends in its own `exit 1`,
        # and `set -e` would turn a non-zero return into an abort that skips their message.
        local rc=0
        git stash pop 2>&1 | while IFS= read -r line; do echo "[$(ts) cortex-sync] $line"; done || rc=$?
        if [ "$rc" -ne 0 ]; then
            log "WARNING: 'git stash pop' FAILED (rc=$rc) — the stashed changes are probably STILL in 'git stash list'"
        fi
    fi
}

# Stash any uncommitted changes before fetch/rebase
STASHED=false
if ! git diff --quiet || ! git diff --cached --quiet; then
    log "Stashing local changes before sync"
    git stash push -m "auto-stash before cortex-sync $(date -u +%Y%m%dT%H%M%SZ)" 2>&1 | while IFS= read -r line; do log "$line"; done || true
    STASHED=true
fi

FETCH_OUTPUT=$("$TIMEOUT_CMD" 12 git fetch origin 2>&1) || {
    FETCH_EXIT=$?
    CTS=$(ts)
    if [ "$FETCH_EXIT" -eq 124 ]; then
        echo "[$CTS cortex-sync] git fetch timed out after 12s, will retry next cycle"
        stash_pop
        exit 1
    fi
    echo "[$CTS cortex-sync] git fetch failed (exit $FETCH_EXIT)"
    echo "[$CTS cortex-sync] $FETCH_OUTPUT"
    stash_pop
    exit 1
}

# Silent exit if already up-to-date
if ! git log HEAD..origin/main --oneline | grep -q .; then
    stash_pop
    exit 0
fi

# Use rebase instead of merge to handle local auto-remediation commits
# that are ahead of origin. Merge would fail when both sides changed
# the same files (install.sh, scripts, etc.).
# GIT_EDITOR=true prevents editor spawn on conflict — conflicts auto-fail
# instead of hanging indefinitely within the timeout (v2: 2026-06-27).
# SKIP_POST_MERGE=1 (v3: 2026-08-07): the post-merge hook runs
# cortex-update.sh (a 2+ min deploy) which exceeds the network-oriented 20s
# timeout and gets killed mid-deploy — the merge succeeds (reflog) but the
# cron reports error and leaves a partial deploy. The deploy now runs
# explicitly below with its own generous budget.
PULL_OUTPUT=$(GIT_EDITOR=true SKIP_POST_MERGE=1 "$TIMEOUT_CMD" 20 git pull --rebase origin main 2>&1) || {
    PULL_EXIT=$?
    CTS=$(ts)
    # Both failure shapes below (timeout mid-rebase, conflict) can leave the
    # rebase STOPPED. Clear it first so the failure is inert: the helper's
    # `git rebase --abort` returns the branch to its original tip — the original
    # local commits are preserved and the in-progress rebase is discarded — and it
    # reports its own failure rather than succeeding silently. The status is
    # captured EXPLICITLY: a piped helper reports the PIPE's status, so a failed
    # abort would read as success while the host stayed blocked.
    #
    # Written as an explicit if/else rather than `... && rc=0 || rc=$?` so the status
    # capture cannot be MISREAD as the classic `A && B || C` bug. An adversarial review
    # claimed `$?` in that one-liner was always 0, i.e. that this exit path was dead; it
    # was measured FALSE on 2026-10-18 (`f() { return 3; }; out=$(f 2>&1) && rc=0 || rc=$?`
    # yields rc=3), so the one-liner was correct and this rewrite is a CLARITY change, not
    # a bug fix.
    if abort_out=$(abort_stalled_rebase 2>&1); then
        abort_rc=0
    else
        abort_rc=$?
    fi
    if [ -n "$abort_out" ]; then
        printf '%s\n' "$abort_out" | while IFS= read -r line; do log "$line"; done
    fi
    if [ "$abort_rc" -ne 0 ]; then
        log "FATAL: a rebase is stopped in $CORTEX_REPO and could not be aborted — commits and pushes stay blocked until it is cleared by hand"
        stash_pop
        exit 1
    fi
    if [ "$PULL_EXIT" -eq 124 ]; then
        echo "[$CTS cortex-sync] git pull --rebase timed out after 20s, will retry next cycle"
        stash_pop
        exit 1
    fi
    echo "[$CTS cortex-sync] git rebase pull failed (exit $PULL_EXIT)"
    echo "[$CTS cortex-sync] $PULL_OUTPUT"
    stash_pop
    exit 1
}

# Old governance re-sync removed (core/governance/ gone July 2026 — MCP-based replaces it)

# Restore stashed changes
stash_pop

# Explicit deploy — the post-merge hook was skipped above so the 20s pull
# timeout only bounds the network operation. Run the full cortex-update.sh
# now with a generous budget; without this the hook's deploy was killed
# mid-flight at 20s, erroring the cron on every merge (v3: 2026-08-07).
DEPLOY_OUTPUT=$("$TIMEOUT_CMD" 600 bash "$CORTEX_REPO/ops/scripts/cortex-update.sh" 2>&1) || {
    DEPLOY_EXIT=$?
    CTS=$(ts)
    echo "[$CTS cortex-sync] cortex-update.sh failed (exit $DEPLOY_EXIT)"
    echo "[$CTS cortex-sync] $(echo "$DEPLOY_OUTPUT" | tail -20)"
    exit 1
}

# Deploy skills manifest from template
SKILLS_TEMPLATE="$CORTEX_REPO/skills.yaml"
SKILLS_DEST="$HOME/.hermes-cortex/skills.yaml"
if [ -f "$SKILLS_TEMPLATE" ]; then
    if [ ! -f "$SKILLS_DEST" ] || ! diff -q "$SKILLS_TEMPLATE" "$SKILLS_DEST" >/dev/null 2>&1; then
        cp "$SKILLS_TEMPLATE" "$SKILLS_DEST"
        log "skills.yaml deployed from template"
    fi
fi

echo "[$(ts) cortex-sync] hermes-cortex updated, tools re-synced."