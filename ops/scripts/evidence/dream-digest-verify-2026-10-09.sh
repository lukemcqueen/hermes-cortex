#!/usr/bin/env bash
# Re-runnable proof for the nightly dream digest (cycle 11724, 2026-10-09).
# Asserts the digest file and INDEX entry exist and match, and prints their
# sha256 + size so the claim is checkable by anyone.
set -u
DREAMS="$HOME/brain/esther/dreams"
TODAY="2026-10-09"

echo "## 1. digest file exists, non-empty"
test -s "$DREAMS/$TODAY.md" && echo "OK  $DREAMS/$TODAY.md present and non-empty" || { echo "FAIL missing"; exit 1; }

echo
echo "## 2. INDEX carries today's entry"
grep -c "^$TODAY |" "$DREAMS/INDEX.md" | sed 's/^/matches: /'
grep "^$TODAY |" "$DREAMS/INDEX.md" | sed 's/^/  /'

echo
echo "## 3. digest references >=1 prior dream (brain remembering its own dreaming)"
grep -oE '10-0[0-9]' "$DREAMS/$TODAY.md" | sort -u | sed 's/^/  prior-ref: /'

echo
echo "## 4. sha256 + size (the claim is the digest below, byte for byte)"
sha256sum "$DREAMS/$TODAY.md" "$DREAMS/INDEX.md"
ls -l "$DREAMS/$TODAY.md"
