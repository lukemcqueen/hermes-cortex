#!/usr/bin/env bash
# The fleet launcher must find its module in BOTH layouts it is installed in - beside it in
# the deployment (scripts/fleet + scripts/fleet.py) and ONE LEVEL UP in the repo
# (ops/scripts/fleet/bin/fleet + ops/scripts/fleet/fleet.py) - and must refuse with 3 rather
# than run some other tree's module when neither is there.
#
# Why this test exists: the launcher used to resolve ${SCRIPT_DIR}/hc.py only, so moving it
# into bin/ would have silently fallen through to the known-path fallback and run a module
# from an unrelated tree. A stub module makes WHICH fleet.py answered observable, and every
# path here is fixture-local, so this runs on any host.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO/ops/scripts/fleet/bin/fleet"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/fleet-launcher.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
fails=0
pass() { echo "  ✓ $1"; }
fail() { echo "  ✗ $1"; fails=$((fails + 1)); }

# A module that identifies itself: which fleet.py ran, and with what args.
stub() {
    printf '#!/usr/bin/env python3\nimport sys\nprint("MODULE=" + __file__)\nprint("ARGS=" + " ".join(sys.argv[1:]))\n' > "$1"
}

if [ ! -f "$SRC" ]; then
    echo "  ✗ launcher source not found at $SRC" >&2
    exit 1
fi

# --- deployed layout: the module sits BESIDE the launcher
mkdir -p "$TMP/deploy"
cp "$SRC" "$TMP/deploy/fleet"
stub "$TMP/deploy/fleet.py"
out="$(bash "$TMP/deploy/fleet" harness verify pi 2>&1)"; rc=$?
if [ $rc -eq 0 ] && printf '%s\n' "$out" | grep -q "MODULE=.*/deploy/fleet\.py$"; then
    pass "module beside the launcher resolves (rc=0)"
else
    fail "module beside the launcher: rc=$rc out=[$out]"
fi

# --- repo layout: the launcher is in bin/, so the module is one level up
mkdir -p "$TMP/repo/bin"
cp "$SRC" "$TMP/repo/bin/fleet"
stub "$TMP/repo/fleet.py"
out="$(bash "$TMP/repo/bin/fleet" harness verify pi 2>&1)"; rc=$?
if [ $rc -eq 0 ] && printf '%s\n' "$out" | grep -q "MODULE=.*/repo/fleet\.py$"; then
    pass "module one level up resolves, and argv passes through ($(printf '%s\n' "$out" | grep '^ARGS='))"
else
    fail "module one level up: rc=$rc out=[$out]"
fi

# --- neither: exit 3 AND say so. HOME is a fixture, so the known-path fallbacks cannot
#     find this host's real repo and answer with a module this test never planted.
mkdir -p "$TMP/none/bin" "$TMP/none/home"
cp "$SRC" "$TMP/none/bin/fleet"
out="$(HOME="$TMP/none/home" bash "$TMP/none/bin/fleet" 2>&1)"; rc=$?
if [ $rc -eq 3 ] && printf '%s\n' "$out" | grep -q "cannot find fleet.py"; then
    pass "no module anywhere exits 3 and names what it looked for"
else
    fail "no module anywhere: rc=$rc out=[$out]"
fi

if [ $fails -eq 0 ]; then
    echo "ALL PASS"
    exit 0
fi
echo "$fails FAILED"
exit 1