#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────────
# install-bridge-killmode.sh
#
# Keeps the bridge units' KillMode correct on every host that runs
# cortex-update.sh.
#
# A cortex-bridge-*.service unit is Type=oneshot, whose systemd default
# KillMode is control-group: when the tick's ExecStart exits, systemd
# tears down the unit cgroup and SIGTERMs any process the job detached
# (agent-message-handler.py spawns its UPDATE_REQUEST worker with
# start_new_session=True). Under control-group that worker dies seconds
# after spawn, so the fleet UPDATE_REQUEST protocol cannot update ANY
# host and every request answers only at the 30-minute sweep timeout.
# KillMode=process kills only the tick and lets detached children finish.
#
# The generator template sets KillMode=process on NEW units, but it can
# never reach a MIGRATED host: migration removes the job from
# ~/.hermes/jobs.json, so the generator never emits that unit again and
# the on-disk file can only be corrected in place (--repair).
#
# Both halves of the repair are done here, together, because either alone
# is a no-op:
#   1. cortex-bus-bridge-generate.py --repair   (rewrites the unit files)
#   2. systemctl --user daemon-reload           (makes the manager load
#      them — without the reload systemd keeps the OLD KillMode)
# and then the LOADED state is read back, because a rewritten file that
# the manager never re-read is not a repair.
#
# The predicate "which units still need the fix" is NOT re-implemented
# here: it comes from the generator's own unit_needs_killmode(), so this
# script cannot drift from the tool that performs the repair. Units that
# set an explicit KillMode are an operator override and are left alone.
#
# Scope: writes only the bridge unit files and the user manager's view of
# them. Idempotent — a host that is already correct skips the reload.
# Nothing is swallowed: a unit the repair could not fix, or that the
# manager still reports without KillMode=process, is named on stderr and
# exits non-zero (the caller in cortex-update.sh surfaces that as a
# warning and continues the deploy).
#
# Exit codes:
#   0  every bridge unit loads with KillMode=process (or none exists)
#   1  a bridge unit exists that is still not repaired/reloaded (named)
#   2  bridge units exist but the generator could not be located
#   3  the self-test itself could not run
#
# Usage:
#   bash install-bridge-killmode.sh             # apply (called by cortex-update.sh)
#   bash install-bridge-killmode.sh --self-test # prove this file in a temp dir
# ───────────────────────────────────────────────────────────────
set -euo pipefail

_self_test() {
  # Sandbox proof that travels with this file. Builds every fixture in a
  # private mktemp dir, puts a fake systemctl FIRST on PATH so no real
  # manager is ever addressed, and copies the real generator into the
  # fixture so the real repair code runs. Writes nothing outside the temp
  # dir, touches no live unit and no live config.
  local tmp
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/bridge-killmode-selftest.XXXXXX")" || {
    echo "self-test: could not create a temp dir" >&2
    return 3
  }
  trap '[[ -n "${tmp:-}" ]] && rm -rf "$tmp"' EXIT

  local bin="$tmp/bin" home="$tmp/home" deploy="$tmp/deploy"
  local units="$home/.config/systemd/user" log="$tmp/systemctl.log"
  mkdir -p "$bin" "$units" "$deploy/scripts"
  : > "$log"

  local gen_src
  gen_src="$(cd "$(dirname "$0")/.." && pwd)/cortex-bus-bridge-generate.py"
  if [[ ! -f "$gen_src" ]]; then
    echo "self-test: generator not beside this script ($gen_src)" >&2
    return 3
  fi
  cp "$gen_src" "$deploy/scripts/cortex-bus-bridge-generate.py"

  cat > "$bin/systemctl" <<'SHIM'
#!/usr/bin/env bash
# Fake systemctl for install-bridge-killmode.sh --self-test. Answers the
# two invocations the installer makes; records every call; never reaches
# the real user manager. `show` reports KillMode=process when the unit
# FILE has a KillMode line (the fake mirrors the file, so a repair that
# never landed is reported as not landed).
case "$*" in
  "--user daemon-reload")
    printf '%s\n' "$*" >> "$FAKE_SYSTEMCTL_LOG"
    exit "${FAKE_RELOAD_RC:-0}" ;;
  "--user show -p KillMode --value "*)
    printf '%s\n' "$*" >> "$FAKE_SYSTEMCTL_LOG"
    if grep -q 'KillMode' "$FAKE_UNITS_DIR/${!#}" 2>/dev/null; then
      echo process
    else
      echo control-group
    fi
    exit 0 ;;
esac
printf '%s\n' "$*" >> "$FAKE_SYSTEMCTL_LOG"
exit 0
SHIM
  chmod +x "$bin/systemctl"

  local failures=0
  local out="" rc=0

  _check() { # name expected actual
    if [[ "$2" == "$3" ]]; then
      echo "PASS $1"
    else
      echo "FAIL $1: expected [$2] got [$3]"
      failures=$((failures + 1))
    fi
  }
  _reloads() { # count of daemon-reload calls recorded so far
    local n
    n="$(grep -c -- '--user daemon-reload' "$log" 2>/dev/null)" || n=0
    printf '%s\n' "$n"
  }
  _run() { # <reload_rc> -> sets out, rc
    rc=0
    out="$(HOME="$home" PATH="$bin:$PATH" \
           CORTEX_DEPLOY_HOME="$deploy" REPO_DIR="$tmp/no-repo" \
           FAKE_UNITS_DIR="$units" FAKE_SYSTEMCTL_LOG="$log" \
           FAKE_RELOAD_RC="$1" bash "$0" 2>&1)" || rc=$?
  }
  _unit() { # <name> — a bridge unit with no KillMode directive
    cat > "$units/$1" <<'UNIT'
[Service]
Type=oneshot
ExecStart=/bin/true
UNIT
  }
  _has() { grep -q -- "$2" "$1" 2>/dev/null && echo yes || echo no; }

  # ── Case 1: no bridge units — nothing to do, no reload ──────
  _run 0
  _check "no-units: exit 0" 0 "$rc"
  _check "no-units: no reload" 0 "$(_reloads)"

  # ── Case 2: a unit without KillMode is repaired and reloaded ─
  _unit cortex-bridge-demo-a.service
  _run 0
  _check "repair: exit 0" 0 "$rc"
  _check "repair: file fixed" yes "$(_has "$units/cortex-bridge-demo-a.service" 'KillMode=process')"
  _check "repair: reloaded once" 1 "$(_reloads)"
  _check "repair: reports the verified read-back" yes \
    "$(grep -q 'verified — 1 repaired unit' <<<"$out" && echo yes || echo no)"

  # ── Case 3: idempotent — a correct host does not reload ─────
  : > "$log"
  _run 0
  _check "idempotent: exit 0" 0 "$rc"
  _check "idempotent: no reload" 0 "$(_reloads)"
  _check "idempotent: exactly one KillMode line" 1 \
    "$(grep -c 'KillMode=process' "$units/cortex-bridge-demo-a.service")"

  # ── Case 4: an explicit operator override is left alone ─────
  cat > "$units/cortex-bridge-demo-b.service" <<'UNIT'
[Service]
Type=oneshot
KillMode=control-group
ExecStart=/bin/true
UNIT
  : > "$log"
  _run 0
  _check "override: exit 0" 0 "$rc"
  _check "override: file untouched" yes "$(_has "$units/cortex-bridge-demo-b.service" 'KillMode=control-group')"
  _check "override: no reload" 0 "$(_reloads)"
  rm -f "$units/cortex-bridge-demo-b.service"

  # ── Case 5: a unit the repair cannot fix exits non-zero ─────
  printf '%s\n' '[Unit]' 'Description=unrepairable' > "$units/cortex-bridge-demo-c.service"
  : > "$log"
  _run 0
  _check "unrepairable: exit 1" 1 "$rc"
  _check "unrepairable: names the unit" yes "$(grep -q 'cortex-bridge-demo-c.service' <<<"$out" && echo yes || echo no)"
  rm -f "$units/cortex-bridge-demo-c.service"

  # ── Case 6: a failed daemon-reload exits non-zero ───────────
  _unit cortex-bridge-demo-d.service
  : > "$log"
  _run 1
  _check "reload-fails: exit 1" 1 "$rc"
  _check "reload-fails: reports the failed reload" yes \
    "$(grep -q "daemon-reload' failed" <<<"$out" && echo yes || echo no)"

  if [[ $failures -gt 0 ]]; then
    echo "self-test: $failures case(s) FAILED" >&2
    return 1
  fi
  echo "self-test: all cases PASS"
  return 0
}

if [[ "${1:-}" == "--self-test" ]]; then
  _self_test
  exit $?
fi

HOME_DIR="${HOME:?}"
CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME:-${HOME_DIR}/.hermes-cortex}"
REPO_DIR="${REPO_DIR:-${HOME_DIR}/hermes-cortex}"
UNITS_DIR="${HOME_DIR}/.config/systemd/user"

# Only a Linux host runs user systemd units; elsewhere there is nothing to
# repair and no manager to reload (macOS hosts have no bridge units).
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "install-bridge-killmode: not Linux — no user-systemd bridge — skipped"
  exit 0
fi

shopt -s nullglob
bridge_units=("${UNITS_DIR}"/cortex-bridge-*.service)
shopt -u nullglob
if [[ ${#bridge_units[@]} -eq 0 ]]; then
  echo "install-bridge-killmode: no bridge units in ${UNITS_DIR} — nothing to repair"
  exit 0
fi

GEN="${CORTEX_DEPLOY_HOME}/scripts/cortex-bus-bridge-generate.py"
[[ -f "$GEN" ]] || GEN="${REPO_DIR}/ops/scripts/cortex-bus-bridge-generate.py"
if [[ ! -f "$GEN" ]]; then
  echo "install-bridge-killmode: ${#bridge_units[@]} bridge unit(s) present but no cortex-bus-bridge-generate.py — cannot repair" >&2
  exit 2
fi

# Names of the units that still need the fix, from the generator's OWN
# predicate (unit_needs_killmode) — one implementation, no second matcher
# to drift. Empty output = nothing to repair.
needing="$(python3 - "$GEN" <<'PY'
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("cortex_bus_bridge_generate", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
units = sorted(mod._UNITS.glob(f"{mod._PREFIX}*.service")) if mod._UNITS.is_dir() else []
for path in units:
    try:
        text = path.read_text()
    except OSError:
        # Unreadable is reported by --repair (which exits non-zero); here it
        # is simply not counted as "needs the fix".
        continue
    if mod.unit_needs_killmode(text):
        print(path.name)
PY
)"

if [[ -z "$needing" ]]; then
  echo "install-bridge-killmode: all ${#bridge_units[@]} bridge unit(s) already load KillMode=process — no reload needed"
  exit 0
fi

n_needing="$(printf '%s\n' "$needing" | grep -c .)"
echo "install-bridge-killmode: ${n_needing} of ${#bridge_units[@]} bridge unit(s) lack KillMode — repairing"

repair_rc=0
repair_out="$(python3 "$GEN" --repair 2>&1)" || repair_rc=$?
printf '%s\n' "$repair_out"
if [[ $repair_rc -ne 0 ]]; then
  echo "install-bridge-killmode: generator --repair failed (rc=$repair_rc) — units above are still wrong" >&2
  exit 1
fi

SYSTEMCTL="$(command -v systemctl || true)"
if [[ -z "$SYSTEMCTL" ]]; then
  echo "install-bridge-killmode: systemctl not found — the ${n_needing} repaired unit(s) stay unloaded until a reload" >&2
  exit 1
fi

if ! "$SYSTEMCTL" --user daemon-reload; then
  echo "install-bridge-killmode: 'systemctl --user daemon-reload' failed — the repaired units are not loaded" >&2
  exit 1
fi

# Read back the LOADED state of exactly the units that changed: the file
# rewrite alone is not the fix (the manager keeps the old KillMode until
# the reload), so this is the measurement, not a restatement of the write.
still=""
while IFS= read -r unit; do
  [[ -n "$unit" ]] || continue
  mode="$("$SYSTEMCTL" --user show -p KillMode --value "$unit" 2>/dev/null || true)"
  [[ "$mode" == "process" ]] || still="${still}${unit}(KillMode=${mode:-<unreadable>}) "
done <<< "$needing"

if [[ -n "$still" ]]; then
  echo "install-bridge-killmode: FAILED — still not KillMode=process after reload: ${still}" >&2
  exit 1
fi

echo "install-bridge-killmode: verified — ${n_needing} repaired unit(s) now load KillMode=process"
exit 0
