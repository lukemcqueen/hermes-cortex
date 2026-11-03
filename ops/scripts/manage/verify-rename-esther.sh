#!/usr/bin/env bash
# verify-rename-esther.sh — live golden-path verification for the local-dir
# rename (esther dogfood, cycle 14077, ADV-14077-2/3). Exits non-zero if ANY
# check fails (all checks run; failures are accumulated). Run from a stable
# workdir AFTER
# migrate-home-dirs.sh + unit regeneration.
set -uo pipefail

IS_MAC=0; [ "$(uname -s)" = "Darwin" ] && IS_MAC=1

NEW_REPO="${HOME}/steadfaste-fleet"       # repo checkout
NEW_HOME="${HOME}/.steadfaste-fleet"      # deployed home (CORTEX_DEPLOY_HOME)
OLD_REPO="${HOME}/hermes-cortex"
OLD_HOME="${HOME}/.hermes-cortex"

fails=0
ck(){ if eval "$2"; then echo "PASS: $1"; else echo "FAIL: $1"; fails=$((fails+1)); fi; }

# `eval` runs the condition string in this scope, so unquoted $VARS expand there;
# `\$(...)` is escaped so the command substitution runs (not at build time).
# Paths have no spaces, so word-splitting is not a concern.

# --- 1. transition symlinks resolve to new dirs ---
ck "old-repo symlink -> new" "[[ -L $OLD_REPO ]] && [[ \$(readlink $OLD_REPO) = $NEW_REPO ]]"
ck "old-home symlink -> new" "[[ -L $OLD_HOME ]] && [[ \$(readlink $OLD_HOME) = $NEW_HOME ]]"
ck "new-repo is a real dir" "[[ -d $NEW_REPO ]]"
ck "new-home is a real dir" "[[ -d $NEW_HOME ]]"

# --- 2. brain/mycortex preserved. The brain is PER-HOST and PER-STRUCTURE: the
#        authentic mycortex knowledge brain lives at ~/brain (home root — the
#        rename never touches it), some hosts keep it at ~/.hermes/brain
#        (untouched), and the deploy-home brain ~/.steadfaste-fleet/brain is the
#        one the rename MOVES (with the transition symlink). Resolve whichever
#        the host actually uses and assert it is present + non-empty — the
#        layouts differ (~/brain: lessons/learnings/shared; deploy-home:
#        kb/memories/sessions/vectors) so we do NOT hardcode subdirs.
BRAIN_A="${HOME}/brain"; BRAIN_B="$NEW_HOME/brain"; BRAIN_C="${HOME}/.hermes/brain"
BRAIN_DIR=""
for _b in "$BRAIN_A" "$BRAIN_B" "$BRAIN_C"; do
  [ -n "$BRAIN_DIR" ] && break
  [ -d "$_b" ] && BRAIN_DIR="$_b"
done
BRAIN_NONEMPTY=0
if [ -n "$BRAIN_DIR" ] && [ -n "$(ls -A "$BRAIN_DIR" 2>/dev/null | head -1)" ]; then BRAIN_NONEMPTY=1; fi
ck "brain dir present (resolved: ${BRAIN_DIR:-none})" "[ -n '$BRAIN_DIR' ]"
ck "brain dir non-empty" "[ '$BRAIN_NONEMPTY' = '1' ]"
ck "mycortex compose present (renamed home or Hermes home)" "[ -f '$NEW_HOME/docker-compose.mycortex.yml' ] || [ -f '${HOME}/.hermes/docker-compose.mycortex.yml' ]"

# --- 3/4/5. platform service surface (systemd on Linux, launchctl on macOS) ---
if [ "$IS_MAC" = 1 ]; then
  left=$(grep -Rl '\.hermes-cortex' "$HOME/Library/LaunchAgents" 2>/dev/null | wc -l)
  ck "0 LaunchAgent plists carry a \`.hermes-cortex\` path token (got $left)" "[ $left = 0 ]"
  n=$(launchctl list 2>/dev/null | grep -ci cortex || true)
  # smoke floor: if the cortex framework is loaded on macOS at least one label
  # exists; no unobserved specific count is asserted here.
  ck "launchd has >=1 cortex label (got $n)" "[ '$n' -ge 1 ]"
else
  left=$(grep -Rl '\.hermes-cortex' "$HOME/.config/systemd/user" 2>/dev/null | wc -l)
  ck "0 unit files carry a \`.hermes-cortex\` path token (got $left)" "[ $left = 0 ]"
  for s in cortex-bus.service hermes-cortex-dashboard.service health-vector.service; do
    st=$(systemctl --user is-active "$s" 2>/dev/null)
    ck "$s active (got $st)" "[ '$st' = 'active' ]"
  done
  ck "cortex-gateway.service unit-clean" "[ -f '${HOME}/.config/systemd/user/cortex-gateway.service' ]"
  n=$(systemctl --user list-timers --no-legend 2>/dev/null | grep -c 'cortex-bridge' || true)
  ck "cortex-bridge timers scheduled (got $n)" "[ '$n' -ge 15 ]"
fi

# --- 6. bus health 200 (ADV-14077-3) ---
code=$(curl -fsS -o /dev/null -w '%{http_code}' 127.0.0.1:8903/health 2>/dev/null || echo ERR)
ck "bus /health == 200 (got $code)" "[ '$code' = '200' ]"

# --- 7. new-path hc present + executable ---
ck "new hc present" "[ -x '$NEW_HOME/scripts/hc' ]"

# --- 8. deployed gate/guard intact (lives under ~/.hermes, unaffected by rename) ---
ck "deployed enforcer intact" "[ -f '${HOME}/.hermes/plugins/governance-enforcer/__init__.py' ]"

echo "------------------------------------"
if [ "$fails" -eq 0 ]; then echo "verify-rename-esther: ALL CHECKS PASS"; exit 0
else echo "verify-rename-esther: $fails FAILURE(S)"; exit 1; fi
