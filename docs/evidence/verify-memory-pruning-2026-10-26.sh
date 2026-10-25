#!/usr/bin/env bash
# Re-runnable verification for the 2026-10-26 memory-pruning run.
# Read-only: touches no memory file and no repo state. Exit 0 = every assertion holds.
#
# Environment note: this host's governance enforcer classifies `bash <path>` as
# write-class inside ~/hermes-cortex, so run it from OUTSIDE the repo, or with an
# active lock. The intended invocation is the one the doctor suggests:
#     (cd "$HOME" && bash "$HOME/hermes-cortex/docs/evidence/verify-memory-pruning-2026-10-26.sh")
set -u

EV="$HOME/hermes-cortex/docs/evidence"
MEM="$HOME/.hermes/memories/MEMORY.md"
USR="$HOME/.hermes/memories/USER.md"
PASS=0; FAIL=0
ok(){ echo "PASS  $1"; PASS=$((PASS+1)); }
no(){ echo "FAIL  $1"; FAIL=$((FAIL+1)); }

echo "## committed snapshots exist (re-verifiable from a clean checkout)"
for f in MEMORY.before-2026-10-26.md USER.before-2026-10-26.md \
         memory-pruning-2026-10-26.txt verify-memory-pruning-2026-10-26.sh; do
  [ -s "$EV/$f" ] && ok "present: $f" || no "missing: $f"
done

echo "## the run changed no memory content (no-change outcome)"
[ "$(md5sum "$MEM" | cut -d' ' -f1)" = "6d1b7b5b56bb94a99a0d33bd6160b731" ] \
  && ok "MEMORY.md md5 pinned" || no "MEMORY.md md5 drifted"
[ "$(md5sum "$USR" | cut -d' ' -f1)" = "90bef2152103beb9fba783c22e2685fd" ] \
  && ok "USER.md md5 pinned" || no "USER.md md5 drifted"

echo "## budget"
MC=$(python3 -c "import sys;print(len(open(sys.argv[1],encoding='utf-8').read()))" "$MEM")
UC=$(python3 -c "import sys;print(len(open(sys.argv[1],encoding='utf-8').read()))" "$USR")
[ "$MC" -le 2200 ] && ok "MEMORY.md $MC <= 2200" || no "MEMORY.md $MC over budget"
[ "$UC" -le 1375 ] && ok "USER.md $UC <= 1375" || no "USER.md $UC over budget"

echo "## no entry carries a date <= 2026-06-15 (the template's stale-entry hypothesis)"
if grep -Eq '2026-0[1-6]-' "$MEM"; then
  no "a pre-2026-06-16 date tag is present in MEMORY.md"
else
  ok "no memory entry carries a date <= 2026-06-15"
fi

echo "## every artifact/route the memory entries point at is live"
for p in "$HOME/.hermes-cortex/deploy-manifest.tsv" \
         "$HOME/hermes-cortex/docs/design/agent-interop.md" \
         "$HOME/hermes-cortex/ops/scripts/cortex_lib/paths.py" \
         "$HOME/hermes-cortex/ops/scripts/orch-bus/adversarial-review.py" \
         "$HOME/.hermes-cortex/scripts/probe-gate-logic.py" \
         "$HOME/.asus" "$HOME/.spotify_user" "$HOME/.xprofile" \
         "$HOME/.config/autostart"; do
  [ -e "$p" ] && ok "live: $p" || no "MISSING: $p"
done
# The third display layer lives in the SYSTEM lightdm conf dir, not under $HOME
# (measured 2026-10-26: /etc/lightdm/lightdm.conf.d/50-hdmi-1080p.conf, root:root 252 B).
# An earlier revision of this probe looked under $HOME/.config and reported a false MISSING.
for p in /etc/lightdm/lightdm.conf.d/50-hdmi-1080p.conf; do
  [ -e "$p" ] && ok "live: lightdm 1080p layer ($p)" || no "MISSING: $p"
done

echo "## network routes named in memory"
ping -c1 -W2 192.168.1.24 >/dev/null 2>&1 && ok "stored peer host reachable" \
  || no "stored peer host unreachable"
timeout 3 bash -c '</dev/tcp/127.0.0.1/14005' 2>/dev/null && ok "metrics :14005 listening" \
  || no "metrics :14005 closed"

echo "## the stored sudo claim still holds (no NOPASSWD for nft/iptables)"
sudo -n true 2>&1 | grep -q 'password is required' \
  && ok "sudo -n still needs a password — stored entry accurate" \
  || no "sudo -n succeeded — the stored NOPASSWD-BROKEN entry is now STALE"

echo "## FINDING 1: AGENTS.md.local is a leftover, not a live backup"
A="$HOME/.hermes/AGENTS.md"; AL="$HOME/.hermes/AGENTS.md.local"; R="$HOME/hermes-cortex/AGENTS.md"
if [ -f "$AL" ]; then
  [ "$(sha256sum "$A" | cut -c1-12)" = "$(sha256sum "$R" | cut -c1-12)" ] \
    && ok "~/.hermes/AGENTS.md == repo AGENTS.md (deployed file correct)" \
    || no "deployed AGENTS.md differs from the repo source"
  if [ "$(sha256sum "$AL" | cut -d' ' -f1)" = "$(sha256sum "$A" | cut -d' ' -f1)" ]; then
    no "AGENTS.md.local hashes to the live file — re-triage it as LIVE"
  else
    ok "AGENTS.md.local hashes to a SUPERSEDED file (leftover of an earlier deploy)"
  fi
  if grep -q 'per SOUL P11' "$AL" 2>/dev/null; then
    ok "AGENTS.md.local carries the pre-fix 'per SOUL P11' cross-reference"
  else
    no "AGENTS.md.local lost the stale-copy signature — re-inspect"
  fi
else
  ok "AGENTS.md.local removed — confirm hermes-home-cleanup SKILL.md:61 was updated"
fi

echo "## FINDING 1 documentation state (the row that still calls it LIVE)"
SK="$HOME/hermes-cortex/skills/devops/hermes-home-cleanup/SKILL.md"
if grep -q 'AGENTS.md.local' "$SK" 2>/dev/null; then
  if grep -q 'Preserved by rule' "$SK"; then
    no "hermes-home-cleanup:61 still documents AGENTS.md.local as LIVE (stale row)"
  else
    ok "skill table row corrected"
  fi
else
  ok "skill table no longer mentions AGENTS.md.local"
fi

echo
echo "PASS=$PASS FAIL=$FAIL"
if [ "$FAIL" -eq 0 ]; then echo "RESULT: PASS"; exit 0; else echo "RESULT: FAIL"; exit 1; fi
