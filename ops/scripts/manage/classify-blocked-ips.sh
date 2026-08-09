#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  classify-blocked-ips.sh — Evidence-based blocklist review
#
#  Classifies blocked_ips.add entries by STRENGTH OF EVIDENCE so
#  legit-user false positives can be removed WITHOUT removing real
#  threats (Luke 2026-08-08: "don't remove the bad ones").
#
#  Evidence tiers:
#    STRONG  — IP appears in fail2ban ban history (real attacker,
#              confirmed by repeated failed auth / attack patterns)
#    WEAK    — IP only ever tripped the volume threshold (>=10 req
#              in 60 min). A legit dashboard user (SPA refresh =
#              15-30 parallel requests) trips this. Candidates for
#              removal / allow-listing.
#    ALLOWED — IP is in /etc/nginx/allow-ips-manual.conf (explicit
#              manual override — must NEVER be blocked)
#    STALE   — fail2ban banned it once, then UNbanned (IP may have
#              been recycled; low current risk)
#
#  OUTPUT: three files next to blocked_ips.add:
#    blocked_ips.add        (unchanged — this script never edits)
#    blocked_ips.review     WEAK-evidence IPs (human review)
#    blocked_ips.confirmed  STRONG-evidence IPs (keep)
#
#  Run ON THE HOST whose fail2ban log carries the evidence
#  (content hosts: kustos/gisu/joseph), not the orchestrator.
#
#  Usage:
#    bash classify-blocked-ips.sh [path-to-blocked_ips.add]
#
#  No_agent-safe: silent-ish output, no writes outside the repo
#  source dir. Never deploys anything — review output only.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

CORTEX_REPO="${CORTEX_REPO:-${HOME}/hermes-cortex}"
BLOCKED="${1:-${CORTEX_REPO}/ops/install/deploy/nginx/blocked_ips.add}"
OUT_DIR="$(dirname "$BLOCKED")"
REVIEW="${OUT_DIR}/blocked_ips.review"
CONFIRMED="${OUT_DIR}/blocked_ips.confirmed"
ALLOW_MANUAL="${ALLOW_MANUAL:-/etc/nginx/allow-ips-manual.conf}"

# ── Collect fail2ban ban evidence ──
F2B_LOGS=()
for f in /var/log/fail2ban.log /var/log/fail2ban.log.1 \
         /var/log/fail2ban.log.*.gz /opt/homebrew/var/log/fail2ban.log \
         /usr/local/var/log/fail2ban.log; do
  [ -f "$f" ] && F2B_LOGS+=("$f")
done

F2B_BANNED=/tmp/f2b-classify-banned.$$
: > "$F2B_BANNED"
for f in "${F2B_LOGS[@]:-}"; do
  case "$f" in
    *.gz) sudo -n zcat "$f" 2>/dev/null || zcat "$f" 2>/dev/null || true ;;
    *)    sudo -n cat "$f" 2>/dev/null || cat "$f" 2>/dev/null || true ;;
  esac | grep -oE 'Ban [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' \
       | awk '{print $2}' >> "$F2B_BANNED" || true
done
sort -u "$F2B_BANNED" -o "$F2B_BANNED"

# Also collect Unban evidence (stale tier)
F2B_UNBANNED=/tmp/f2b-classify-unbanned.$$
: > "$F2B_UNBANNED"
for f in "${F2B_LOGS[@]:-}"; do
  case "$f" in
    *.gz) sudo -n zcat "$f" 2>/dev/null || zcat "$f" 2>/dev/null || true ;;
    *)    sudo -n cat "$f" 2>/dev/null || cat "$f" 2>/dev/null || true ;;
  esac | grep -oE 'Unban [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' \
       | awk '{print $2}' >> "$F2B_UNBANNED" || true
done
sort -u "$F2B_UNBANNED" -o "$F2B_UNBANNED"

# ── Allow-list ──
ALLOWED=()
if [ -f "$ALLOW_MANUAL" ]; then
  while IFS= read -r line; do
    line="$(echo "$line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    case "$line" in
      \#*|"") continue ;;
      allow*) ALLOWED+=("$(echo "$line" | sed -E 's/^allow[[:space:]]+//; s/;.*$//')") ;;
    esac
  done < "$ALLOW_MANUAL"
fi

# ── Classify (batch: comm against sorted sets — no per-IP grep) ──
SORTED_BLOCKED=/tmp/f2b-classify-blocked.$$
grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' "$BLOCKED" | sort -u > "$SORTED_BLOCKED"

# Weak = in blocklist, never banned by fail2ban
comm -23 "$SORTED_BLOCKED" "$F2B_BANNED" > "$REVIEW"
# Strong = banned (and never unbanned)
comm -12 "$SORTED_BLOCKED" "$F2B_BANNED" > "$CONFIRMED"
# Stale = banned AND unbanned
comm -12 "$SORTED_BLOCKED" "$F2B_UNBANNED" > /tmp/f2b-classify-stale.$$
comm -12 "$CONFIRMED" /tmp/f2b-classify-stale.$$ > /tmp/f2b-classify-stale2.$$
# Rebuild confirmed = banned minus unbanned
comm -23 "$CONFIRMED" /tmp/f2b-classify-stale.$$ > "$CONFIRMED"

STRONG=$(wc -l < "$CONFIRMED")
WEAK=$(wc -l < "$REVIEW")
STALE=$(wc -l < /tmp/f2b-classify-stale2.$$)
TOTAL=$(wc -l < "$SORTED_BLOCKED")
ALLOWED_CNT=0
# Exclude allow-listed from review (they're never blocked anyway)
# Batch: expand allow entries (IPs + CIDRs) ONCE via a single python call,
# then comm — never per-IP subprocess spawns.
if [ "${#ALLOWED[@]}" -gt 0 ]; then
  ALLOW_EXPANDED=/tmp/f2b-classify-allowed.$$
  python3 - "$ALLOW_EXPANDED" "${ALLOWED[@]}" <<'PYEOF'
import ipaddress, sys
out, entries = sys.argv[1], sys.argv[2:]
seen = set()
for e in entries:
    try:
        if "/" in e:
            for ip in ipaddress.ip_network(e, strict=False).hosts():
                s = str(ip)
                if s not in seen:
                    seen.add(s)
        else:
            ipaddress.ip_address(e)  # validate
            if e not in seen:
                seen.add(e)
    except ValueError:
        continue
with open(out, "w") as fh:
    for s in sorted(seen):
        fh.write(s + "\n")
PYEOF
  comm -23 "$REVIEW" "$ALLOW_EXPANDED" > "$REVIEW".filtered
  mv "$REVIEW".filtered "$REVIEW"
  ALLOWED_CNT=$(wc -l < "$ALLOW_EXPANDED")
  WEAK=$(wc -l < "$REVIEW")
  rm -f "$ALLOW_EXPANDED"
fi

echo "━━━ Blocklist classification ━━━"
echo "  Total entries:        $TOTAL"
echo "  STRONG evidence:      $STRONG  (fail2ban-banned — KEEP)"
echo "  Stale (banned+unban): $STALE   (in confirmed, review later)"
echo "  WEAK evidence:        $WEAK    (volume-only — review file)"
echo "  Allow-listed:         $ALLOWED_CNT (excluded, never blocked)"
echo ""
echo "  Review candidates:  $REVIEW"
echo "  Confirmed to keep:  $CONFIRMED"

rm -f "$F2B_BANNED" "$F2B_UNBANNED" "$SORTED_BLOCKED" \
      /tmp/f2b-classify-stale.$$ /tmp/f2b-classify-stale2.$$
