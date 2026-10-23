#!/usr/bin/env bash
# [cost/4] evidence generator — re-runnable, read-only on the live system.
#
#   bash ops/evidence/cost4-host-cost-adapter-2026-10-24.sh
#
# Writes docs/evidence/cost4-host-cost-adapter/verify.txt (this script writes the
# committed file itself, so "generated-by" is a fact about the file). Rebuilds the
# fixture in a throwaway git worktree at the pinned pre-change revision, so the RED
# side is the real pre-change code and not a reconstruction.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUTDIR="$REPO/docs/evidence/cost4-host-cost-adapter"
OUT="$OUTDIR/verify.txt"
PY="$HOME/.hermes-cortex/venv/bin/python3"
TESTFILE="tests/test_runtime/test_cron_cost_reporting.py"
SCRIPT="ops/scripts/manage/cron-cost-metrics.py"

# PINNED baseline: the revision the working tree sat on before this change.
# A literal, never a relative ref — HEAD now IS the change once it is committed,
# so `HEAD~1`/`origin/main` would silently start comparing the fix with itself.
BASE_PIN="e6f49875fca17e126b1a06277d982667f3d68bd9"

mkdir -p "$OUTDIR"
exec >"$OUT" 2>&1

say() { printf '%s\n' "$*"; }
# For lines that interpolate a PATH into the printed text: those bypass `norm`,
# which only filters command output, so an unnormalised home path would land in
# the committed transcript while the check beside it read as redacted.
say_san() { printf '%s\n' "$*" | sed -e "s|$HOME|~|g"; }
norm() { sed -e "s|$HOME|~|g" -e 's/\x1b\[[0-9;]*m//g' "$1"; }
rule() { printf '\n%s\n' "── $* ──"; }

say "# [cost/4] host cost summary — verification transcript"
say "captured-at: $(git -C "$REPO" rev-parse --short=8 HEAD)  (the revision the working"
say "  tree sat on when this ran; the committed copy is necessarily one commit ahead,"
say "  so a transcript cannot name its own commit)"
say "pinned pre-change baseline: $BASE_PIN"
say "re-run: bash ops/evidence/cost4-host-cost-adapter-2026-10-24.sh"

# ── 1. the baseline really is the pre-change revision ────────────────────────
rule "1. materialise the pinned baseline and ASSERT it is pre-change"
WT="$(mktemp -d "$HOME/.hermes/cache/scratch/cost4-wt-XXXXXX")"
git -C "$REPO" worktree add --detach "$WT" "$BASE_PIN" >"$WT.add.log" 2>&1
say "\$ git worktree add --detach <scratch> $BASE_PIN"
say "rc=$?"
norm "$WT.add.log"
resolved="$(git -C "$WT" rev-parse HEAD 2>/dev/null)"
say "asserted worktree HEAD: ${resolved:-<unresolved>}"
if [ "$resolved" != "$BASE_PIN" ]; then
  say "comparison NOT RUN, nothing claimed — the baseline did not materialise."
  exit 3
fi
# A marker the fix INTRODUCED wholesale: absent here proves this is pre-change.
hits="$(grep -F -c -- '--json-summary' "$WT/$SCRIPT" 2>/dev/null)"
say "grep -F -c -- '--json-summary' <baseline>/$SCRIPT  -> $hits"
say "  (must be 0: the option is what this change adds)"
if [ "$hits" != "0" ]; then
  say "comparison NOT RUN, nothing claimed — the baseline already carries the change."
  exit 3
fi

# ── 2. RED: the new tests against the pre-change script ──────────────────────
rule "2. RED — the new tests against the PRE-CHANGE revision"
cp "$REPO/$TESTFILE" "$WT/$TESTFILE"
say_san "\$ $PY -m pytest -q $TESTFILE   (cwd = the baseline worktree)"
(cd "$WT" && "$PY" -m pytest -q "$TESTFILE" >"$WT.red.log" 2>&1)
say "rc=$?"
norm "$WT.red.log" | tail -n 16
say "  ^ the failures above ARE the report: each is this change's option missing"
say "    from the pre-change script, which is the property the tests exist to pin."

# ── 3. GREEN: the same tests at the tip ──────────────────────────────────────
rule "3. GREEN — the same tests at the tip (this working tree)"
say_san "\$ $PY -m pytest -q $TESTFILE tests/test_runtime/test_push_metrics_cost_series.py   (cwd = repo)"
(cd "$REPO" && "$PY" -m pytest -q "$TESTFILE" tests/test_runtime/test_push_metrics_cost_series.py >"$WT.green.log" 2>&1)
say "rc=$?"
norm "$WT.green.log" | tail -n 6

# ── 4. the real thing, on this host's live audit log ─────────────────────────
rule "4. --json-summary against the LIVE audit log and LIVE state.db"
# The raw JSON goes to SCRATCH, not into the repo: its `audit.path` field carries
# an absolute home path and a committed transcript must not. Every number this
# section reads out of it is printed into THIS file, below.
say "\$ python3 $SCRIPT --json-summary --since 2026-10-06   > <scratch>/summary-esther.json"
python3 "$REPO/$SCRIPT" --json-summary --since 2026-10-06 >"$WT.summary.json" 2>"$WT.summary.err"
say "rc=$?"
say "stderr bytes: $(wc -c < "$WT.summary.err")"
say "stdout bytes: $(wc -c < "$WT.summary.json")  (an EXEC body is this whole stream)"
"$PY" - "$WT.summary.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
print("json.loads() OK — one object, no log lines beside it")
print("agent        :", d["agent"])
print("audit        :", {k: v for k, v in d["audit"].items() if k != "path"})
print("window       :", d["window"])
print("per_day      :", len(d["per_day"]), "days",
      d["per_day"][0], "...", d["per_day"][-1])
print("per_job      :", len(d["per_job"]), "rows, omitted", d["per_job_omitted"])
print("per_job[0]   :", d["per_job"][0])
print("spend        : available", d["spend"]["available"],
      "lifetime $", d["spend"].get("lifetime_usd"))
lf = {k: v for k, v in d["langfuse"].items() if k != "days"}
print("langfuse     :", lf, "days", len(d["langfuse"].get("days", [])))
PYEOF

# ── 5. static gates ──────────────────────────────────────────────────────────
rule "5. static gates"
say "\$ python3 ~/.hermes-cortex/scripts/adversarial-verify.py --file $SCRIPT --level A4 --gate"
python3 "$HOME/.hermes-cortex/scripts/adversarial-verify.py" --file "$REPO/$SCRIPT" --level A4 --gate >"$WT.a4.log" 2>&1
say "rc=$?"
norm "$WT.a4.log" | tail -n 8
say "\$ python3 -m py_compile $SCRIPT $TESTFILE"
python3 -m py_compile "$REPO/$SCRIPT" "$REPO/$TESTFILE"
say "rc=$?"
say "\$ bash ops/scripts/secret-leak-detector.sh"
bash "$REPO/ops/scripts/secret-leak-detector.sh" >"$WT.leak.log" 2>&1
say "rc=$?"
norm "$WT.leak.log" | tail -n 6

# ── cleanup ─────────────────────────────────────────────────────────────────
rule "6. cleanup"
git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1
say "worktree removed: rc=$?  (scratch dir under ~/.hermes/cache/scratch, never pruned by this script)"

say ""
say "# generated-by: this script (it wrote this file itself; stdout is not retyped)"
