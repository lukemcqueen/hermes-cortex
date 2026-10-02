#!/usr/bin/env bash
# session-identity.sh — give a concurrent session its OWN git authorship.
#
# WHY
#   Two sessions in one working tree collide twice over:
#     1. they share ONE git index, so a commit in either sweeps the other's
#        staged work (observed 2026-10-02: session A's staged 20-line edit
#        landed inside session B's commit e40139b6);
#     2. both author as the same identity, so commits cannot be attributed and
#        the close-gate's author-scoping cannot tell the sessions apart.
#   Both are fixed by "one session = one worktree = one branch = one identity".
#
# RULE
#   This touches GIT AUTHORSHIP ONLY. The bus/routing identity — AGENT_NAME in
#   agent.env, which decides the inbox_<agent> queue and the on-bus name — is
#   NEVER modified here. Session-appending the bus identity would break routing.
#
# USAGE
#   session-identity.sh show                 # worktree, branch, identity, agent
#   session-identity.sh set <tag>            # git identity -> <agent>-<tag>
#   session-identity.sh new <tag> [path]     # new worktree + identity (recommended)
#
# Exit: 0 ok, 1 usage/validation error, 2 not in a git work tree.
set -euo pipefail

DEPLOY="${CORTEX_DEPLOY_HOME:-$HOME/.hermes-cortex}"
AGENT_ENV="$DEPLOY/agent.env"

die() { echo "session-identity: $*" >&2; exit 1; }

_agent_name() {
  if [[ -f "$AGENT_ENV" ]]; then
    # shellcheck disable=SC1090
    ( set -a; . "$AGENT_ENV"; set +a; printf '%s' "${AGENT_NAME:-}" )
  fi
}

_email_domain() {
  # Domain from the PRIMARY worktree's identity, else a sane default. The
  # primary keeps the host identity; sessions are distinguished by the local part.
  local primary email dom
  primary="$(git worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2; exit}')" || true
  if [[ -n "${primary:-}" ]]; then
    email="$(git -C "$primary" config user.email || true)"
    dom="${email##*@}"
    [[ -n "$dom" && "$dom" != "$email" ]] && { printf '%s' "$dom"; return; }
  fi
  printf 'hermes.local'
}

_validate_tag() {
  [[ $# -ge 1 && -n "${1:-}" ]] || die "a session tag is required (e.g. set pi)"
  [[ "${1}" =~ ^[A-Za-z0-9._-]+$ ]] || die "tag '${1}' must match [A-Za-z0-9._-]+"
}

cmd_show() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 2
  local agent; agent="$(_agent_name)"
  printf 'worktree : %s\n' "$(git rev-parse --show-toplevel)"
  printf 'branch   : %s\n' "$(git rev-parse --abbrev-ref HEAD)"
  printf 'git who  : %s <%s>\n' "$(git config user.name || echo '-')" "$(git config user.email || echo '-')"
  printf 'agent    : %s   (bus identity — NOT modified by this tool)\n' "${agent:-<unset>}"
  if [[ "$(git config --get extensions.worktreeConfig 2>/dev/null || echo false)" != "true" ]]; then
    echo "NOTE     : extensions.worktreeConfig is off, so 'git config' here writes"
    echo "           to the SHARED config and would change every worktree's identity."
  fi
}

cmd_set() {
  _validate_tag "${1:-}"
  local tag="$1" agent dom
  agent="$(_agent_name)"
  [[ -n "$agent" ]] || die "AGENT_NAME not found in $AGENT_ENV"
  dom="$(_email_domain)"

  # Per-worktree scope, so setting an identity here cannot leak to other trees.
  git config extensions.worktreeConfig true
  git config --worktree user.name  "${agent}-${tag}"
  git config --worktree user.email "${agent}+${tag}@${dom}"

  # Prove the bus identity is untouched — this tool must never change routing.
  local after; after="$(_agent_name)"
  [[ "$after" == "$agent" ]] || die "AGENT_NAME changed ($agent -> $after); aborting"

  printf 'set: %s <%s>  (agent %s unchanged)\n' \
    "$(git config user.name)" "$(git config user.email)" "$agent"
}

cmd_new() {
  _validate_tag "${1:-}"
  local tag="$1" path="${2:-$HOME/hc-session-${1}}"
  [[ -e "$path" ]] && die "path already exists: $path"
  local primary; primary="$(git rev-parse --show-toplevel)"
  git -C "$primary" fetch -q origin main
  git -C "$primary" worktree add "$path" -b "session/${tag}" origin/main
  ( cd "$path" && cmd_set "$tag" )
  printf 'worktree: %s (branch session/%s) — run your session here\n' "$path" "$tag"
}

case "${1:-}" in
  show) shift; cmd_show "$@" ;;
  set)  shift; cmd_set  "$@" ;;
  new)  shift; cmd_new  "$@" ;;
  *) echo "usage: $(basename "$0") {show|set <tag>|new <tag> [path]}" >&2; exit 1 ;;
esac
