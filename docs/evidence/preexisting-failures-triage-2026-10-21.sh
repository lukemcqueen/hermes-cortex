#!/usr/bin/env bash
# Triage the pre-existing suite failures that the collection fix made visible.
#
# Input is a COMMITTED artifact, not a live list: the attribution section of
# docs/evidence/sweep-json-rows-and-engine-error-2026-10-21.txt, which already re-ran every
# failing file at the range base with the same runner. This script takes those files, runs each
# once at the current tip, and records the FIRST failure reason — then groups the reasons by
# signature so the next fix can target a class instead of the next instance.
#
# Read-only with respect to the product: it runs tests and writes only its own transcript.
#
# Re-run: bash docs/evidence/preexisting-failures-triage-2026-10-21.sh
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 2
TMP="${TMPDIR:-/tmp}/triage.$$"
mkdir -p "$TMP" || exit 2
SOURCE="docs/evidence/sweep-json-rows-and-engine-error-2026-10-21.txt"
OUT="docs/evidence/preexisting-failures-triage-2026-10-21.txt"

exec >"$OUT" 2>&1

say() { printf '%s\n' "$@"; }
rule() { printf '\n===== %s =====\n' "$1"; }
norm() { sed -e "s#${HOME}#~#g"; }

say "generated-by: docs/evidence/preexisting-failures-triage-2026-10-21.sh   (this file IS that script's stdout)"
say "host-date:    $(date -Is)"
say "captured-at:  $(git rev-parse HEAD)"
say "committed-in: the commit that ADDS this file — always one commit ahead of captured-at. A"
say "              transcript cannot name its own commit: writing this file changes the revision."
say "input:        $SOURCE  (the committed attribution; section 9 re-ran every failing file at"
say "              the range base with the same runner, so this list is already attributed)"
say "why-triage:   the collection fix (commit c1333161, issue #212) made these visible again. A"
say "              bare list says nothing about whether they share a cause."

rule "1. each failing file, run once at this tip, with its first failure reason"
FILES="$(sed -n '/failing files at the tip/,/^  $/p' "$SOURCE" | grep -a '^  tests/' | sed -e 's/^  //' | sort -u)"
# Guard: the list comes from a committed artifact via a section range. If the source's shape ever
# changes, the extraction above yields nothing — and "zero files to run" reads like a clean result.
# Refuse to produce that silence: name the source and the section we expected, and exit non-zero so
# the run is visibly broken rather than quietly empty.
if [ -z "$(printf '%s\n' "$FILES" | grep -c .)" ] || [ "$(printf '%s\n' "$FILES" | grep -c .)" -eq 0 ]; then
  say "FATAL: extracted ZERO files from $SOURCE."
  say "  expected a section beginning 'failing files at the tip' and ending at a blank line,"
  say "  with entries indented two spaces under 'tests/'. The source's shape has changed, or"
  say "  the file is missing. Refusing to emit a transcript that looks like a clean run."
  say "GENERATOR_rc=2"
  exit 2
fi
say "files to run: $(printf '%s\n' "$FILES" | grep -c .)"
say ""
: > "$TMP/reasons.tsv"
for f in $FILES; do
  [ -f "$f" ] || { say "  $f"; say "    MISSING at this tip — skipped, recorded as such"; \
                   printf '%s\t%s\n' "$f" "FILE MISSING AT THIS TIP" >> "$TMP/reasons.tsv"; continue; }
  timeout 300 bash tests/run-tests.sh "$f" -q --color=no > "$TMP/one.txt" 2>&1
  rc=$?
  # rc=124 is the timeout's OWN exit code, not a test failure. Treat it as its own cause: a killed
  # run's output may be truncated mid-line, so grepping it for a reason would report whatever
  # fragment happened to survive — or nothing — and call that the failure. Name the kill instead.
  if [ "$rc" -eq 124 ]; then
    reason="TIMEOUT — file did not finish within 300s (rc=124); no failure reason is meaningful"
  else
    # The FIRST reason, not the last: a file can fail many tests, and the first is the one to fix.
    reason="$(grep -aE '^(E |FAILED )' "$TMP/one.txt" | head -1 | sed -e 's/^E *//' -e 's/^FAILED [^ ]* *//' | cut -c1-220)"
  fi
  summary="$(grep -aE '[0-9]+ (passed|failed)' "$TMP/one.txt" | tail -1)"
  # An empty summary means the runner never printed its counts — a crash, or a changed output format.
  # Printing "rc=$rc   " with nothing after it reads as "ran fine, nothing to say". Say what is true.
  [ -z "$summary" ] && summary="(no summary line captured — runner produced no pass/fail counts)"
  # A file in the attributed list that PASSES at this tip is its own finding, not a silence:
  # it is either flaky or was fixed inside the range. Name it as a cause, do not leave it blank.
  if [ "$rc" -eq 0 ] && [ -z "$reason" ]; then reason="PASSES AT THIS TIP — not reproducible now (was failing at the range base)"; fi
  [ -z "$reason" ] && reason="(no E/FAILED line captured — rc=$rc)"
  # Normalise the host path HERE, at capture, so every section of the transcript agrees — section 3
  # normalises too, and a transcript that hides a path in one section and shows it in another is
  # its own defect. It also keeps the committed artifact free of the absolute home path.
  reason="$(printf '%s' "$reason" | norm)"
  say "  $f"
  say "    rc=$rc   $summary"
  say "    reason: $reason"
  printf '%s\t%s\n' "$f" "$reason" >> "$TMP/reasons.tsv"
done

rule "2. GROUPED BY SIGNATURE — what each reason looks like, counted"
# Signatures are ordered: the first that matches wins, so a specific cause is never swallowed by
# a general one. Counted, never estimated — the numbers below are this run's own tally.
group() {
  case "$1" in
    "PASSES AT THIS TIP"*)                                echo "P. rc=0 at this tip — not reproducible now" ;;
    *REVIEWER_LIGHT_MODEL_DEFAULT*)                       echo "A. a reviewer-tier constant was renamed and not propagated" ;;
    *UNJUDGED*)                                           echo "B. the reviewer returns UNJUDGED where a verdict is required" ;;
    *contaminat*|*site-packages*|*PYTHONPATH*)            echo "C. probes decide from a contaminated interpreter env" ;;
    *"STALE artifact"*|*"does not match a fresh run"*|*"must state the real"*|*"Legacy gbrain refs"*)
                                                          echo "D. committed evidence / doc drifted from the code" ;;
    *cron*|*cron_manifest*)                               echo "E. cron manifest vs the live job" ;;
    *interpreter*)                                        echo "F. interpreter selection decides the run" ;;
    *"No module named"*|*ModuleNotFoundError*)            echo "G. missing module" ;;
    *"Permission denied"*|*PermissionError*)              echo "H. permissions" ;;
    *)                                                    echo "Z. unclassified — one-off" ;;
  esac
}
: > "$TMP/grouped.tsv"
while IFS="$(printf '\t')" read -r f r; do
  [ -z "$f" ] && continue
  g="$(group "$r")"
  printf '%s\t%s\t%s\n' "$g" "$f" "$r" >> "$TMP/grouped.tsv"
done < "$TMP/reasons.tsv"
cut -f1 "$TMP/grouped.tsv" | sort | uniq -c | sort -rn | while read -r n g; do
  say "  $n file(s)  $g"
  awk -F'\t' -v g="$g" '$1==g {printf "        %s\n", $2}' "$TMP/grouped.tsv"
done
say ""
say "  LEVERAGE — the largest group that is NOT the rc=0 group and NOT the one-off group:"
top="$(cut -f1 "$TMP/grouped.tsv" | sort | uniq -c | sort -rn | grep -av '^ *[0-9]* P\.' | grep -av ' Z\.' | head -1)"
say "    $top"
say "  A group of several files under one named cause is the next fix: one change closes them all."

rule "3. the raw table (file -> first reason), for re-grouping by hand"
while IFS="$(printf '\t')" read -r f r; do
  [ -z "$f" ] && continue
  printf '  %-62s %s\n' "$f" "$r"
done < "$TMP/reasons.tsv" | norm

rule "end of transcript"
say "Grouping is by SIGNATURE over the first captured reason, first match wins; the counts above are"
say "this run's own tally. A group with several files is the leverage: one cause, several red files."
rm -rf "$TMP"
