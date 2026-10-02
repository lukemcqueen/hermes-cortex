#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# audit-pi-integration.sh — verify the Pi ⇄ Hermes Cortex integration on THIS host.
#
# WHY VERSION-AWARE. The integration has TWO routes and the correct checks differ:
#
#   MCP route    Pi >= 0.99 — an MCP client. Four cortex servers (loop-governance,
#                tasks, executor, agent-bus) via ~/.pi/agent/mcp.json.
#   HOOKS route  Pi <  0.99 (the shipped 0.87.1 has NO MCP client) — governance and
#                the cortex tools arrive through the git hooks + ops/scripts/loop-gov.py.
#
# Auditing with the MCP checklist on a 0.87.1 host reports FAIL on a healthy install,
# so an agent ends up chasing an impossible PASS. Detect the route first, then check
# only what that route requires; report the other as NA with the reason.
# Do NOT infer MCP support from `pi mcp list` (the harness registry warns about that).
#
# Usage:  audit-pi-integration.sh [--json]
# Exit:   0 = every layer required on this host is PASS (NA is not a failure)
#         1 = at least one required layer FAILED
# ─────────────────────────────────────────────────────────────
set -u

JSON_MODE=0
[[ "${1:-}" == "--json" ]] && JSON_MODE=1

PI_DIR="${PI_DIR:-$HOME/.pi/agent}"
SETTINGS="$PI_DIR/settings.json"
MCP_JSON="$PI_DIR/mcp.json"
SKILLS_LINKS="$PI_DIR/cortex-skills"
AGENT_ENV="$HOME/.hermes-cortex/agent.env"
DEPLOY="${CORTEX_DEPLOY_HOME:-$HOME/.hermes-cortex}"
MANIFEST="${CORTEX_SKILLS_MANIFEST:-}"

_fail=0
_line() {  # _line <layer> <PASS|FAIL|NA> <text>
  [[ "$JSON_MODE" == "1" ]] && return 0
  local mark="✅"
  [[ "$2" == "FAIL" ]] && mark="❌"
  [[ "$2" == "NA" ]] && mark="➖"
  printf '  %s %-9s %s\n' "$mark" "$2" "$3"
}
_failed() {  # record a required failure
  _fail=1
  _line "$1" FAIL "$2"
}

# ── route detection ──
PI_BIN="$(command -v pi 2>/dev/null || true)"
PI_VER=""
MCP_CAPABLE=0
if [[ -n "$PI_BIN" ]]; then
  PI_VER="$(pi --version 2>/dev/null | head -1 | tr -d '[:space:]')"
  # The registry's method: the CLI's own help is the signal, not `pi mcp list`.
  if pi --help 2>/dev/null | grep -qiE '(^|[^a-z])mcp([^a-z]|$)'; then MCP_CAPABLE=1; fi
fi

[[ "$JSON_MODE" == "1" ]] || echo "Pi integration audit — ${PI_BIN:-pi not installed}${PI_VER:+ (v$PI_VER)}"

# ── Layer 1: MCP servers (route-dependent) ──
if [[ -z "$PI_BIN" ]]; then
  _failed 1 "Pi is not installed on this host (no 'pi' on PATH) — nothing to integrate. Install: npm install -g @earendil-works/pi-coding-agent (see the pi-coding-agent skill)"
elif [[ "$MCP_CAPABLE" == "1" ]]; then
  if [[ ! -f "$MCP_JSON" ]]; then
    _failed 1 "MCP-capable Pi but $MCP_JSON is missing — run install-pi-mcp.sh"
  else
    missing=""
    for s in loop-governance tasks executor agent-bus; do
      grep -q "\"$s\"" "$MCP_JSON" || missing="$missing $s"
    done
    if [[ -n "$missing" ]]; then
      _failed 1 "mcp.json is missing server(s):$missing — run install-pi-mcp.sh"
    else
      srv_missing=""
      for f in "$DEPLOY/tools/loop-governance/loop-gov-mcp.py" "$DEPLOY/scripts/task-mcp.py" \
               "$DEPLOY/scripts/executor-mcp.py" "$DEPLOY/scripts/cortex-bus-mcp.py"; do
        [[ -f "$f" ]] || srv_missing="$srv_missing $(basename "$f")"
      done
      if [[ -n "$srv_missing" ]]; then
        _failed 1 "mcp.json lists 4 servers but the deployed files are missing:$srv_missing — run cortex-update.sh"
      else
        _line 1 PASS "4 servers configured and deployed (loop-governance, tasks, executor, agent-bus)"
      fi
    fi
  fi
else
  _line 1 NA "Pi v${PI_VER:-?} has no MCP client — governance arrives via the git hooks + loop-gov.py (registry: MCP needs >= 0.99)"
  if [[ -x "$DEPLOY/scripts/loop-gov.py" ]] || [[ -f "$(git rev-parse --show-toplevel 2>/dev/null)/ops/scripts/loop-gov.py" ]]; then
    _line 1 PASS "hooks route available (loop-gov.py present)"
  else
    _failed 1 "no MCP client AND no loop-gov.py — this host has no governance route"
  fi
fi

# ── Layer 2: curated always-skills ──
if [[ ! -f "$SETTINGS" ]]; then
  _failed 2 "$SETTINGS missing — run install-pi-integration.sh"
else
  missing_keys=""
  for k in extensions skills; do
    grep -q "\"$k\"" "$SETTINGS" || missing_keys="$missing_keys $k"
  done
  if [[ -n "$missing_keys" ]]; then
    _failed 2 "settings.json lacks key(s):$missing_keys — run install-pi-integration.sh"
  else
    # The curated list comes from the skills MANIFEST (`always:`), never hardcoded here.
    WANT=""
    for m in "$MANIFEST" "$HOME/.hermes-cortex/skills.yaml" "${CORTEX_REPO:-$HOME/hermes-cortex}/skills.yaml"; do
      [[ -n "$m" && -f "$m" ]] || continue
      WANT="$(awk '/^always:/{f=1;next} /^[a-z]/{f=0} f && /- name:/{sub(/.*- name:[ ]*/,""); print}' "$m")"
      break
    done
    if [[ -z "$WANT" ]]; then
      _line 2 NA "no skills manifest found (skills.yaml) — cannot verify the curated set"
    else
      link_missing=""
      for s in $WANT; do
        [[ -e "$SKILLS_LINKS/$s" ]] || link_missing="$link_missing $s"
      done
      n=$(echo "$WANT" | wc -w | tr -d ' ')
      if [[ -n "$link_missing" ]]; then
        _failed 2 "$SKILLS_LINKS is missing curated skill(s):$link_missing — run install-pi-integration.sh"
      else
        _line 2 PASS "$n/$n curated skills linked in $SKILLS_LINKS, settings.json carries extensions+skills"
      fi
    fi
  fi
fi

# ── Layer 3: session/memory extension ──
EXT_OK=0
for c in "$DEPLOY/harnesses/pi/extensions/cortex-context.ts" \
         "${CORTEX_REPO:-$HOME/hermes-cortex}/ops/install/harnesses/pi/extensions/cortex-context.ts"; do
  [[ -f "$c" ]] && EXT_OK=1 && break
done
if [[ "$EXT_OK" == "1" ]]; then
  _line 3 PASS "cortex-context extension present (native mem_*/session_* tools are visible to the agent itself)"
else
  _failed 3 "cortex-context.ts not found (deployed or repo) — run cortex-update.sh"
fi

# ── Layer 4: governance wiring ──
if [[ -f "$DEPLOY/tools/loop-governance/loop-gov-mcp.py" ]]; then
  _line 4 PASS "loop-governance gate deployed (a cycle test is the agent's own check: begin_change -> feedback_accept -> end_change)"
else
  _failed 4 "loop-governance gate not deployed at $DEPLOY/tools/loop-governance/ — run cortex-update.sh"
fi

# ── Layer 5: failsafes ──
if [[ -f "$AGENT_ENV" ]] && grep -qE '^AGENT_NAME=.+' "$AGENT_ENV"; then
  name="$(grep -E '^AGENT_NAME=' "$AGENT_ENV" | head -1 | cut -d= -f2)"
  _line 5 PASS "AGENT_NAME=$name"
else
  _failed 5 "AGENT_NAME not set in $AGENT_ENV (bus identity + governance attribution need it)"
fi
# The Hermes venv is a PREFERENCE: install-pi-mcp.sh falls back to PATH python3 if the
# MCP extra is importable there. Reporting it as a hard failure would be wrong.
if [[ -x "$HOME/.hermes/hermes-agent/venv/bin/python3" ]]; then
  _line 5 PASS "Hermes venv python present (install-pi-mcp.sh prefers it)"
else
  _line 5 NA "no Hermes venv — install-pi-mcp.sh falls back to python3 on PATH (fine if 'mcp' is importable there)"
fi

[[ "$JSON_MODE" == "1" ]] && printf '{"layer_failures":%s}\n' "$_fail"
[[ "$JSON_MODE" == "1" ]] || {
  echo
  if [[ "$_fail" == "0" ]]; then echo "  RESULT: PASS (every layer required on this host)"; else echo "  RESULT: FAIL (remediation above)"; fi
}
exit "$_fail"
