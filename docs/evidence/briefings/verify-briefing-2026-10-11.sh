#!/usr/bin/env bash
# Verification for the 2026-10-11 KAESA sustainability briefing deliverables.
# Re-runnable: bash verify-briefing-2026-10-11.sh
# Exit 0 = all checks passed; non-zero = a check failed.
#
# This script verifies BOTH copies of the artifacts, because the task delivers
# them to the cron output dir AND they are committed to the repo as evidence:
#   1. delivery path  ~/.hermes/cron/output/            (what the cron sends)
#   2. repo evidence  <repo>/docs/evidence/briefings/   (what a reviewer audits)
# A reviewer running this from the repo checks both; a mismatch is a real bug.
set -u
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="${REPO_DIR:-$HOME/hermes-cortex/docs/evidence/briefings}"
OUT_DIR="$HOME/.hermes/cron/output"
FAIL=0

chk() { # chk <label> <command...>
  local label="$1"; shift
  if out=$("$@" 2>&1); then
    printf 'PASS  %s :: %s\n' "$label" "$out"
  else
    printf 'FAIL  %s :: %s\n' "$label" "$out"; FAIL=1
  fi
}

# --- resolve the two locations -------------------------------------------
# Prefer the copy next to this script; fall back to the known paths so the
# script works whether run from the repo or from the cron output dir.
if [ -f "$SELF_DIR/sustainability-briefing-2026-10-11.md" ]; then
  HERE="$SELF_DIR"
elif [ -f "$OUT_DIR/sustainability-briefing-2026-10-11.md" ]; then
  HERE="$OUT_DIR"
else
  HERE=""
fi

echo "== location resolution =="
printf 'INFO  script dir : %s\n' "$SELF_DIR"
printf 'INFO  using copy : %s\n' "${HERE:-(none found)}"
printf 'INFO  out dir    : %s\n' "$OUT_DIR"
printf 'INFO  repo dir   : %s\n' "$REPO_DIR"

# --- check 1: both copies exist ------------------------------------------
echo "== deliverables present in BOTH delivery and repo paths =="
for d in "$OUT_DIR" "$REPO_DIR"; do
  tag=$(basename "$d")
  for ext in md docx pdf; do
    chk "exists:$tag/$ext" test -s "$d/sustainability-briefing-2026-10-11.$ext"
  done
done

# --- check 2: the two copies are byte-identical ---------------------------
echo "== delivery copy and repo copy agree =="
for ext in md docx pdf; do
  chk "same:$ext" bash -c "
    a='$OUT_DIR/sustainability-briefing-2026-10-11.$ext'
    b='$REPO_DIR/sustainability-briefing-2026-10-11.$ext'
    if [ -f \"\$a\" ] && [ -f \"\$b\" ]; then
      cmp -s \"\$a\" \"\$b\" && echo 'identical' || { echo 'DIFFER'; exit 1; }
    else echo 'one copy missing'; exit 1; fi"
done

BASE="$OUT_DIR/sustainability-briefing-2026-10-11"
echo "== file types (delivery path) =="
chk "type:docx" bash -c "file -b '$BASE.docx' | grep -q 'Microsoft Word'"
chk "type:pdf"  bash -c "file -b '$BASE.pdf'  | grep -q 'PDF document'"

echo "== pdf is a real document (page count + extractable text) =="
chk "pdf:pages"   bash -c "file -b '$BASE.pdf' | grep -oE '[0-9]+ page[s]?'"
chk "pdf:has-text" bash -c "n=\$(pdftotext '$BASE.pdf' - | wc -w); test \$n -gt 500 && echo \"\$n words\""

echo "== docx is a valid OOXML zip with body content =="
chk "docx:zip"  bash -c "unzip -t '$BASE.docx' >/dev/null && echo 'zip OK'"
chk "docx:body" bash -c "unzip -p '$BASE.docx' word/document.xml | grep -q '<w:body'"
chk "docx:size" bash -c "unzip -l '$BASE.docx' word/document.xml | awk '/document.xml/{print \$1\" bytes\"}'"

echo "== markdown content integrity =="
chk "md:words"    bash -c "wc -w < '$BASE.md' | tr -d ' '"
chk "md:urls"     bash -c "grep -oE 'https?://[^ )]+' '$BASE.md' | sort -u | wc -l | tr -d ' '"
chk "md:sections" bash -c "grep -cE '^## [0-9]' '$BASE.md'"
chk "md:no-placeholder" bash -c "! grep -qE 'TODO|FIXME|XXX|placeholder' '$BASE.md' && echo 'clean'"
chk "md:no-truncated-url" bash -c "! grep -qE 'https?://[^ )]*\\.\\.\\.' '$BASE.md' && echo 'none'"

# --- check 3: source-URL reachability (opt-in; needs network) -------------
# Set CHECK_URLS=1 to hit each unique source URL. Off by default so the
# script stays fast and usable offline; a non-2xx is reported, not fatal,
# because publishers legitimately return 403/paywall codes to bots.
if [ "${CHECK_URLS:-0}" = "1" ]; then
  echo "== source URL reachability (CHECK_URLS=1) =="
  urls=$(grep -oE 'https?://[^ )]+' "$BASE.md" | sort -u)
  n=0; bad=0
  for u in $urls; do
    n=$((n+1))
    code=$(curl -sS -o /dev/null -w '%{http_code}' -L --max-time 15 \
           -A 'Mozilla/5.0 (compatible; briefing-verifier)' "$u" 2>/dev/null || echo 000)
    case "$code" in
      2*|3*) : ;;
      *) printf 'WARN  http %s :: %s\n' "$code" "$u"; bad=$((bad+1)) ;;
    esac
  done
  printf 'INFO  checked %s URLs, %s non-2xx (403/paywall to bots is expected for some publishers)\n' "$n" "$bad"
else
  echo "== source URL reachability: skipped (set CHECK_URLS=1 to enable) =="
fi

echo
if [ "$FAIL" -eq 0 ]; then echo "RESULT: ALL CHECKS PASSED"; else echo "RESULT: FAILURES PRESENT"; fi
exit "$FAIL"
