#!/usr/bin/env bash
# Evidence capture — session-scoped review window (cycle 13355, 2026-10-19).
#
# Records the four things that make the fix trustworthy:
#   1. the hermetic unit/e2e assertions (one git identity, two sessions)
#   2. the DEPLOYED hook (symlink target + checksum) — not just the repo source
#   3. A1 LIVE: the trailer the hook actually wrote on this cycle's own commit
#   4. A2 LIVE: what the close would exclude — the same identities, resolved by session
#
# Paths are redacted at the generator ($HOME → ~) because this transcript is committed to a
# public repo.
set -uo pipefail
exec > >(sed -u "s|${HOME}|~|g") 2>&1

REPO="${REPO:-$HOME/hermes-cortex}"
DEPLOY="$HOME/.hermes-cortex"
PY="$DEPLOY/venv/bin/python3"
SESSION="$(grep -ho '"session_id"[[:space:]]*:[[:space:]]*"[^"]*"' "$DEPLOY"/state/.governance-*.json 2>/dev/null \
  | head -1 | sed 's/.*"\([^"]*\)"$/\1/')"
cd "$REPO" || exit 1

echo "=== session-scoped review window — evidence (cycle 13355) ==="
echo "date: $(date -Is)"
echo "repo: $REPO"
echo

echo "--- 1. hermetic assertions (real git repos, tmp_path) ---"
if [[ -x "$PY" ]]; then
  "$PY" -m pytest tests/test_session_scoped_review.py -q 2>&1 | tail -3
else
  echo "SKIP: $PY not found"
fi
echo

echo "--- 2. the DEPLOYED hook ---"
ls -l "$DEPLOY/hooks/prepare-commit-msg"
echo "sha256 (deployed)  $(sha256sum "$DEPLOY/scripts/prepare-commit-msg-session" | cut -c1-16)"
echo "sha256 (repo src)  $(sha256sum ops/scripts/prepare-commit-msg-session | cut -c1-16)"
echo "hooks dir immutable: $(lsattr -d "$DEPLOY/hooks" 2>/dev/null | awk '{print $1}')"
echo

echo "--- 3. A1 LIVE: the trailer on this cycle's commit ---"
OWN="$(git log --format='%H %s' -3 | head -3)"
echo "$OWN"
TR="$(git log -1 --format=%B | grep -i '^Cortex-Session:' || echo '(none on HEAD)')"
echo "HEAD trailer: $TR"
echo "second-parent check — trailer count in HEAD body: $(git log -1 --format=%B | grep -ci '^Cortex-Session:' || true)"
echo

echo "--- 4. A2 LIVE: which commits the close scope would exclude ---"
echo "own session id: ${SESSION:-<not read from state/.governance-session>}"
echo "window (author=this host's identity, last 10):"
git log --format='  %h %s  [author=%an]' -10
echo "trailers present in window:"
git log --format='%h %s%n  %(trailers:key=Cortex-Session,valueonly)' -10 | paste - - - 2>/dev/null | head -12
echo
echo "=== end ==="
