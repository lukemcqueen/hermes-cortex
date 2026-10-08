#!/usr/bin/env bash
# Re-runnable, ENFORCING proof for the nightly dream digest (cycle 11724, 2026-10-09).
# Exits non-zero on ANY failing assertion and PINS the artifacts it claims via
# an expected sha256 read from a sibling sidecar file, so a changed digest
# cannot still print PASS. ADV history: -1/-2 swallowed-error + self-referential
# prior-ref; -3 label/check mismatch; -4 unpinned hashes.
set -euo pipefail
DREAMS="${HOME}/brain/esther/dreams"
TODAY="2026-10-09"
DIGEST="${DREAMS}/${TODAY}.md"
INDEX="${DREAMS}/INDEX.md"
EXPECTED="$(dirname "$0")/dream-digest-2026-10-09.expected"
FAILED=0
fail() { echo "FAIL: $*"; FAILED=1; }

echo "## 0. expected-hash sidecar present"
if [ -s "$EXPECTED" ]; then
  echo "OK  $EXPECTED present"
else
  fail "missing sidecar $EXPECTED"
fi

echo
echo "## 1. digest file exists, non-empty"
if test -s "$DIGEST"; then
  echo "OK  $DIGEST present and non-empty"
else
  fail "digest missing or empty: $DIGEST"
fi

echo
echo "## 2. INDEX carries today's entry (at least one)"
n=$(grep -c "^${TODAY} |" "$INDEX" || true)
if [ "$n" -ge 1 ]; then
  echo "OK  INDEX matches: $n"
  grep "^${TODAY} |" "$INDEX" | sed 's/^/  /'
else
  fail "INDEX has no '${TODAY} |' entry"
fi

echo
echo "## 3. digest references >=1 PRIOR dream (excluding today)"
prior=$(grep -oE '10-0[0-9]' "$DIGEST" | grep -v -- "^${TODAY#2026-}" | sort -u || true)
prior=$(printf '%s\n' "$prior" | grep -v '^$' || true)
if [ -n "$prior" ]; then
  echo "OK  prior-dream refs found:"
  printf '%s\n' "$prior" | sed 's/^/  prior-ref: /'
else
  fail "no prior-dream reference (a self-reference to ${TODAY#2026-} is not a prior dream)"
fi

echo
echo "## 4. artifacts match the PINNED sha256 + size (byte for byte)"
# Sidecar format: first non-comment line = sha256 of DIGEST, second = sha256 of
# INDEX, third = byte size of DIGEST.
mapfile -t EXP < <(grep -vE '^\s*#|^\s*$' "$EXPECTED")
EXP_DIGEST_SHA="${EXP[0]:-}"; EXP_INDEX_SHA="${EXP[1]:-}"; EXP_SIZE="${EXP[2]:-}"
sha256sum -c <<<"${EXP_DIGEST_SHA}  ${DIGEST}" || fail "digest sha256 != pinned"
sha256sum -c <<<"${EXP_INDEX_SHA}  ${INDEX}"  || fail "INDEX sha256 != pinned"
ACT_SIZE=$(stat -c '%s' "$DIGEST")
if [ "$ACT_SIZE" = "$EXP_SIZE" ]; then
  echo "OK  digest size ${ACT_SIZE} matches pinned ${EXP_SIZE}"
else
  fail "digest size ${ACT_SIZE} != pinned ${EXP_SIZE}"
fi

echo
if [ "$FAILED" -eq 0 ]; then
  echo "RESULT: PASS (all enforced checks passed; artifacts pinned by sha256+size)"
  exit 0
else
  echo "RESULT: FAIL (one or more enforced checks failed)"
  exit 1
fi
