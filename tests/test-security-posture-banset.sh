#!/usr/bin/env bash
# test-security-posture-banset.sh
# Case matrix for the firewall ban-set decision in agent-security-posture-check.sh.
# Extracts the real block (anchored on stable markers) and runs it under
# stub binaries (nft/iptables/sudo on a temp PATH), so the test covers the
# deployed logic, not a copy.
set -uo pipefail

SCRIPT="${HOME}/hermes-cortex/ops/scripts/agent-security-posture-check.sh"
[ -f "$SCRIPT" ] || { echo "SKIP: script not found"; exit 0; }

BLOCK=$(awk '/^# --- 3\. firewall ban set ---/{p=1} p{print} /^# --- 4\./{exit}' "$SCRIPT")

FAILBIN=$(mktemp -d)
trap 'rm -rf "$FAILBIN"' EXIT

make_stub() { # $1 = name, $2 = env var for rc
  cat > "$FAILBIN/$1" <<EOF
#!/usr/bin/env bash
exit "\${$2:-1}"
EOF
  chmod +x "$FAILBIN/$1"
}
make_stub nft NFT_RC
make_stub iptables IPT_RC
make_stub sudo SUDO_RC

failures=0

run_case() {
  local name="$1" expect="$2"
  local out
  out=$(PATH="$FAILBIN:$PATH" bash -c '
    set -uo pipefail
    ok()   { echo "OK:$*"; }
    warn() { echo "WARN:$*"; }
    fail() { echo "FAIL:$*"; exit 1; }
    OS=Linux
    TIER_MINIMAL=0
    F2B_JAIL_LIST="${F2B_JAIL_LIST:-}"
    '"$BLOCK"'
  ' 2>&1)
  local rc=$?
  if [[ "$out" == "$expect"* ]]; then
    echo "PASS: $name → $out"
  else
    echo "FAIL: $name → expected [$expect...] got [$out] rc=$rc"
    failures=$((failures + 1))
  fi
}

# Case A — esther: jail active, firewall not verifiable as non-root → WARN (not FAIL)
NFT_RC=1 IPT_RC=1 SUDO_RC=1 F2B_JAIL_LIST="nginx-badbots sshd" run_case \
  "jail-active-but-unverifiable-warns" "WARN:firewall ban set f2b-sshd not verifiable"

# Case B — full verification via sudo nft → OK
NFT_RC=1 IPT_RC=1 SUDO_RC=0 F2B_JAIL_LIST="sshd" run_case \
  "sudo-nft-verifies-ok" "OK:nftables f2b-sshd set present"

# Case C — nothing verifiable AND no jail list → FAIL (real gap)
NFT_RC=1 IPT_RC=1 SUDO_RC=1 F2B_JAIL_LIST="" run_case \
  "unverifiable-and-no-jail-fails" "FAIL:firewall ban set f2b-sshd missing"

# Case D — nft readable without sudo → OK
NFT_RC=0 IPT_RC=1 SUDO_RC=1 F2B_JAIL_LIST="sshd" run_case \
  "plain-nft-reads-ok" "OK:nftables f2b-sshd set present"

if [[ $failures -gt 0 ]]; then
  echo "RESULT: $failures case(s) FAILED"
  exit 1
fi
echo "RESULT: all cases passed"
