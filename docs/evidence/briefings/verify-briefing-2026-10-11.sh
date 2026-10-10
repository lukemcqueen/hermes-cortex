#!/usr/bin/env bash
# Verification for the 2026-10-11 KAESA sustainability briefing deliverables.
# Re-runnable: ./verify-briefing-2026-10-11.sh
# Exit 0 = all checks passed; non-zero = a check failed.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$DIR/sustainability-briefing-2026-10-11"
FAIL=0

chk() { # chk <label> <command...>
  local label="$1"; shift
  if out=$("$@" 2>&1); then
    printf 'PASS  %s :: %s\n' "$label" "$out"
  else
    printf 'FAIL  %s :: %s\n' "$label" "$out"; FAIL=1
  fi
}

echo "== deliverables present, non-empty =="
for ext in md docx pdf; do
  chk "exists:$ext" test -s "$BASE.$ext"
done

echo "== file types =="
chk "type:docx" bash -c "file -b '$BASE.docx' | grep -q 'Microsoft Word'"
chk "type:pdf"  bash -c "file -b '$BASE.pdf'  | grep -q 'PDF document'"

echo "== pdf is a real document (page count + extractable text) =="
chk "pdf:pages" bash -c "file -b '$BASE.pdf' | grep -oE '[0-9]+ page[s]?'"
chk "pdf:text-pages>1" bash -c "n=\$(pdftotext '$BASE.pdf' - | wc -w); test \$n -gt 500 && echo \"\$n words\""

echo "== docx is a valid OOXML zip with body content =="
chk "docx:zip"     bash -c "unzip -t '$BASE.docx' >/dev/null && echo 'zip OK'"
chk "docx:body"    bash -c "unzip -p '$BASE.docx' word/document.xml | grep -q '<w:body'"
chk "docx:size"    bash -c "unzip -l '$BASE.docx' word/document.xml | awk '/document.xml/{print \$1\" bytes\"}'"

echo "== markdown content integrity =="
chk "md:words"     bash -c "wc -w < '$BASE.md' | tr -d ' '"
chk "md:sources"   bash -c "grep -oE 'https?://[^ )]+' '$BASE.md' | sort -u | wc -l | tr -d ' '"
chk "md:sections"  bash -c "grep -cE '^## [0-9]' '$BASE.md'"
chk "md:no-placeholder" bash -c "! grep -qE 'TODO|FIXME|XXX|placeholder' '$BASE.md' && echo 'clean'"

echo "== source URLs are well-formed (no truncation markers) =="
chk "md:no-truncated-url" bash -c "! grep -qE 'https?://[^ )]*\.\.\.' '$BASE.md' && echo 'none'"

echo
if [ "$FAIL" -eq 0 ]; then echo "RESULT: ALL CHECKS PASSED"; else echo "RESULT: FAILURES PRESENT"; fi
exit "$FAIL"
