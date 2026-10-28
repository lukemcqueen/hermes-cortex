#!/usr/bin/env bash
# Re-runnable proof that the Jev routing notice appears when a model is SWITCHED, and
# that the `notice` switch in state.json is what controls it.
#
# Drives the INSTALLED plugin's own decision + transform_output path. HERMES_HOME is
# repointed at a scratch dir inside the probe, so the live state.json and the live
# decisions log are never read for state nor written to.
#
# Usage: bash docs/evidence/jev-notice-2026-10-28/run.sh
# Exit:  0 all assertions held, 1 an assertion failed, 3 a precondition was missing.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PLUGIN="${HERMES_HOME:-$HOME/.hermes}/plugins/hermes-jev/__init__.py"
PY="${JEV_PYTHON:-python3}"

command -v "$PY" >/dev/null 2>&1 || { echo "python3 not found" >&2; exit 3; }
[ -f "$PLUGIN" ] || { echo "hermes-jev plugin not installed at $PLUGIN" >&2; exit 3; }

OUT="$HERE/transcript.txt"
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/jev-notice-XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT

# A stale TYPESAFE_BASE_URL export would point the probe at a dead stub and produce a
# fail-open "kept" decision that looks like a routing bug. Drop both overrides.
env -u TYPESAFE_BASE_URL -u JEV_PROXY_API_KEY \
    JEV_PROBE_HOME="$SCRATCH" "$PY" "$HERE/notice_probe.py" > "$OUT" 2>&1
rc=$?
cat "$OUT"

echo
fail=0
check() { # check <description> <pattern>
    if grep -qF "$2" "$OUT"; then
        echo "  ✅ $1"
    else
        echo "  ❌ $1 — expected to find: $2"
        fail=1
    fi
}
check "notice=on renders the footer for a switched model" \
      "[Jev] simple · general → qwen/qwen3.7-flash · confidence 1.00"
check "notice=off renders NO footer for the SAME decision" \
      "reply ends with: 'Here is the change you asked for.'"
# The confidence is a live model judgement and moves between runs (0.79, 0.81, ...), so
# the assertion stops at the part that is stable: the tier, the specialty and the model.
check "the hard whitelist head is reachable and named in the notice" \
      "[Jev] hard · coding → deepseek/deepseek-v4-pro-0813 · confidence 0."
check "the decision log records the switch" \
      "'routed': True, 'tier': 'simple'"
[ "$rc" -eq 0 ] || { echo "  ❌ the probe itself exited $rc"; fail=1; }

echo
if [ "$fail" -eq 0 ]; then
    echo "VERDICT: the notice works and state.json controls it (4/4)"
else
    echo "VERDICT: FAILED — see the ❌ lines above"
fi
exit "$fail"
