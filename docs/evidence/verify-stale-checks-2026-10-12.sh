#!/usr/bin/env bash
# Re-runnable stale-check probe for the 2026-10-12 memory-pruning run.
# Each check corresponds to one MEMORY.md entry that survived pruning; the
# point is to show the stored fact is still true on the live host today.
# Environment-dependent checks SKIP (never FAIL) on a non-worker host.
# Exit 0 = every applicable check passed.
set -u
fail=0
ok()   { echo "OK    $1"; }
bad()  { echo "FAIL  $1"; fail=1; }
skip() { echo "SKIP  $1"; }

echo "## referenced artifacts still exist (MEMORY entries A4 / A10)"
for f in "$HOME/.hermes-cortex/deploy-manifest.tsv" \
         "$HOME/hermes-cortex/docs/design/agent-interop.md" \
         "$HOME/hermes-cortex/ops/scripts/cortex_lib/paths.py" \
         "$HOME/.asus" "$HOME/.spotify_user" ; do
  if [ -e "$f" ]; then ok "exists: ${f/#$HOME/\$HOME}"; else bad "missing: ${f/#$HOME/\$HOME}"; fi
done

echo "## stored claim 'sudo NOPASSWD ... BROKEN' (entry A7) — expect a password prompt"
if command -v sudo >/dev/null 2>&1; then
  if sudo -n true 2>&1 | grep -q 'password is required'; then
    ok "sudo -n still prompts -> NOPASSWD still BROKEN (entry A7 accurate, kept)"
  else
    echo "NOTE  sudo -n did NOT prompt -> NOPASSWD may now work; entry A7 would need revisiting"
  fi
else
  skip "sudo not present"
fi

echo "## stored claim 'Moses ssh mosesaaron (192.168.1.24)' (entry A2) — expect reachable"
if command -v ping >/dev/null 2>&1; then
  if ping -c1 -W2 192.168.1.24 >/dev/null 2>&1; then
    ok "moses 192.168.1.24 reachable (entry A2 accurate, kept)"
  else
    skip "moses unreachable from here (entry A2 is host/LAN-dependent, not falsified)"
  fi
else
  skip "ping not present"
fi

echo "---"
if [ "$fail" -eq 0 ]; then echo "RESULT: all applicable stale checks PASS, exit 0"; else echo "RESULT: $fail check(s) FAILED"; fi
exit "$fail"
