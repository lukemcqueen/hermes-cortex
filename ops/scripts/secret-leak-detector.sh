#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  secret-leak-detector.sh — Pre-commit secret leak scan
#
#  Scans staged files (git diff --cached) for patterns that
#  indicate secrets being passed as literal strings in
#  terminal commands or shell scripts.
#
#  Three patterns detected:
#    1. printf + inline string + redirection (> or >>)
#       e.g. printf '8ec^t!p&7GME' > /tmp/pass.txt
#    2. echo + inline string + pipe to sensitive tool
#       e.g. echo 'ghp_token123' | gh auth login
#    3. Inline -u "user:pass" in curl/wget commands
#       e.g. curl -u "admin:password" https://...
#
#  WARN-ONLY — does not block the commit. Prints warnings
#  that the agent must review before pushing.
#
#  Installed as part of cortex-update.sh verify step.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; YELLOW='\033[1;33m'; RESET='\033[0m'
warn()  { echo -e "${YELLOW}⚠${RESET} $*"; }
error() { echo -e "${RED}✗${RESET} $*"; }

FOUND_ISSUES=0
DETECTION_FILE=$(mktemp)

# Only run in a git repo
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  exit 0
fi

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
  [[ -z "$CODE_CONTENT" ]] && continue

  # === Pattern 1: printf + quoted string + redirection ===
  # Matches: printf 'something' > file or printf "something" > file
  if echo "$CODE_CONTENT" | grep -Pn "printf\s+['\"][^'\"]{8,}['\"]\s*(?:[|>]|>>)" >/dev/null 2>&1; then
    # Get the matching lines for reporting
    MATCHES=$(echo "$CODE_CONTENT" | grep -Pn "printf\s+['\"][^'\"]{8,}['\"]\s*(?:[|>]|>>)" 2>/dev/null || true)
    if [[ -n "$MATCHES" ]]; then
      echo "$FILE|printf_redirect|$MATCHES" >> "$DETECTION_FILE"
    fi
  fi

  # === Pattern 2: echo + inline secret + pipe to sensitive tool ===
  # Matches: echo 'secret' | gh auth login or echo 'secret' | pass
  if echo "$CODE_CONTENT" | grep -Pn "echo\s+['\"][^'\"]{8,}['\"]\s*\|" >/dev/null 2>&1; then
    MATCHES=$(echo "$CODE_CONTENT" | grep -Pn "echo\s+['\"][^'\"]{8,}['\"]\s*\|" 2>/dev/null || true)
    if [[ -n "$MATCHES" ]]; then
      echo "$FILE|echo_pipe|$MATCHES" >> "$DETECTION_FILE"
    fi
  fi

  # === Pattern 3: Inline -u "user:pass" in curl/wget ===
  # Matches: curl -u "user:longstring" or wget --user=user --password=longstring
  if echo "$CODE_CONTENT" | grep -Pn "curl\s+.*\s-u\s+['\"][^'\"]+:[^'\"]{8,}['\"]" >/dev/null 2>&1; then
    MATCHES=$(echo "$CODE_CONTENT" | grep -Pn "curl\s+.*\s-u\s+['\"][^'\"]+:[^'\"]{8,}['\"]" 2>/dev/null || true)
    if [[ -n "$MATCHES" ]]; then
      echo "$FILE|curl_basic_auth|$MATCHES" >> "$DETECTION_FILE"
    fi
  fi

  # === Pattern 4: Command substitution with secret literal ===
  # Matches: VAR='longsecret' or export VAR='longsecret'
  if echo "$CODE_CONTENT" | grep -Pn "(?:^|export\s+)[A-Z_]+\s*=\s*['\"][A-Za-z0-9_!@#$%^&*()]{20,}['\"]" >/dev/null 2>&1; then
    MATCHES=$(echo "$CODE_CONTENT" | grep -Pn "(?:^|export\s+)[A-Z_]+\s*=\s*['\"][A-Za-z0-9_!@#$%^&*()]{20,}['\"]" 2>/dev/null || true)
    if [[ -n "$MATCHES" ]]; then
      echo "$FILE|literal_secret_var|$MATCHES" >> "$DETECTION_FILE"
    fi
  fi

  # === Pattern 5: PII — hardcoded /home/<user>/ paths ===
  # Matches: /home/moses/, /home/luke/, /home/<any-real-username>/
  # Skips: /home/user/, /home/nobody/
  if echo "$STAGED_CONTENT" | grep -Pn "/home/[a-z]{2,12}/" >/dev/null 2>&1; then
    MATCHES=$(echo "$STAGED_CONTENT" | grep -Pn "/home/[a-z]{2,12}/" 2>/dev/null || true)
    # Filter out allowlisted patterns
    SAFE_MATCHES=""
    while IFS= read -r line; do
      if ! echo "$line" | grep -qE "/home/(user|nobody|pi|ubuntu|ec2-user)/"; then
        SAFE_MATCHES="${SAFE_MATCHES}${line}"$'\n'
      fi
    done <<< "$MATCHES"
    if [[ -n "$SAFE_MATCHES" ]]; then
      echo "$FILE|pii_home_path|$SAFE_MATCHES" >> "$DETECTION_FILE"
    fi
  fi

  # === Pattern 6: PII — non-placeholder domains in URL examples ===
  # Matches: https://somedomain.com or http://custom.server.net
  # Skips: your-domain.com, example.com, github.com, etc.
  if echo "$STAGED_CONTENT" | grep -Po "https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}" >/dev/null 2>&1; then
    MATCHES=$(echo "$STAGED_CONTENT" | grep -Pn "https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}" 2>/dev/null || true)
    SAFE_MATCHES=""
    while IFS= read -r line; do
      if ! echo "$line" | grep -qE "(your-domain|example\.(com|org|net|io)|localhost|127\.0\.0\.1|github\.com|gitlab\.com|bitbucket\.org|pypi\.org|npmjs\.com|docker\.com|python\.org|nodejs\.org|nginx\.org|apache\.org|letsencrypt\.org|stackoverflow\.com|npm\.|docker\.|documentation\.|hermes-agent\.nousresearch|raw\.githubusercontent|ollama\.com|apple\.com|gutenberg\.org|ankiweb\.net|webtoons\.com|talktomeinkorean\.com|howtostudykorean\.com|docs\.pytest|apps\.ankiweb)"; then
        SAFE_MATCHES="${SAFE_MATCHES}${line}"$'\n'
      fi
    done <<< "$MATCHES"
    if [[ -n "$SAFE_MATCHES" ]]; then
      echo "$FILE|pii_real_domain|$SAFE_MATCHES" >> "$DETECTION_FILE"
    fi
  fi
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
        error "Inline credentials in curl command in ${FILE}:"
        echo "   ${MATCH_LINE}"
        echo "   → Use: curl -u \"user:\$(cat ~/.password_file)\" https://..."
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
    esac
    FOUND_ISSUES=$((FOUND_ISSUES + 1))
  done < "$DETECTION_FILE"

  echo "━━━ End of Secret Leak Report (${FOUND_ISSUES} potential leak(s)) ━━━"
  echo ""
fi

rm -f "$DETECTION_FILE"

exit 0  # warn-only, never blocks commit
