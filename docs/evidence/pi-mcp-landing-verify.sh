#!/usr/bin/env bash
# Verify the pi-mcp landing (cycle 12234) in ONE run: every claim, with the numbers
# observed at run time. Exits non-zero if any claim fails.
#
#   bash docs/evidence/pi-mcp-landing-verify.sh
# Overrides: REPO=, PYTHON=
set -uo pipefail

REPO="${REPO:-$HOME/hermes-cortex}"
PY="${PYTHON:-$HOME/.hermes/hermes-agent/venv/bin/python3}"
FAILS=0
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
say() { printf '%s\n' "$*"; }
bad() { say "FAIL  $1"; FAILS=$((FAILS + 1)); }

cd "$REPO" || exit 2
say "pi-mcp landing verify — repo=$REPO  head=$(git rev-parse --short HEAD)"
say

# 1 — the installer suite (interpreter-by-capability + the malformed variants D1..D4)
bash tests/test_pi_mcp_installer.sh >"$TMP/inst.txt" 2>&1; rc=$?
say "1  installer suite rc=$rc  $(grep -c '^  PASS' "$TMP/inst.txt") checks   $(tail -1 "$TMP/inst.txt")"
[ "$rc" = 0 ] || bad "1 installer suite"
say "   D variants exercised: $(grep -oE '^  PASS  D[0-9]+:' "$TMP/inst.txt" | sort -u | wc -l | tr -d ' ') shapes"

# 2 — the audit suite (cortex-context required; foreign entries not judged)
python3 tests/test_pi_integration_audit.py >"$TMP/audit.txt" 2>&1; rc=$?
say "2  audit suite rc=$rc  $(tail -1 "$TMP/audit.txt")"
[ "$rc" = 0 ] || bad "2 audit suite"
python3 tests/test_pi_integration_foreign_server.py >"$TMP/for.txt" 2>&1; rc=$?
say "2b foreign-server cases rc=$rc  $(tail -1 "$TMP/for.txt")"
[ "$rc" = 0 ] || bad "2b foreign-server cases"

# 3 — the gateway suite the changed pi_control.py belongs to
"$PY" -m pytest tests/test_gateway_slash_parity.py tests/test_pi_integration_foreign_server.py \
      -q --no-header >"$TMP/pytest.txt" 2>&1; rc=$?
say "3  pytest (gateway slash parity + foreign server) rc=$rc  $(grep -Eo '[0-9]+ passed[^=]*' "$TMP/pytest.txt" | tail -1)"
[ "$rc" = 0 ] || bad "3 pytest"

# 4 — the generated harness docs still match the registry
"$PY" ops/install/harnesses/generate-harnesses.py --check >"$TMP/gen.txt" 2>&1; rc=$?
say "4  generate-harnesses --check rc=$rc  $(tail -1 "$TMP/gen.txt")"
[ "$rc" = 0 ] || bad "4 derived harness docs drift"

# 5 — the DEPLOYED copies match the repo (body compare, leading comments stripped)
"$PY" - <<'PY' >"$TMP/dep.txt" 2>&1
import pathlib
def body(p):
    lines = pathlib.Path(p).read_text().splitlines()
    while lines and (lines[0].startswith("#") or not lines[0].strip()):
        lines.pop(0)
    return lines
home = pathlib.Path.home()
for src, dep in (("ops/scripts/cortex_gateway/pi_control.py", home/".hermes-cortex/scripts/cortex_gateway/pi_control.py"),
                 ("mcp-servers/cortex-context-mcp.py", home/".hermes-cortex/scripts/cortex-context-mcp.py")):
    print(("PASS" if body(dep) == body(pathlib.Path(src)) else "FAIL"), "deployed == repo:", src)
PY
cat "$TMP/dep.txt"
grep -q '^FAIL' "$TMP/dep.txt" && bad "5 deployed copy differs"

say
if [ "$FAILS" -eq 0 ]; then say "ALL CLAIMS VERIFIED (0 failures)"; exit 0; fi
say "$FAILS CLAIM(S) FAILED"; exit 1
