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

# --- 2. brain/mycortex preserved (per-host location: a host may keep its brain
#        at the renamed home ~/.steadfaste-fleet/brain, OR under the Hermes home
#        ~/.hermes/brain — the latter is NOT renamed and is untouched by the
#        migration, so verify whichever the host actually uses) ---
BRAIN_A="$NEW_HOME/brain"; BRAIN_B="${HOME}/.hermes/brain"
BRAIN_DIR=""
if [ -d "$BRAIN_A" ]; then BRAIN_DIR="$BRAIN_A"; elif [ -d "$BRAIN_B" ]; then BRAIN_DIR="$BRAIN_B"; fi
ck "brain dir present (resolved: ${BRAIN_DIR:-none})" "[ -n '$BRAIN_DIR' ]"
ck "brain/kb present" "[ -d '${BRAIN_DIR}/kb' ]"
ck "brain/memories present" "[ -d '${BRAIN_DIR}/memories' ]"
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
