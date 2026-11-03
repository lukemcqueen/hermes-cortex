#!/usr/bin/env bash
# verify-rename-esther.sh — live golden-path verification for the local-dir
# rename (esther dogfood, cycle 14077, ADV-14077-2/3). Exits non-zero on the
# first broken check. Run from a stable workdir AFTER
# migrate-home-dirs.sh + unit regeneration.
set -uo pipefail

NEW_REPO="${HOME}/steadfaste-fleet"       # repo checkout
NEW_HOME="${HOME}/.steadfaste-fleet"      # deployed home (CORTEX_DEPLOY_HOME)
OLD_REPO="${HOME}/hermes-cortex"
OLD_HOME="${HOME}/.hermes-cortex"

fails=0
ck(){ if eval "$2"; then echo "PASS: $1"; else echo "FAIL: $1"; fails=$((fails+1)); fi; }

# --- 1. transition symlinks resolve to new dirs ---
ck "old-repo symlink -> new" "[ -L '$OLD_REPO' ] && [ \"$(readlink '$OLD_REPO')\" = '$NEW_REPO' ]"
ck "old-home symlink -> new" "[ -L '$OLD_HOME' ] && [ \"$(readlink '$OLD_HOME')\" = '$NEW_HOME' ]"
ck "new-repo is a real dir" "[ -d '$NEW_REPO' ]"
ck "new-home is a real dir" "[ -d '$NEW_HOME' ]"

# --- 2. brain/mycortex preserved at the new path ---
ck "brain/kb present" "[ -d '$NEW_HOME/brain/kb' ]"
ck "brain/memories present" "[ -d '$NEW_HOME/brain/memories' ]"
ck "mycortex compose present" "[ -f '$NEW_HOME/docker-compose.mycortex.yml' ]"

# --- 3. no residual old path in generated systemd user units (ADV-14077-2) ---
left=$(grep -Rl '\.hermes-cortex' "$HOME/.config/systemd/user" 2>/dev/null | wc -l)
ck "0 unit files still carry ~/.hermes-cortex (got $left)" "[ '$left' = '0' ]"

# --- 4. key services active ---
for s in cortex-bus.service cortex-gateway.service hermes-cortex-dashboard.service health-vector.service; do
  st=$(systemctl --user is-active "$s" 2>/dev/null)
  ck "$s active (got $st)" "[ '$st' = 'active' ]"
done

# --- 5. timers still scheduled ---
n=$(systemctl --user list-timers --no-legend 2>/dev/null | grep -c 'cortex-bridge' || true)
ck "cortex-bridge timers scheduled (got $n)" "[ '$n' -ge 15 ]"

# --- 6. bus health 200 (ADV-14077-3) ---
code=$(curl -fsS -o /dev/null -w '%{http_code}' 127.0.0.1:8903/health 2>/dev/null || echo ERR)
ck "bus /health == 200 (got $code)" "[ '$code' = '200' ]"

# --- 7. new-path hc present + executable ---
ck "new hc present" "[ -x '$NEW_HOME/scripts/hc' ]"

# --- 8. deployed gate/guard moved (spot) ---
ck "deployed enforcer moved" "[ -f '$NEW_HOME/plugins/governance-enforcer/__init__.py' ]"

echo "------------------------------------"
if [ "$fails" -eq 0 ]; then echo "verify-rename-esther: ALL CHECKS PASS"; exit 0
else echo "verify-rename-esther: $fails FAILURE(S)"; exit 1; fi
