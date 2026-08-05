#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  secret-leak-detector.sh — Pre-commit secret leak scan
#
#  Scans staged files (git diff --cached) for patterns that
#  indicate secrets being passed as literal strings in
#  terminal commands or shell scripts, and PII (emails,
#  home paths, real domains, public IPs).
#
#  BLOCKS (exit 1) on real-looking credentials:
#    3a. curl/wget -u "user:12+alnum-chars" (looks like a live
#        password, not a placeholder like your-password)
#    7.  Real email addresses in the PUBLIC repo (default
#        $HOME/hermes-cortex; override with PII_PUBLIC_REPO for
#        tests). Placeholder domains (example.com, client-domain.com,
#        *.test, *.local, public services) pass.
#  WARNS on:
#    1. printf + inline string + redirection (> or >>)
#       e.g. printf '8ec^t!p&7GME' > /tmp/pass.txt
#    2. echo + inline string + pipe to sensitive tool
#       e.g. echo 'ghp_token123' | gh auth login
#    3b. Inline -u "user:placeholder" (your-password, $(cat ...))
#    4. Literal secret-looking variable assignments (20+ chars)
#    5. PII — hardcoded /home/<user>/ paths
#    6. PII — non-placeholder domains
#    7b. Real email addresses in NON-public repos (project/client
#        work is warned, never blocked)
#    8. PII — public IPv4 addresses
#
#  History:
#    2026-07-13 added as warn-only (exit 0).
#    2026-08-03 hardened after a LIVE nginx Basic-auth password
#    sat in public docs for 2 weeks — the warn-only design let it
#    through. Now blocks commits containing real-looking inline
#    credentials.
#    2026-08-04 (Esther, PII-guard incident) — added email + public-IP
#    patterns; converted every grep -P / \s / (?: construct to
#    portable ERE (grep -E / [[:space:]]) so the scan actually runs
#    on macOS (BSD grep has no -P). Emails BLOCK only in the public
#    repo; they WARN elsewhere so client/project repos are never
#    broken. PII_PUBLIC_REPO env override enables scope testing.
#
#  Installed as part of cortex-update.sh verify step.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; YELLOW='\033[1;33m'; RESET='\033[0m'
warn()  { echo -e "${YELLOW}⚠${RESET} $*"; }
error() { echo -e "${RED}✗${RESET} $*"; }

FOUND_ISSUES=0
BLOCKING_ISSUES=0
DETECTION_FILE=$(mktemp)

# Public-repo scope: real emails BLOCK only here (default = hermes-cortex).
# Override PII_PUBLIC_REPO for testing the block path in a scratch repo.
PII_PUBLIC_REPO="${PII_PUBLIC_REPO:-$HOME/hermes-cortex}"
IS_PUBLIC_REPO=0

# Only run in a git repo
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  exit 0
fi

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || true)
if [[ -n "$REPO_ROOT" && "$REPO_ROOT" == "$PII_PUBLIC_REPO" ]]; then
  IS_PUBLIC_REPO=1
fi

# Placeholder / public-service domains that are safe in any repo.
# Emails on any OTHER domain are treated as real PII.
# NOTE: keep in sync with _PLACEHOLDER_DOMAIN_RE in
# plugins/governance-enforcer/__init__.py (_check_pii_content_gate).
PLACEHOLDER_DOMAIN_RE='^(|.*\.)(example\.(com|org|net)|client-domain\.com|customer\.org|contoso\.com|test\.com|email\.com|b\.com|ex\.com|github\.com|gitlab\.com|pinggy\.io|localhost\.run|openssh\.com|libssh\.org|cluster\.mongodb\.net|all-hands\.dev|agentmail\.to|domain\.tld|test|local|internal|acme)$'

# Get staged files (non-binary, non-lock)
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACMR \
  | grep -v '\.lock$' \
  | grep -v 'package-lock\.json\|yarn\.lock\|pnpm-lock\.yaml' \
  | grep -v '\.svg$\|\.png$\|\.jpg$\|\.jpeg$\|\.gif$\|\.ico$\|\.woff2?$\|\.ttf$' \
  || true)

[[ -z "$STAGED_FILES" ]] && exit 0

# Check each staged file
for FILE in $STAGED_FILES; do
  # Skip non-text files
  if [[ "$FILE" == *.pyc ]] || [[ "$FILE" == *.pyo ]]; then
    continue
  fi

  # Get the staged content (what would be committed)
  STAGED_CONTENT=$(git show ":${FILE}" 2>/dev/null || true)
  [[ -z "$STAGED_CONTENT" ]] && continue

  # Strip comment lines (bash/sh # comments) to avoid false positives
  # from example code in documentation
  CODE_CONTENT=$(echo "$STAGED_CONTENT" | grep -v '^[[:space:]]*#' || true)
  # NOTE: no `continue` on empty CODE_CONTENT — patterns 5-8 scan
  # STAGED_CONTENT (docs-class PII) and must run even for comment-only
  # or heading-only files. Patterns 1-4 simply find nothing on empty
  # CODE_CONTENT.

  # === Pattern 1: printf + quoted string + redirection ===
  # Matches: printf 'something' > file or printf "something" > file
  if echo "$CODE_CONTENT" | grep -En "printf[[:space:]]+['\"][^'\"]{8,}['\"][[:space:]]*([|>]|>>)" >/dev/null 2>&1; then
    # Get the matching lines for reporting
    MATCHES=$(echo "$CODE_CONTENT" | grep -En "printf[[:space:]]+['\"][^'\"]{8,}['\"][[:space:]]*([|>]|>>)" 2>/dev/null || true)
    if [[ -n "$MATCHES" ]]; then
      echo "$FILE|printf_redirect|$MATCHES" >> "$DETECTION_FILE"
    fi
  fi

  # === Pattern 2: echo + inline secret + pipe to sensitive tool ===
  # Matches: echo 'secret' | gh auth login or echo 'secret' | pass
  if echo "$CODE_CONTENT" | grep -En "echo[[:space:]]+['\"][^'\"]{8,}['\"][[:space:]]*\|" >/dev/null 2>&1; then
    MATCHES=$(echo "$CODE_CONTENT" | grep -En "echo[[:space:]]+['\"][^'\"]{8,}['\"][[:space:]]*\|" 2>/dev/null || true)
    if [[ -n "$MATCHES" ]]; then
      echo "$FILE|echo_pipe|$MATCHES" >> "$DETECTION_FILE"
    fi
  fi

  # === Pattern 3: Inline -u "user:pass" in curl/wget ===
  # 3a. BLOCKS: password segment is 12+ alphanumeric chars with no
  #     separators — looks like a real generated/hex credential
  #     (e.g. a generated hex password), not a placeholder.
  # 3b. WARNS: any other curl -u "user:pass" (placeholders like
  #     your-password / $(cat file) / short demo values).
  _BLOCK_HIT=0
  if echo "$CODE_CONTENT" | grep -En "curl[[:space:]]+.*-u[[:space:]]+['\"][^'\"]+:[A-Za-z0-9]{12,}['\"]" >/dev/null 2>&1; then
    MATCHES=$(echo "$CODE_CONTENT" | grep -En "curl[[:space:]]+.*-u[[:space:]]+['\"][^'\"]+:[A-Za-z0-9]{12,}['\"]" 2>/dev/null || true)
    if [[ -n "$MATCHES" ]]; then
      echo "$FILE|curl_basic_auth_block|$MATCHES" >> "$DETECTION_FILE"
      BLOCKING_ISSUES=$((BLOCKING_ISSUES + 1))
      _BLOCK_HIT=1
    fi
  fi
  if [[ "$_BLOCK_HIT" -eq 0 ]] && echo "$CODE_CONTENT" | grep -En "curl[[:space:]]+.*-u[[:space:]]+['\"][^'\"]+:[^'\"]{8,}['\"]" >/dev/null 2>&1; then
    MATCHES=$(echo "$CODE_CONTENT" | grep -En "curl[[:space:]]+.*-u[[:space:]]+['\"][^'\"]+:[^'\"]{8,}['\"]" 2>/dev/null || true)
    if [[ -n "$MATCHES" ]]; then
      echo "$FILE|curl_basic_auth|$MATCHES" >> "$DETECTION_FILE"
    fi
  fi

  # === Pattern 4: Command substitution with secret literal ===
  # Matches: VAR='longsecret' or export VAR='longsecret'
  if echo "$CODE_CONTENT" | grep -En "(^|export[[:space:]]+)[A-Z_]+[[:space:]]*=[[:space:]]*['\"][A-Za-z0-9_!@#$%^&*()]{20,}['\"]" >/dev/null 2>&1; then
    MATCHES=$(echo "$CODE_CONTENT" | grep -En "(^|export[[:space:]]+)[A-Z_]+[[:space:]]*=[[:space:]]*['\"][A-Za-z0-9_!@#$%^&*()]{20,}['\"]" 2>/dev/null || true)
    if [[ -n "$MATCHES" ]]; then
      echo "$FILE|literal_secret_var|$MATCHES" >> "$DETECTION_FILE"
    fi
  fi

  # === Pattern 5: PII — hardcoded /home/<user>/ paths ===
  # Matches: /home/moses/, /home/luke/, /home/<any-real-username>/
  # Skips: /home/user/, /home/nobody/
  if echo "$STAGED_CONTENT" | grep -En "/home/[a-z]{2,12}/" >/dev/null 2>&1; then
    MATCHES=$(echo "$STAGED_CONTENT" | grep -En "/home/[a-z]{2,12}/" 2>/dev/null || true)
    # Filter out allowlisted patterns
    SAFE_MATCHES=""
    while IFS= read -r line; do
      if ! echo "$line" | grep -Eq "/home/(user|nobody|pi|ubuntu|ec2-user)/"; then
        SAFE_MATCHES="${SAFE_MATCHES}${line}"$'\n'
      fi
    done <<< "$MATCHES"
    if [[ -n "$SAFE_MATCHES" ]]; then
      echo "$FILE|pii_home_path|$SAFE_MATCHES" >> "$DETECTION_FILE"
    fi
  fi

  # === Pattern 6: PII — non-placeholder domains in URL examples ===
  # Matches: https://example.com or http://example.net (real-looking)
  # Skips: your-domain.com, example.com, github.com, etc.
  if echo "$STAGED_CONTENT" | grep -Eo "https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}" >/dev/null 2>&1; then
    MATCHES=$(echo "$STAGED_CONTENT" | grep -En "https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}" 2>/dev/null || true)
    SAFE_MATCHES=""
    while IFS= read -r line; do
      if ! echo "$line" | grep -Eq "(your-domain|example\.(com|org|net|io)|localhost|127\.0\.0\.1|github\.com|gitlab\.com|bitbucket\.org|pypi\.org|npmjs\.com|docker\.com|python\.org|nodejs\.org|nginx\.org|apache\.org|letsencrypt\.org|stackoverflow\.com|npm\.|docker\.|documentation\.|hermes-agent\.nousresearch|raw\.githubusercontent|ollama\.com|apple\.com|gutenberg\.org|ankiweb\.net|webtoons\.com|talktomeinkorean\.com|howtostudykorean\.com|docs\.pytest|apps\.ankiweb)"; then
        SAFE_MATCHES="${SAFE_MATCHES}${line}"$'\n'
      fi
    done <<< "$MATCHES"
    if [[ -n "$SAFE_MATCHES" ]]; then
      echo "$FILE|pii_real_domain|$SAFE_MATCHES" >> "$DETECTION_FILE"
    fi
  fi

  # === Pattern 7: PII — real email addresses ===
  # Matches: user@domain.tld (domain must start with a letter, which
  # skips asset filenames like icon@2x.png). Domain checked against
  # the placeholder allowlist. BLOCKS in the public repo, WARNS in
  # project/client repos (never breaks non-cortex work).
  # Scans STAGED_CONTENT (docs-class PII, like patterns 5/6).
  EMAIL_RE='[A-Za-z0-9._%+-]+@[A-Za-z][A-Za-z0-9.-]*\.[A-Za-z]{2,}'
  if echo "$STAGED_CONTENT" | grep -Eo "$EMAIL_RE" >/dev/null 2>&1; then
    EMAIL_MATCHES=$(echo "$STAGED_CONTENT" | grep -Eo "$EMAIL_RE" 2>/dev/null || true)
    if [[ -n "$EMAIL_MATCHES" ]]; then
      while IFS= read -r EMAIL; do
        [[ -z "$EMAIL" ]] && continue
        DOMAIN="${EMAIL#*@}"
        if ! echo "$DOMAIN" | grep -Eq "$PLACEHOLDER_DOMAIN_RE"; then
          MASKED=$(echo "$EMAIL" | sed -E 's/^[^@]{1,4}[^@]*@/***@/')
          if [[ "$IS_PUBLIC_REPO" -eq 1 ]]; then
            echo "$FILE|pii_email_block|$MASKED" >> "$DETECTION_FILE"
            BLOCKING_ISSUES=$((BLOCKING_ISSUES + 1))
          else
            echo "$FILE|pii_email_warn|$MASKED" >> "$DETECTION_FILE"
          fi
        fi
      done <<< "$EMAIL_MATCHES"
    fi
  fi

  # === Pattern 8: PII — public IPv4 addresses ===
  # Matches any IPv4; skips private / loopback / link-local / CGNAT /
  # documentation ranges (10/8, 127/8, 192.168/16, 172.16-31/12,
  # 169.254/16, 100.64-127/10, 192.0.2/24, 198.51.100/24, 203.0.113/24).
  # EXEMPT (2026-08-05): the shared blocklist files — blocked_ips.add and
  # blocked_ips.submit exist to hold public IPs; that IS the data, not PII.
  # Without the exemption every agent commit warns once per blocked IP
  # (Gisu got flooded; Telegram spam-filter ban risk).
  case "$FILE" in
    ops/install/deploy/nginx/blocked_ips.add|ops/install/deploy/nginx/blocked_ips.submit)
      : ;;  # blocklist data — public IPs are the content, skip pattern 8
    *)
  IP_RE='[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}'
  if echo "$STAGED_CONTENT" | grep -Eo "$IP_RE" >/dev/null 2>&1; then
    IP_MATCHES=$(echo "$STAGED_CONTENT" | grep -Eo "$IP_RE" 2>/dev/null || true)
    if [[ -n "$IP_MATCHES" ]]; then
      while IFS= read -r IPADDR; do
        [[ -z "$IPADDR" ]] && continue
        O1=$((10#${IPADDR%%.*})); REST="${IPADDR#*.}"
        O2=$((10#${REST%%.*}));  REST2="${REST#*.}"
        O3=$((10#${REST2%%.*}))
        if [[ "$O1" -eq 10 ]] || [[ "$O1" -eq 127 ]] || [[ "$O1" -eq 0 ]]; then continue; fi
        if [[ "$O1" -eq 192 && "$O2" -eq 168 ]]; then continue; fi
        if [[ "$O1" -eq 172 && "$O2" -ge 16 && "$O2" -le 31 ]]; then continue; fi
        if [[ "$O1" -eq 169 && "$O2" -eq 254 ]]; then continue; fi
        if [[ "$O1" -eq 100 && "$O2" -ge 64 && "$O2" -le 127 ]]; then continue; fi
        if [[ "$O1" -eq 192 && "$O2" -eq 0 && "$O3" -eq 2 ]]; then continue; fi
        if [[ "$O1" -eq 198 && "$O2" -eq 51 && "$O3" -eq 100 ]]; then continue; fi
        if [[ "$O1" -eq 203 && "$O2" -eq 0 && "$O3" -eq 113 ]]; then continue; fi
        echo "$FILE|pii_public_ip|$IPADDR" >> "$DETECTION_FILE"
      done <<< "$IP_MATCHES"
    fi
  fi
      ;;
  esac
done

# Report findings
if [[ -s "$DETECTION_FILE" ]]; then
  echo ""
  echo "━━━ Secret Leak Detector ━━━"
  echo ""

  while IFS='|' read -r FILE TYPE MATCH_LINE; do
    case "$TYPE" in
      printf_redirect)
        error "Potential secret leak via printf+redirect in ${FILE}:"
        echo "   ${MATCH_LINE}"
        echo "   → Use: cp ~/credential_file /tmp/dest  (file-to-file, no content leakage)"
        echo ""
        ;;
      echo_pipe)
        error "Potential secret leak via echo+pipe in ${FILE}:"
        echo "   ${MATCH_LINE}"
        echo "   → Use: command < ~/token_file  (stdin redirect from file)"
        echo ""
        ;;
      curl_basic_auth)
        error "Potential secret leak via curl -u in ${FILE}:"
        echo "   ${MATCH_LINE}"
        echo "   → Use: curl -u \"user:\$(cat ~/.password_file)\" https://..."
        echo ""
        ;;
      curl_basic_auth_block)
        error "🔴 BLOCKED — live credential inline in curl command in ${FILE}:"
        echo "   ${MATCH_LINE}"
        echo "   → Replace the literal password with a placeholder or \$(cat ~/.password_file)"
        echo "   → Commit BLOCKED: a real-looking credential must never be committed."
        echo ""
        ;;
      literal_secret_var)
        error "Literal secret value in variable assignment in ${FILE}:"
        echo "   ${MATCH_LINE}"
        echo "   → Use: VAR=\$(cat ~/secret_file)  (subshell, no leakage)"
        echo ""
        ;;
      pii_home_path)
        error "PII — hardcoded /home/<user>/ path in ${FILE}:"
        echo "   ${MATCH_LINE}"
        echo "   → Use: \$HOME or ~/ instead of /home/username/"
        echo ""
        ;;
      pii_real_domain)
        warn "PII — non-placeholder domain in ${FILE}:"
        echo "   ${MATCH_LINE}"
        echo "   → Use: your-domain.com or example.com for examples"
        echo ""
        ;;
      pii_email_block)
        error "🔴 BLOCKED — real email address in ${FILE}:"
        echo "   ${MATCH_LINE}"
        echo "   → Real emails must never be committed to the public repo (agent-contract rule 16)."
        echo "   → Use a placeholder: admin@client-domain.com"
        echo ""
        ;;
      pii_email_warn)
        warn "PII — real-looking email in ${FILE}:"
        echo "   ${MATCH_LINE}"
        echo "   → If this is a real address, use a placeholder (admin@client-domain.com)."
        echo ""
        ;;
      pii_public_ip)
        warn "PII — public IP address in ${FILE}:"
        echo "   ${MATCH_LINE}"
        echo "   → Use a private-range example (192.168.1.1) or a placeholder."
        echo ""
        ;;
    esac
    FOUND_ISSUES=$((FOUND_ISSUES + 1))
  done < "$DETECTION_FILE"

  echo "━━━ End of Secret Leak Report (${FOUND_ISSUES} potential leak(s), ${BLOCKING_ISSUES} blocking) ━━━"
  echo ""
fi

rm -f "$DETECTION_FILE"

# BLOCKING credentials (real-looking inline passwords, real emails in
# the public repo) fail the commit. Pre-commit-score runs this with
# `set -euo pipefail` — a non-zero exit aborts the hook and blocks the
# push. Warn-only items exit 0.
if [[ "$BLOCKING_ISSUES" -gt 0 ]]; then
  exit 1
fi
exit 0  # warn-only findings do not block the commit
