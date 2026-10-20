#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# audit-pi-integration.sh — verify the Pi ⇄ Hermes Cortex integration on THIS host.
#
# WHY VERSION-AWARE. The integration has TWO routes and the correct checks differ:
#
#   MCP route    Pi >= 0.99 — an MCP client. Five cortex servers (loop-governance,
#                tasks, executor, agent-bus, cortex-context) via ~/.pi/agent/mcp.json.
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
# Pi is a MANAGED install (see the pi-coding-agent skill): the entrypoint is a symlink
# into the user's bin dir, which may not be on PATH, so `command -v pi` reports a
# perfectly working install as missing. Try the launcher first, then PATH.
PI_BIN=""
for cand in "$HOME/.pi/agent/bin/pi" "$(command -v pi 2>/dev/null || true)"; do
  [[ -n "$cand" && -x "$cand" ]] && PI_BIN="$cand" && break
done
PI_VER=""
MCP_CAPABLE=0
if [[ -n "$PI_BIN" ]]; then
  # current-version is authoritative and needs no execution; fall back to the CLI.
  _cv="$HOME/.pi/agent/install/current-version"
  if [[ -r "$_cv" ]]; then
    PI_VER="$(head -1 "$_cv" | tr -d '[:space:]')"
  else
    PI_VER="$("$PI_BIN" --version 2>/dev/null | head -1 | tr -d '[:space:]')"
  fi
  # The registry's method: the CLI's own help is the signal, not `pi mcp list`.
  if "$PI_BIN" --help 2>/dev/null | grep -qiE '(^|[^a-z])mcp([^a-z]|$)'; then MCP_CAPABLE=1; fi
fi

[[ "$JSON_MODE" == "1" ]] || echo "Pi integration audit — ${PI_BIN:-pi not installed}${PI_VER:+ (v$PI_VER)}"

# ── Layer 1: MCP servers (route-dependent) ──
if [[ -z "$PI_BIN" ]]; then
  _failed 1 "Pi is not installed on this host (no 'pi' on PATH) — nothing to integrate. Install: npm install -g @earendil-works/pi-coding-agent (see the pi-coding-agent skill)"
elif [[ "$MCP_CAPABLE" == "1" ]]; then
  if [[ ! -f "$MCP_JSON" ]]; then
    _failed 1 "MCP-capable Pi but $MCP_JSON is missing — run install-pi-mcp.sh"
  else
    # ONE source of truth for the required set: this loop and the PASS line both
    # read REQUIRED, so a server can never be required without being reported. The
    # old "4 servers configured" line outlived cortex-context's 2026-10-03
    # deployment precisely because the set was written out twice — a loop that
    # checked four names and a sentence that claimed four of them.
    REQUIRED="loop-governance tasks executor agent-bus cortex-context"
    missing=""
    for s in $REQUIRED; do
      grep -q "\"$s\"" "$MCP_JSON" || missing="$missing $s"
    done
    if [[ -n "$missing" ]]; then
      _failed 1 "mcp.json is missing server(s):$missing — run install-pi-mcp.sh"
    else
      srv_missing=""
      for f in "$DEPLOY/tools/loop-governance/loop-gov-mcp.py" "$DEPLOY/scripts/task-mcp.py" \
               "$DEPLOY/scripts/executor-mcp.py" "$DEPLOY/scripts/cortex-bus-mcp.py" \
               "$DEPLOY/scripts/cortex-context-mcp.py"; do
        [[ -f "$f" ]] || srv_missing="$srv_missing $(basename "$f")"
      done
      if [[ -n "$srv_missing" ]]; then
        _failed 1 "mcp.json requires ${REQUIRED// /, } but the deployed files are missing:$srv_missing — run cortex-update.sh"
      else
        # Presence of a name is not a working server: verify each entry actually points
        # at a runnable command, an existing script, and THIS agent's name (a stale or
        # copied-in mcp.json can look complete and hand the agent another agent's bus
        # identity).
        # PLAIN REDIRECT, never `$( ... <<PY )`: a heredoc inside a command
        # substitution is a bash 3.2 parser trap (macOS).
        _ENTRY_ISSUES_RAW_TMP="$(mktemp "${TMPDIR:-/tmp}/cortex-audit.XXXXXX" 2>/dev/null || echo "${TMPDIR:-/tmp}/cortex-audit.$$")"
        MCP_JSON="$MCP_JSON" AGENT_ENV="$AGENT_ENV" REQUIRED="$REQUIRED" python3 - <<'PY' >"$_ENTRY_ISSUES_RAW_TMP"
import json, os, shutil
from pathlib import Path
d = json.loads(Path(os.environ["MCP_JSON"]).read_text())
srv = d.get("mcpServers") or d.get("servers") or {}
want = ""
env_path = Path(os.environ["AGENT_ENV"])
if env_path.exists():
    for ln in env_path.read_text().splitlines():
        if ln.startswith("AGENT_NAME="):
            want = ln.split("=", 1)[1].strip()
# The AGENT_NAME rule is the CORTEX contract, so it is applied to the servers this
# audit OWNS and to nothing else: a host-local foreign server (no env, no cortex
# semantics) judged by it makes a healthy host report FAIL — measured 2026-10-12 on a
# hand-registered DeepSeek adversarial-review entry sitting beside the five cortex
# ones. Its command and script ARE still checked: a broken path is a real defect, and
# scoping the identity rule must not make the audit blind.
required = set((os.environ.get("REQUIRED") or "").split())
issues, foreign = [], []
for name, cfg in srv.items():
    cfg = cfg or {}
    cmd = cfg.get("command", "")
    args = cfg.get("args") or []
    if not cmd or not (Path(cmd).exists() or shutil.which(cmd)):
        issues.append(f"{name}: command not runnable ({cmd or 'none'})")
    if not args or not Path(str(args[0])).exists():
        issues.append(f"{name}: script missing ({args[0] if args else 'none'})")
    if name not in required:
        foreign.append(name)
        continue
    got = (cfg.get("env") or {}).get("AGENT_NAME", "")
    if want and got != want:
        issues.append(f"{name}: AGENT_NAME={got or 'unset'} (host is {want!r})")
print("; ".join(issues))
print(",".join(sorted(foreign)))
PY
        # An AUDIT must not read a crashed parser as "no issues": capture the status and
        # report the failure explicitly. (`_failed` is this script's own failure channel.)
        _ei_rc=$?
        entry_issues_raw="$(cat "$_ENTRY_ISSUES_RAW_TMP" 2>/dev/null)"
        rm -f "$_ENTRY_ISSUES_RAW_TMP"
        if [[ $_ei_rc -ne 0 ]]; then
            # rc is the ONLY failure signal here: the parser always prints two join lines
            # (issues, foreign), so a HEALTHY host legitimately yields an EMPTY string —
            # command substitution strips the two empty lines' newlines. Gating on `-z`
            # inverted that and failed a healthy host (caught by running the audit).
            # A non-zero rc means the parser itself died: no verdict is not a pass, and
            # parsing its output would invent a clean result — record it and stop here.
            _failed 6 "the mcp.json entry audit could not run (parser exited $_ei_rc) — this check produced NO verdict, which is not the same as 'no issues'"
            entry_issues_raw=""
            _entry_audit_failed=1
        fi
        # Line 1 is the issues, line 2 the foreign servers — two facts, one subprocess.
        if [[ "${_entry_audit_failed:-0}" -eq 1 ]]; then
            :   # nothing to parse — the failure above is the verdict
        else
        entry_issues="${entry_issues_raw%%$'\n'*}"
        foreign_servers="$(printf '%s\n' "$entry_issues_raw" | sed -n '2p')"
        if [[ -n "$entry_issues" ]]; then
          _failed 1 "MCP entries are not fully usable: $entry_issues"
        else
          agent_name="$(grep -E '^AGENT_NAME=' "$AGENT_ENV" 2>/dev/null | head -1 | cut -d= -f2)"
          _line 1 PASS "cortex servers present and runnable: ${REQUIRED// /, } — AGENT_NAME=${agent_name:-?} on every entry"
          # The audit prints only what it MEASURED. It cannot count another server's
          # tools (that needs a live MCP session), so it asserts no number: the old
          # "4 servers / 46 tools" line was a hardcoded claim that stayed stale for
          # weeks — tasks exposes 14, not 13, and cortex-context's 12 were missing
          # from it entirely. Live counts belong in a transcript, beside the command
          # that produced them, not in an assertion this script cannot check.
          _line 1 PASS "live check (agent, in a Pi session): 'pi mcp list' → every cortex server should report 'connected' (no tool count is asserted here: this audit cannot measure one)"
          # A foreign entry is REPORTED, never judged: it is not a cortex server, so
          # the audit neither requires nor forbids it — but a reader must be able to
          # tell "not audited" from "audited and fine".
          if [[ -n "$foreign_servers" ]]; then
            _line 1 NA "host-local server(s) present, NOT audited here (no cortex identity expected): ${foreign_servers//,/ }"
          fi
        fi
        fi   # end: skip parsing entirely when the entry audit itself failed
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
# The cortex venv is a PREFERENCE: install-pi-mcp.sh falls back to PATH python3 if the
# MCP extra is importable there. Reporting it as a hard failure would be wrong.
if [[ -x "$HOME/.hermes-cortex/venv/bin/python3" ]]; then
  _line 5 PASS "cortex venv python present (install-pi-mcp.sh prefers it)"
else
  _line 5 NA "no cortex venv — install-pi-mcp.sh falls back to python3 on PATH (fine if 'mcp' is importable there)"
fi

# ── Layer 6: web search (free providers) ──
# Without this the pi agent has NO online path at all: pi's built-in tools are
# local (read/bash/edit/write/grep/find/ls) and the five cortex MCP servers
# expose no search, so "research this" / "review this repo" fails with an error
# that reads like a broken tool instead of a missing package. Both halves are
# checked because either alone is inert: a DECLARATION with nothing on disk
# loads no extension, and an INSTALL with no config finds no provider.
# Required only where pi is — a host with no coding agent is not a fault.
if [[ -z "$PI_BIN" ]]; then
  _line 6 NA "no pi on this host — web search not applicable"
elif [[ ! -f "$SETTINGS" ]]; then
  _failed 6 "$SETTINGS missing — run install-pi-integration.sh"
else
  WS_JSON="$HOME/.pi/agent/web-search.json"
  PKG_INSTALLED="$HOME/.pi/agent/npm/node_modules/pi-web-access"
  if ! grep -q '"npm:pi-web-access' "$SETTINGS"; then
    _failed 6 "no pi-web-access package declared in $SETTINGS — the agent has no web tool. Run install-pi-integration.sh"
  elif [[ ! -d "$PKG_INSTALLED" ]]; then
    _failed 6 "pi-web-access declared but NOT installed ($PKG_INSTALLED absent) — pi loads no extension. Run install-pi-integration.sh"
  else
    # The verdict comes from the CONFIG, parsed rather than grepped: a keyed-only
    # chain is valid for its owner and useless on a host with no keys, and a
    # substring match cannot tell the two apart.
    # PLAIN REDIRECT, never `$( ... <<PY )`: a heredoc inside a command
    # substitution is a bash 3.2 parser trap (macOS).
    _WS_VERDICT_TMP="$(mktemp "${TMPDIR:-/tmp}/cortex-audit.XXXXXX" 2>/dev/null || echo "${TMPDIR:-/tmp}/cortex-audit.$$")"
    WS_JSON="$WS_JSON" python3 - <<'PY' >"$_WS_VERDICT_TMP"
import json, os
p = os.environ["WS_JSON"]
if not os.path.exists(p):
    print("missing"); raise SystemExit
try:
    cfg = json.load(open(p))
except Exception:
    print("invalid"); raise SystemExit
routing = cfg.get("searchRouting") if isinstance(cfg, dict) else None
route = routing.get("providers", []) if isinstance(routing, dict) else []
chosen = [x for x in route if isinstance(x, str)] or [cfg.get("provider")]
keyless = [x for x in chosen if x in ("exa", "duckduckgo")]
print("keyless:" + ",".join(keyless) if keyless else "keyed-only")
PY
    _wv_rc=$?
    # Capture the READ's status on its own line: a vanished/unreadable tempfile is not the
    # parser failing, and reporting it as "check-failed" would misdiagnose the cause.
    # (An explicit capture beats testing `if VAR=$(cat ...)`, whose status is the
    # substitution's — correct, but easy for a reader to get backwards.)
    ws_verdict="$(cat "$_WS_VERDICT_TMP")"
    _wv_read_ok=$?
    rm -f "$_WS_VERDICT_TMP"
    if [[ $_wv_read_ok -ne 0 ]]; then   # $? is 0 on SUCCESS — -ne, not -eq
        _failed 6 "could not read the search-routing probe output (tempfile unreadable) — the check produced NO verdict"
        ws_verdict="check-failed"
    fi
    # An empty verdict is never a verdict: the parser can exit 0 having printed nothing,
    # and an empty string would fall through the case and read as a silent pass.
    if [[ $_wv_rc -ne 0 || -z "$ws_verdict" ]]; then
        ws_verdict="check-failed"
    fi
    # The parser above prints EXACTLY one of these, so every one needs an arm:
    #   missing | invalid | keyless:<providers> | keyed-only     (plus check-failed below,
    # set when the parser itself died or its output could not be read).
    case "$ws_verdict" in
      check-failed)
        _failed 6 "the search-routing verdict could not be computed (parser failed) — NO verdict is not a pass"
        ;;
      keyless:*)
        _line 6 PASS "pi-web-access installed; keyless search path ${ws_verdict#keyless:} (no API key needed)"
        ;;
      keyed-only)
        _failed 6 "$WS_JSON names no keyless provider (exa/duckduckgo) — every search fails on a host with no API key. Fix: install-pi-integration.sh writes the keyless chain when the file is absent; keep a keyed chain only if you intend to pay for it"
        ;;
      invalid)
        _failed 6 "$WS_JSON is not valid JSON — the search tool cannot read its own config"
        ;;
      *)
        _failed 6 "$WS_JSON missing — the search tool has no provider chain. Run install-pi-integration.sh"
        ;;
    esac
  fi
fi

[[ "$JSON_MODE" == "1" ]] && printf '{"layer_failures":%s}\n' "$_fail"
[[ "$JSON_MODE" == "1" ]] || {
  echo
  if [[ "$_fail" == "0" ]]; then echo "  RESULT: PASS (every layer required on this host)"; else echo "  RESULT: FAIL (remediation above)"; fi
}
exit "$_fail"
