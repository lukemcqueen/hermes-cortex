#!/usr/bin/env bash
# Reproduce every claim of cycle 12223 (gateway /restart under launchd) in ONE run.
#
#   bash docs/evidence/launchd-restart-12223-reproduce.sh
#
# Prints one PASS/FAIL line per claim WITH the numbers observed at run time, and
# exits non-zero if any claim fails. Overrides: REPO=, PYTHON=.
set -uo pipefail

REPO="${REPO:-$HOME/hermes-cortex}"
PY="${PYTHON:-$HOME/.hermes/hermes-agent/venv/bin/python3}"
FAILS=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

say() { printf '%s\n' "$*"; }
bad() { say "FAIL  $1"; FAILS=$((FAILS + 1)); }
passed_of() { grep -Eo '[0-9]+ passed[^=]*' "$1" | tail -1; }

cd "$REPO" || exit 2
say "cycle 12223 — repo=$REPO  interpreter=$PY  head=$(git rev-parse --short HEAD)"
say

# 1 — the slash-parity suite, and the selection a changed gateway file belongs to
"$PY" -m pytest tests/test_gateway_slash_parity.py -q >"$TMP/one.txt" 2>&1
rc=$?
say "1a  rc=$rc  $(passed_of "$TMP/one.txt")   (tests/test_gateway_slash_parity.py)"
[ "$rc" = 0 ] && grep -qF "53 passed" "$TMP/one.txt" || bad "1a slash-parity suite (want rc=0 and '53 passed')"

"$PY" -m pytest tests/ -q -k 'gateway or harness or startup' >"$TMP/sel.txt" 2>&1
rc=$?
say "1b  rc=$rc  $(passed_of "$TMP/sel.txt")   (tests/ -k gateway/harness/startup)"
[ "$rc" = 0 ] || bad "1b gateway/harness/startup selection (want rc=0)"

# 2 — the launchd decision logic (the new behaviour), exercised on the test fixtures
"$PY" -m pytest tests/test_gateway_slash_parity.py -q \
      -k 'launchd or damaged or plist_template or not_supervised or SOMEONE_ELSES' \
      >"$TMP/lau.txt" 2>&1
rc=$?
say "2   rc=$rc  $(passed_of "$TMP/lau.txt")   (launchd + plist-template cases)"
[ "$rc" = 0 ] || bad "2 launchd/supervision cases (want rc=0)"

# 3 — the DEPLOYED copies match the repo (the landing claim).
#     NOTE: the header is not the same shape in every deployed file (a script may
#     carry the SOURCE lines AFTER its shebang; a template may carry none), so the
#     comparison strips leading comment/blank lines on BOTH sides — never a fixed
#     line count, which is how a probe reports drift that does not exist.
"$PY" - <<'PY' >"$TMP/deployed.txt" 2>&1
import pathlib
def body(p):
    lines = pathlib.Path(p).read_text().splitlines()
    while lines and (lines[0].startswith("#") or not lines[0].strip()):
        lines.pop(0)
    return lines
home = pathlib.Path.home()
pairs = [("ops/scripts/cortex_gateway/daemon.py", home/".hermes-cortex/scripts/cortex_gateway/daemon.py"),
         ("ops/scripts/cortex_gateway/slash_parity_evidence.py", home/".hermes-cortex/scripts/cortex_gateway/slash_parity_evidence.py"),
         ("docs/templates/com.hermes.cortex-gateway.plist", home/".hermes-cortex/templates/com.hermes.cortex-gateway.plist")]
for src, dep in pairs:
    print(("PASS" if body(dep) == body(pathlib.Path(src)) else "FAIL"), "deployed == repo:", src)
PY
cat "$TMP/deployed.txt"
grep -q "^FAIL" "$TMP/deployed.txt" && bad "3 a deployed copy differs from the repo"

# 4 — the doctor: the OVERALL line, and whether any warning names a changed path
python3 ops/scripts/manage/cortex-doctor.py --quiet >"$TMP/doc.txt" 2>&1
rc=$?
say "4   rc=$rc  $(grep -Eo 'Overall:[^(]*\([^)]*\)' "$TMP/doc.txt" | tail -1)"
grep -qF "0 fail" "$TMP/doc.txt" || bad "4 doctor (want '0 fail' in the Overall line)"
n=$(grep -E 'gateway|launchd|plist|slash_parity' "$TMP/doc.txt" | grep -c '⚠️' || true)
say "4   warnings naming a changed path: $n"
[ "$n" = "0" ] || bad "4 a doctor warning names a changed path"

# 5 — the adversarial gate, against the REAL pre-change baseline
#     (origin/main already CONTAINS the fix, so it is not a baseline)
BASE="$(git rev-parse 190aadd7^)"
git show "$BASE:ops/scripts/cortex_gateway/daemon.py" >"$TMP/before.py"
for f in "$TMP/before.py" ops/scripts/cortex_gateway/daemon.py; do
  out=$(python3 "$HOME/.hermes-cortex/scripts/adversarial-verify.py" --file "$f" --level A4 --gate 2>&1)
  counts=$(printf '%s' "$out" | grep -Eo '(Medium|Low|Info): [0-9]+' | tr '\n' ' ')
  verdict=$(printf '%s' "$out" | grep -o 'GATE_PASSED' | head -1)
  say "5   $(basename "$f"): $counts $verdict"
  [ -n "$verdict" ] || bad "5 adversarial gate blocked on $f"
done

say
if [ "$FAILS" -eq 0 ]; then say "ALL CLAIMS VERIFIED (0 failures)"; exit 0; fi
say "$FAILS CLAIM(S) FAILED"; exit 1
