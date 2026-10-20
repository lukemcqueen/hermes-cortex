#!/usr/bin/env bash
# SOURCE: hermes-cortex/docs/evidence/gov-task-id-normalization-2026-10-20-verify.sh
#
# Re-runnable verification for the issue-#188 ledger repair (cycle 13418).
# Recorded output: gov-task-id-normalization-2026-10-20.txt — regenerate by running
# this script; do not trust that file without re-running it.
#
# It re-derives EVERY claim the repair makes:
#   §1 the tool itself, re-run: 0 repairable now, and the 2 ids it refuses, named
#   §2 the ledger invariants (no id carries a newline; the repair notes are present)
#   §3 provenance: the old→new mapping read OUT of the rows' own audit field
#   §4 the backup exists, predates the repair, and still holds the malformed ids
#   §5 the two skipped ids really are in the ledger, with their spaces
#
# Exits non-zero when any invariant stops holding, so it is safe to wire into CI.
# Counts that grow with the fleet (hook cycles, total rows) are PRINTED, not
# asserted: only the invariants are asserted, and the at-repair-time totals are
# read from the manifest the tool wrote at the time.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DB="${LOOP_GOV_DB:-$HOME/.hermes-cortex/data/loop-governance.db}"
TOOL="$REPO/ops/scripts/manage/normalize-precommit-task-ids.py"
MANIFEST="$HOME/.hermes-cortex/state/task-id-normalization-manifest.txt"
TAG="task_id normalized (issue #188)"
FAILED=0

say() { printf '%s\n' "$*"; }
run() { printf '$ %s\n' "$*"; "$@"; }
fail() { say "ASSERTION FAILED: $*"; FAILED=1; }

say "# task-id normalization — verification (issue #188, cycle 13418)"
say "# host: $(hostname -s)  date: $(date '+%F %T %Z')"
say "# ledger: $DB"
say

say "=== 1. the tool, re-run against the live ledger ==="
say "# a second --apply is a no-op and the dry run reports nothing repairable;"
say "# the two ids it refuses are named rather than silently passed over"
run python3 "$TOOL" --db "$DB"
OUT="$(python3 "$TOOL" --db "$DB" 2>&1)"
case "$OUT" in
  *"RESULT: nothing to do"*) say "  → nothing repairable remains" ;;
  *) fail "the tool still finds repairable rows — the repair did not complete" ;;
esac
case "$OUT" in
  *"skipped (no guess)  : 2"*) say "  → 2 ids reported as skipped (not guessed at)" ;;
  *) say "  → NOTE: the skip count is no longer 2; inspect the output above" ;;
esac
say

say "=== 2. ledger invariants after the repair ==="
run python3 - "$DB" "$TAG" <<'PY'
import sqlite3, sys, pathlib
db, tag = pathlib.Path(sys.argv[1]), sys.argv[2]
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
rows = con.execute("SELECT task_id FROM loop_cycles").fetchall()
total = len(rows)
newline = sum(1 for r in rows if chr(10) in str(r[0]) or chr(13) in str(r[0]))
notes = con.execute("SELECT COUNT(*) FROM loop_cycles WHERE outcome_note LIKE ?",
                    (f"%{tag}%",)).fetchone()[0]
hook = con.execute("SELECT COUNT(*) FROM loop_cycles WHERE task_id LIKE 'precommit-%'").fetchone()[0]
print(f"  total rows                        : {total}")
print(f"  ids carrying a newline            : {newline}   <- invariant: must be 0")
print(f"  rows carrying the repair note     : {notes}")
print(f"  hook cycles (task_id precommit-%) : {hook}")
raise SystemExit(0 if newline == 0 else 1)
PY
[ $? -eq 0 ] || fail "an id still carries a newline"
say "# hook-cycle and total counts GROW with the fleet, so they are printed above"
say "# rather than asserted; the at-repair-time totals live in the manifest:"
if [ -f "$MANIFEST" ]; then
  grep -E "^# rows" "$MANIFEST" || say "  (manifest has no row count line)"
else
  say "  manifest absent at $MANIFEST — cannot corroborate the at-repair counts"
fi
say

say "=== 3. provenance: the mapping read OUT of the rows' audit field ==="
say "# nothing here is recomputed — the originals come from each row's own"
say "# outcome_note, so the table below is what the rows actually say"
run python3 - "$DB" "$TAG" <<'PY'
import sqlite3, sys, pathlib, re, collections
db, tag = pathlib.Path(sys.argv[1]), sys.argv[2]
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
pairs = con.execute(
    "SELECT task_id, outcome_note, COUNT(*) FROM loop_cycles WHERE outcome_note LIKE ? "
    "GROUP BY task_id, outcome_note", (f"%{tag}%",)).fetchall()
agg = collections.Counter()
for new, note, n in pairs:
    m = re.search(re.escape(tag) + r": was '(.*)'$", note or "")
    if m:
        agg[(new, m.group(1))] += n
print(f"  distinct (old -> new) pairs       : {len(agg)}")
print(f"  rows covered by those pairs       : {sum(agg.values())}")
bad = [p for p in agg if p[0] == p[1] or any(c.isspace() for c in p[0])]
print(f"  pairs where new != old, new clean : {'yes' if not bad else 'NO -> ' + repr(bad[:3])}")
print()
print("  rows | original (escaped, as stored) -> current id")
for (new, old), n in agg.most_common():
    print(f"  {n:>5}  {old!r}")
    print(f"         -> {new!r}")
raise SystemExit(0 if agg and not bad else 1)
PY
[ $? -eq 0 ] || fail "the provenance mapping could not be read back from the audit fields"
say

say "=== 4. the backup exists and predates the repair ==="
say "# the strongest proof it predates the repair: the BACKUP still holds the"
say "# malformed ids while the live ledger holds none"
BACKUP="$(ls -1t "$(dirname "$DB")"/"$(basename "$DB")".backup-* 2>/dev/null | head -1)"
if [ -n "$BACKUP" ]; then
  say "  backup: $BACKUP"
  stat -c '  size=%s bytes  mtime=%y' "$BACKUP" 2>/dev/null || ls -l "$BACKUP"
  if command -v sha256sum >/dev/null 2>&1; then
    say "  sha256: $(sha256sum "$BACKUP" | cut -d' ' -f1)"
  else
    say "  sha256: (shasum unavailable; skipped)"
  fi
  python3 - "$BACKUP" "$DB" <<'PY'
import sqlite3, sys, pathlib
backup, live = (pathlib.Path(p) for p in sys.argv[1:3])
def newline_ids(p):
    try:
        return sum(1 for r in sqlite3.connect(f"file:{p}?mode=ro", uri=True)
                   .execute("SELECT task_id FROM loop_cycles") if chr(10) in str(r[0]))
    except sqlite3.Error as e:
        print(f"  could not read {p}: {e}"); return None
b, l = newline_ids(backup), newline_ids(live)
print(f"  ids with a newline — backup: {b}   live: {l}")
print("  → the backup predates the repair" if (b or 0) > (l or 0)
      else "  → WARNING: the backup does not hold more malformed ids than the live ledger")
raise SystemExit(0 if (b or 0) > (l or 0) else 1)
PY
  [ $? -eq 0 ] || fail "the backup does not demonstrate pre-repair state"
else
  fail "no backup file found next to $DB"
fi
say

say "=== 5. the two skipped ids really are in the ledger ==="
run python3 - "$DB" <<'PY'
import sqlite3, sys, pathlib
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
rows = con.execute("SELECT id, task_id FROM loop_cycles WHERE task_id LIKE '% %'").fetchall()
print(f"  ids containing a space: {len(rows)}")
for rid, tid in rows:
    print(f"    row {rid}: {tid!r}")
raise SystemExit(0 if rows else 1)
PY
[ $? -eq 0 ] || fail "the two space-bearing ids are not in the ledger"
say "# these are agent-authored ids, not the concatenation bug: the tool refuses to"
say "# rewrite them rather than guessing at intent (see §1)"
say

if [ "$FAILED" -eq 0 ]; then
  say "RESULT: PASS — every claim about the repair is reproduced above"
else
  say "RESULT: FAIL — see ASSERTION FAILED lines"
fi
exit "$FAILED"
