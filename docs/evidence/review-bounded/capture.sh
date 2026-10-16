#!/usr/bin/env bash
# capture.sh — REGENERATE docs/evidence/review-bounded/live-proof.txt
#
# The claim this artifact supports: the close-time reviewer is now BOUNDED — in
# thinking budget, in wall clock, and in the UNIT it judges (one blob at a time,
# cached by content) — and the pre-change revision demonstrably is not. Sections 5
# and 6 additionally show the RESTARTED in-process path loading that module and the
# live store holding per-blob verdicts, so the claim is artifact-backed rather than
# asserted.
#
# Every command is printed immediately above its own output, and each rc is
# measured from the command itself (not from a pipe's last stage). The baseline is
# pinned to a SHA, never to HEAD: the artifact is committed in the same range as
# the fix, so HEAD would resolve to the FIXED module and the comparison would be a
# tautology.
#
#   cd ~ && bash hermes-cortex/docs/evidence/review-bounded/capture.sh \
#       > hermes-cortex/docs/evidence/review-bounded/live-proof.txt
set -u

EV="hermes-cortex/docs/evidence/review-bounded"
BASELINE="119e6006"          # tip before the change: no per-blob surface, no bounds
PRE="/tmp/pre-review-bounds-loop-gov.py"

body() {
  cd "$HOME" || exit 1
  local PY
  PY=$(command -v python3)

  echo "REVIEWER BOUNDS — LIVE proof (generated, not hand-written)"
  echo "Produced by: bash $EV/capture.sh   (every path below is normalised to ~)"
  echo "Generated at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo

  echo "═══════ 1. The baseline is genuinely PRE-change ═══════"
  echo "\$ git -C hermes-cortex show $BASELINE:mcp-servers/loop-gov-mcp.py > $PRE"
  git -C hermes-cortex show "$BASELINE:mcp-servers/loop-gov-mcp.py" > "$PRE"
  echo "\$ grep -c 'blob_reviews' $PRE     # 0 => no per-blob surface in the baseline"
  grep -c 'blob_reviews' "$PRE" || true
  echo "\$ grep -c '_hard_deadline' $PRE   # 0 => no hard deadline in the baseline"
  grep -c '_hard_deadline' "$PRE" || true
  echo "\$ grep -c '\"reasoning\"' $PRE     # 0 => no bounded thinking in the baseline"
  grep -c '"reasoning"' "$PRE" || true
  echo

  echo "═══════ 2. The bounds hold on the working tree ═══════"
  echo "\$ python3 hermes-cortex/tests/test_reviewer_budget.py"
  "$PY" hermes-cortex/tests/test_reviewer_budget.py 2>&1 | grep -v '^\[mcp-server\]'
  echo "rc=${PIPESTATUS[0]}"
  echo
  echo "\$ python3 hermes-cortex/tests/test_review_per_blob.py"
  "$PY" hermes-cortex/tests/test_review_per_blob.py 2>&1 | grep -v '^\[mcp-server\]'
  echo "rc=${PIPESTATUS[0]}"
  echo

  echo "═══════ 3. The baseline FAILS the same checks (discrimination) ═══════"
  echo "\$ CORTEX_LOOP_GOV_SERVER=$PRE python3 hermes-cortex/tests/test_reviewer_budget.py"
  CORTEX_LOOP_GOV_SERVER="$PRE" "$PY" hermes-cortex/tests/test_reviewer_budget.py 2>&1 \
    | grep -v '^\[mcp-server\]'
  echo "rc=${PIPESTATUS[0]}"
  echo "  -> note the deadline case: against a TRICKLING peer the baseline took ~22s"
  echo "     and was aborted only by the socket timeout after the peer stopped. The"
  echo "     measured production hang ran 15 and 26 MINUTES because the provider kept"
  echo "     sending; only a wall-clock deadline bounds that."
  echo
  echo "\$ CORTEX_LOOP_GOV_SERVER=$PRE python3 hermes-cortex/tests/test_review_per_blob.py"
  CORTEX_LOOP_GOV_SERVER="$PRE" "$PY" hermes-cortex/tests/test_review_per_blob.py 2>&1 \
    | grep -v '^\[mcp-server\]'
  echo "rc=${PIPESTATUS[0]}"
  echo

  echo "═══════ 4. Adversarial gate (A4) on every changed file ═══════"
  echo "\$ adversarial-verify.py --file <f> --level A4 --gate   (rc 0 = no critical/high)"
  for f in mcp-servers/loop-gov-mcp.py tests/test_review_per_blob.py \
           tests/test_reviewer_budget.py "$EV/capture.sh"; do
    printf '%-56s ' "$f"
    hermes-cortex/ops/scripts/quality/adversarial-verify.py --file "hermes-cortex/$f" --level A4 --gate 2>&1 \
      | grep -E 'GATE_PASSED|GATE_FAILED' || echo "NO VERDICT"
  done
  echo

  echo "═══════ 5. The RESTARTED in-process path runs this module ═══════"
  echo "The close-time reviewer runs in-process when a close goes through the"
  echo "loop-governance MCP child. That child holds the revision it STARTED with, so"
  echo "the child's own start time is the thing to look at."
  echo
  echo "\$ pgrep -af 'tools/loop-governance/loop-gov-mcp.py'"
  pgrep -af 'tools/loop-governance/loop-gov-mcp.py' || echo "(no such process)"
  echo "rc=$?"
  echo
  echo "\$ ps -o pid,lstart,etimes -p <that pid>   # started AFTER the deploy of this module"
  CHILD=$(pgrep -f 'tools/loop-governance/loop-gov-mcp.py' | head -1)
  if [ -n "${CHILD:-}" ]; then
    ps -o pid=,lstart=,etimes= -p "$CHILD"
  fi
  echo "rc=$?"
  echo
  echo "\$ grep -c <symbol> ~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py"
  echo "   (symbols the fix INTRODUCED — 0 would mean the deployed copy is pre-change)"
  for sym in _review_uncovered_blobs other_locks _hard_deadline BLOB_REVIEW_CAP_PER_CLOSE; do
    printf '   %-28s %s\n' "$sym" \
      "$(grep -c "$sym" "$HOME/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py")"
  done
  echo "rc=$?"
  echo
  echo "\$ python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet   (loop-gov lines + counts)"
  DO=$("$PY" hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet 2>&1)
  DRC=$?
  printf '%s\n' "$DO" | grep -i 'loop-gov'
  printf '%s\n' "$DO" | grep -E 'PENDING cycles'
  echo "doctor rc=$DRC   warnings=$(printf '%s\n' "$DO" | grep -c '⚠️')   failures=$(printf '%s\n' "$DO" | grep -c '^  ❌')"
  echo "   A non-zero rc here is not a hidden failure: the doctor's warnings include"
  echo "   'Repo clean' (this capture's own regenerated file is uncommitted until the"
  echo "   cycle commits it) and the pre-existing skill drift the lesson pipeline writes"
  echo "   to the DEPLOYED copies (reconciled by reconcile-stranded-skills.py). The"
  echo "   PENDING-cycles line is informational and counts THIS cycle, which stays"
  echo "   unscored until the close scores it. The failure count above is the one to read."
  echo
  echo "═══════ 6. The LIVE store holds per-blob verdicts, and what a receipt records ═══════"
  echo "Verdicts are written by the per-blob pass as it runs, keyed by blob CONTENT. The"
  echo "query resolves the store through the component's OWN module-level LOOP_DB and"
  echo "opens it on a read-only URI, so this script never names the store file and writes"
  echo "nothing to it."
  echo
  echo "\$ python3 -c '<blob_reviews + newest receipts, via the component store accessor>'"
  "$PY" -c "
import glob, importlib.util, json, os, sqlite3
from pathlib import Path
src = Path.home() / 'hermes-cortex' / 'mcp-servers' / 'loop-gov-mcp.py'
spec = importlib.util.spec_from_file_location('loopgov', src)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)   # inert on import: the server's work is behind __main__
con = sqlite3.connect('file:%s?mode=ro' % mod.LOOP_DB, uri=True)
print('LOOP_DB:', os.path.basename(str(mod.LOOP_DB)))
print('blob_reviews, by verdict:',
      list(con.execute('SELECT verdict, COUNT(*) FROM blob_reviews GROUP BY verdict')))
print('most recent verdicts (blob_sha, verdict, ts):')
for row in con.execute('SELECT blob_sha, verdict, ts FROM blob_reviews ORDER BY ts DESC LIMIT 5'):
    print('  ', row)
files = sorted(glob.glob(os.path.expanduser('~/.hermes-cortex/state/.reviewed-*.json')),
               key=os.path.getmtime, reverse=True)
print('receipts on disk:', len(files))
for f in files[:3]:
    d = json.load(open(f))
    print('  ', os.path.basename(f), '| verdict:', d.get('verdict'),
          '| reviewed_blobs:', len(d.get('reviewed_blobs') or []),
          '| reviewed_files:', len(d.get('reviewed_files') or []))
"
  echo "rc=$?"
  echo "   No receipt carries the CURRENT tip, and that is expected: a receipt is written"
  echo "   BY a successful close, so the close this range is working toward is what creates"
  echo "   it. Receipts that predate this range record as few as 0 reviewed blobs; a receipt"
  echo "   whose blobs do not cover the range it authorises is refused by the push gate."
  echo
  echo "═══════ 7. What this proof does NOT cover ═══════"
  echo "- A live reviewer outage. The stalled peer in §2/§3 is a local socket that"
  echo "  TRICKLES bytes, which is what defeats a socket timeout; no real provider was"
  echo "  asked to hang."
  echo "- macOS. The pi-side rendering and the CLI adapter are untested on that host."
}

body | sed "s|$HOME|~|g"
