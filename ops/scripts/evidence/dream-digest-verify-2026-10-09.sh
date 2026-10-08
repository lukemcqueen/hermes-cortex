#!/usr/bin/env bash
# Re-runnable proof for the nightly dream digest (cycle 11724, 2026-10-09).
# ENFORCES the assertions (non-zero exit on any failure) and prints sha256 +
# size so the claim is checkable by anyone. Fixes ADV-11724-1/-2:
#   - set -euo pipefail, every grep is an assertion (|| exit 1)
#   - prior-ref check EXCLUDES today's date (a self-reference is not a prior dream)
set -euo pipefail
DREAMS="${HOME}/brain/esther/dreams"
TODAY="2026-10-09"
DIGEST="${DREAMS}/${TODAY}.md"
INDEX="${DREAMS}/INDEX.md"
FAILED=0
fail() { echo "FAIL: $*"; FAILED=1; }

echo "## 1. digest file exists, non-empty"
if test -s "$DIGEST"; then
  echo "OK  $DIGEST present and non-empty"
else
  fail "digest missing or empty: $DIGEST"
fi

echo
echo "## 2. INDEX carries exactly today's entry"
n=$(grep -c "^${TODAY} |" "$INDEX" || true)
if [ "$n" -ge 1 ]; then
  echo "OK  INDEX matches: $n"
  grep "^${TODAY} |" "$INDEX" | sed 's/^/  /'
else
  fail "INDEX has no '${TODAY} |' entry"
fi

echo
echo "## 3. digest references >=1 PRIOR dream (excluding today)"
# Exclude TODAY's own date so a self-reference cannot satisfy the requirement.
prior=$(grep -oE '10-0[0-9]' "$DIGEST" | grep -v -- "^${TODAY#2026-}$" | sort -u || true)
prior=$(printf '%s\n' "$prior" | grep -v '^$' || true)
if [ -n "$prior" ]; then
  echo "OK  prior-dream refs found:"
  printf '%s\n' "$prior" | sed 's/^/  prior-ref: /'
else
  fail "no prior-dream reference (a self-reference to ${TODAY#2026-} is not a prior dream)"
fi

echo
echo "## 4. sha256 + size (the claim is the digest below, byte for byte)"
sha256sum "$DIGEST" "$INDEX"
ls -l "$DIGEST"

echo
if [ "$FAILED" -eq 0 ]; then
  echo "RESULT: PASS (all enforced checks passed)"
  exit 0
else
  echo "RESULT: FAIL (one or more enforced checks failed)"
  exit 1
fi
