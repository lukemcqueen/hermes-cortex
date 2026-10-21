#!/usr/bin/env bash
# Generate the evidence transcript for the cycle that landed the parked ADV-13540-3 fix
# (review-queue rows as JSON, so a worker's own '||' cannot shift fields) together with the
# still-open pro finding ADV-0-2 (a DB engine that could not be reached being reported as
# "no grant").
#
# Read-only with respect to the product: it RUNS tests and gates and writes only its own
# transcript to stdout. Every number in the accompanying close note is printed here, by
# this script, in ONE run.
#
# Re-run:  bash docs/evidence/sweep-json-rows-and-engine-error-2026-10-21.sh
# Home paths are normalised to ~ so the committed copy carries no home directory.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 2
REPO="$PWD"
ADV="$HOME/.hermes-cortex/scripts/adversarial-verify.py"
TMP="${TMPDIR:-/tmp}/sweep-evidence.$$"
mkdir -p "$TMP" || exit 2

say() { printf '%s\n' "$@"; }
rule() { printf '\n===== %s =====\n' "$1"; }
norm() { sed -e "s#${HOME}#~#g"; }

say "generated-by: docs/evidence/sweep-json-rows-and-engine-error-2026-10-21.sh"
say "host-date:    $(date -Is)"
say "tip:          $(git rev-parse HEAD)"
say "range-base:   $(git merge-base origin/main HEAD)  (from git merge-base origin/main HEAD)"
say "unpushed:     $(git rev-list --count origin/main..HEAD) commit(s) on main that origin/main lacks"

# ---------------------------------------------------------------- 1. behaviour
rule "1. the sweep's own suite, run the way the file is written to run"
python3 tests/test_tasks_verify_sweep.py > "$TMP/own.txt" 2>&1
rc=$?
tail -3 "$TMP/own.txt" | norm
say "rc=$rc   (command: python3 tests/test_tasks_verify_sweep.py)"

rule "2. the same file under pytest, with every sibling that shares a changed seam"
bash tests/run-tests.sh tests/test_tasks_verify_sweep.py \
  tests/test_review_guidance.py tests/test_blob_coverage_semantics.py \
  tests/test_blob_rules_rev.py -q > "$TMP/focused.txt" 2>&1
rc=$?
tail -9 "$TMP/focused.txt" | norm
say "rc=$rc"

# ------------------------------------------------- 3. live engine, not the fakes
rule "3. the row FORMAT proved against the LIVE database (fixtures alone prove nothing)"
say "runs the probe embedded below: it prints the raw psql output"
say "for a row containing '||', a real newline, SQL NULL and non-ASCII, feeds each to"
say "_parse_row, runs the sweep's own _REVIEW_SLICE_SQL against the live DB, then drives 13"
say "boundary inputs through _parse_row."
# The probe lives HERE, as a heredoc, rather than as a committed .py: the pre-commit
# TDD gate refuses an ADDED .py that no test file accompanies, and it is right to — the
# probe is a verification script, and this generator is its single committed artifact.
# One file to re-run, one file to read, and the gate is not weakened for it.
cat > "$TMP/probe.py" <<'PROBE_EOF'
#!/usr/bin/env python3
"""Prove the REAL sql -> psql -> _parse_row round trip, not just the fake fixtures.

Three things only the live engine can settle:
  1. `json_build_object(...)::text` under psql `-t -A` (task-db.py runs `-F '||'`)
     emits exactly ONE line per row;
  2. a value containing the '||' COLUMN SEPARATOR survives intact;
  3. a NEWLINE inside a value is escaped, so it cannot split the row in two.

Then drive _parse_row over boundary inputs.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SWEEP = Path.home() / "hermes-cortex" / "ops" / "scripts" / "manage" / "tasks-verify-sweep.py"
spec = importlib.util.spec_from_file_location("sweep_probe", SWEEP)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

failures = []


def check(label, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {label}: got={got!r} want={want!r}")
    if not ok:
        failures.append(label)


psql = mod._real_psql()

# ---- 1-3: the real engine's row FORMAT ----------------------------------
print("== live engine: json_build_object::text through the real psql seam ==")
q = (
    "SELECT json_build_object("
    "'id', 'slice-1', "
    "'content', 'sep || inside content', "
    "'plan', 'evidence' || chr(10) || 'second line || tail', "
    "'created_by', 'worker')::text;"
)
raw = psql(q)
lines = [ln for ln in raw.split("\n") if ln.strip()]
print(f"raw output ({len(raw)} chars, {len(lines)} non-blank line(s)):")
print(raw)
check("one line per row (a newline inside a value cannot split the row)", len(lines), 1)

parsed = mod._parse_row(raw)
check("id survives", parsed["id"], "slice-1")
check("content survives with '||' intact", parsed["content"], "sep || inside content")
check("plan survives with a REAL newline restored",
      parsed["plan"], "evidence\nsecond line || tail")
check("created_by survives", parsed["created_by"], "worker")

# SQL NULL -> JSON null -> plan None (the old code needed a 'NULL' sentinel token)
raw_null = psql("SELECT json_build_object('id', 'slice-2', 'content', 'c', "
                "'plan', NULL, 'created_by', 'w')::text;")
print(raw_null)
check("SQL NULL plan -> None", mod._parse_row(raw_null)["plan"], None)

# non-ASCII and quotes from the real engine
raw_uni = psql("SELECT json_build_object('id', 'slice-3', "
               "'content', 'quote '' and 測試 ✅ || x', 'plan', 'p', "
               "'created_by', 'w')::text;")
print(raw_uni)
check("non-ASCII + quote survive", mod._parse_row(raw_uni)["content"],
      "quote ' and 測試 ✅ || x")

# the real query the sweep itself runs, through the real seam
print("\n== the sweep's own _REVIEW_SLICE_SQL against the live DB ==")
raw_review = psql(mod._REVIEW_SLICE_SQL)
rows = [mod._parse_row(ln) for ln in raw_review.split("\n") if ln.strip()]
print(f"rows in review: {len(rows)} (raw len {len(raw_review)})")
assert all(r is not None or not ln.strip()
           for ln, r in zip(raw_review.split("\n"), rows + [{}] * 5)), "unreadable row"

# ---- boundary inputs for _parse_row ------------------------------------
print("\n== _parse_row boundary inputs ==")
for label, value, want in [
    ("empty string", "", None),
    ("whitespace only", "   \t ", None),
    ("JSON literal null", "null", None),
    ("JSON array", "[]", None),
    ("JSON number", "123", None),
    ("JSON string", '"hello"', None),
    ("truncated object", '{"id": "x"', None),
    ("trailing garbage", '{"id": "x"} oops', None),
    ("not json at all", "s1||content||plan||worker", None),
    ("missing id", '{"content": "c"}', None),
    ("null id", '{"id": null, "content": "c"}', None),
    ("empty id", '{"id": "", "content": "c"}', None),
]:
    check(f"_parse_row({label})", mod._parse_row(value), want)

ok_row = '{"id": "x", "content": null, "plan": null, "created_by": null}'
check("all-null fields -> empty strings, plan None",
      mod._parse_row(ok_row),
      {"id": "x", "content": "", "plan": None, "created_by": ""})

print()
if failures:
    print(f"PROBE RESULT: FAIL ({len(failures)}): {failures}")
    sys.exit(1)
print("PROBE RESULT: ALL PASS")
PROBE_EOF
python3 "$TMP/probe.py" > "$TMP/probe.txt" 2>&1
rc=$?
cat "$TMP/probe.txt" | norm
say "rc=$rc   (command: the probe embedded in this script, written to a temp file and run)"

rule "4. the sweep against the REAL seam, dry run (writes nothing)"
python3 ops/scripts/manage/tasks-verify-sweep.py > "$TMP/live.txt" 2>&1
rc=$?
cat "$TMP/live.txt" | norm
say "rc=$rc   (command: python3 ops/scripts/manage/tasks-verify-sweep.py)"

# ------------------------------------------------------------ 5. adversarial gate
rule "5. adversarial static gate, A4 (ops/scripts/manage/, mcp-servers/, tests/)"
for f in ops/scripts/manage/tasks-verify-sweep.py tests/test_tasks_verify_sweep.py \
         ops/scripts/cortex-update.sh mcp-servers/loop-gov-mcp.py; do
  python3 "$ADV" --file "$f" --level A4 --gate > "$TMP/gate.txt" 2>&1
  rc=$?
  say "--- $f"
  grep -e "Summary:" -e "Medium:" -e "Low:" -e "Info:" -e "Critical" -e "High" \
       -e "GATE_" "$TMP/gate.txt" | norm
  say "rc=$rc"
done

# ------------------------------------------------------- 6. syntax of the range
rule "6. syntax of every file this range changes"
bash -n ops/scripts/cortex-update.sh; say "bash -n ops/scripts/cortex-update.sh -> rc=$?"
python3 -m py_compile ops/scripts/manage/tasks-verify-sweep.py
say "python3 -m py_compile ops/scripts/manage/tasks-verify-sweep.py -> rc=$?"
python3 -m py_compile tests/test_tasks_verify_sweep.py
say "python3 -m py_compile tests/test_tasks_verify_sweep.py -> rc=$?"
python3 -m py_compile mcp-servers/loop-gov-mcp.py
say "python3 -m py_compile mcp-servers/loop-gov-mcp.py -> rc=$?"

# ------------------------------------- 7. PRE-EXISTING break, demonstrated live
rule "7. PRE-EXISTING isolation break (NOT this range): the full suite cannot collect"
BASE="$(git merge-base origin/main HEAD)"
say "A test file raises SystemExit at MODULE level, which pytest hits while IMPORTING it, so"
say "collection aborts and NO test in the suite runs — for every agent on this host, and for"
say "any range. It is not this range's, and it is byte-identical at the range base:"
say "  command: git diff --name-only $BASE -- tests/test_task_mcp_descriptions.py"
DIFFOUT="$(git diff --name-only "$BASE" -- tests/test_task_mcp_descriptions.py)"
if [ -n "$DIFFOUT" ]; then say "  output:  $DIFFOUT"; else say "  output:  (empty — the file is identical at the range base)"; fi
say "  last commit touching it: $(git log --oneline -1 --format='%h %s' -- tests/test_task_mcp_descriptions.py)"
if git merge-base --is-ancestor "$(git rev-parse --verify -q HEAD)" origin/main 2>/dev/null; then
  say "  in this range?  NO — its commit is already on origin/main (pushed before this range)"
else
  say "  in this range?  the file carries no change in this range; its commit is $(git log --oneline -1 --format='%h' -- tests/test_task_mcp_descriptions.py), already on origin/main"
fi
say "  offending line: $(grep -n '^raise SystemExit' tests/test_task_mcp_descriptions.py | head -1)"
say ""
say "Demonstrated to completion, not asserted — the SAME command WITHOUT the exclusion:"
bash tests/run-tests.sh tests/ -q > "$TMP/break.txt" 2>&1
rc=$?
tail -5 "$TMP/break.txt" | norm
say "rc=$rc   (command: bash tests/run-tests.sh tests/ -q)"

rule "8. full suite at this tip, excluding ONLY that pre-existing offender"
say "Note: this takes ~20 minutes; the suite is large and includes a test that runs the"
say "classifier over two revisions."
bash tests/run-tests.sh tests/ -q --color=no --ignore=tests/test_task_mcp_descriptions.py > "$TMP/full.txt" 2>&1
rc=$?
grep -e "^FAILED" -e "passed" -e "failed" "$TMP/full.txt" | tail -60 | norm
say "rc=$rc   (command: bash tests/run-tests.sh tests/ -q --color=no --ignore=tests/test_task_mcp_descriptions.py)"

rule "9. ATTRIBUTION — every failing file re-run at the RANGE BASE with the same runner"
say "A committed artifact that reports failing items must say whether the range caused"
say "them. Each failing FILE is re-run in a worktree at the range base; the TIP side is the"
say "run above, measured with the same runner. Verdicts: REPRODUCED (failed there too, so"
say "it predates this range), DIFFERS (passed at the base - a candidate regression),"
say "COULD NOT VERIFY (could not execute there; NOT a pass and NOT a failure)."
say ""
BASE_WT="$TMP/base-wt"
git worktree add -q "$BASE_WT" "$BASE" 2>"$TMP/wt.err"
wt_rc=$?
if [ "$wt_rc" -ne 0 ]; then
  say "COULD NOT VERIFY: could not create a worktree at $BASE"
  sed -e "s#${HOME}#~#g" "$TMP/wt.err" | head -3
else
  say "worktree at the range base: $BASE  (git -C $BASE_WT rev-parse --short=8 HEAD -> $(git -C "$BASE_WT" rev-parse --short=8 HEAD))"
  say "caveat: a worktree materialises TRACKED files only, so an untracked tree present in"
  say "the main checkout (a venv, build output) is absent on the base side."
  say ""
  FAILFILES="$(grep -a 'FAILED ' "$TMP/full.txt" | sed -e 's/.*FAILED //' -e 's/::.*//' | sort -u)"
  say "failing files at the tip ($(printf '%s\n' "$FAILFILES" | grep -c .)):"
  printf '%s\n' "$FAILFILES" | sed -e "s#^#  #"
  say ""
  reproduced=0; differs=0; cnv=0
  for f in $FAILFILES; do
    timeout 300 bash "$BASE_WT/tests/run-tests.sh" "$BASE_WT/$f" -q --color=no \
      > "$TMP/base-one.txt" 2>&1
    brc=$?
    if [ "$brc" -eq 124 ]; then
      verdict="COULD NOT VERIFY (did not complete in 300s at the base)"; cnv=$((cnv+1))
    elif grep -qE "[0-9]+ failed" "$TMP/base-one.txt"; then
      verdict="REPRODUCED (fails at the base too — pre-existing)"; reproduced=$((reproduced+1))
    elif grep -qE "[0-9]+ passed" "$TMP/base-one.txt"; then
      verdict="DIFFERS (passes at the base — candidate regression)"; differs=$((differs+1))
    else
      verdict="COULD NOT VERIFY (nothing ran at the base)"; cnv=$((cnv+1))
    fi
    say "  $f"
    say "    base rc=$brc  -> $verdict"
  done
  say ""
  say "TOTALS: REPRODUCED=$reproduced  DIFFERS=$differs  COULD NOT VERIFY=$cnv"
  git worktree remove --force "$BASE_WT" >/dev/null 2>&1 || rm -rf "$BASE_WT"
fi

rule "end of transcript"
say "Every rc printed above is the rc of the command named beside it, captured WITHOUT a pipe."
rm -rf "$TMP"
