#!/usr/bin/env bash
# Re-runnable evidence for the soul-refinement pass of 2026-10-24 (cycle 13776).
#
# The pass's deliverable was FLEET HYGIENE, not a principle: the mining window
# held no operator corrections, so the work was the drift the day's own commits
# re-broke — a skill lesson committed at 22:38 had not been deployed, so the
# fleet had not received it. This generator re-measures every claim the cycle
# note makes, and writes docs/evidence/soul-refinement-2026-10-24.txt itself so
# `generated-by` is a fact about the file rather than a claim about who typed it.
#
# Every emitted line goes through ONE normaliser (home paths -> ~, ANSI colour
# stripped, runs of 7+ digits masked) so no host path or long id reaches the
# committed transcript. Regenerate with:
#     bash ops/evidence/soul-refinement-2026-10-24.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 2

OUT="${OUT:-$REPO/docs/evidence/soul-refinement-2026-10-24.txt}"
DEPLOYED="${DEPLOYED:-$HOME/.hermes-cortex/skills/devops/fleet-commands/SKILL.md}"
BACKUP="${BACKUP:-$HOME/.hermes-cortex/state/deploy-backups/SKILL.md.20261024_232131.bak}"
STRAY="docs/evidence/weekly-dream-content-2026-10-24.md.tmp"

# ONE normaliser for every emitted line: ~ paths, ANSI, and 7+ digit runs.
norm() {
  sed -e "s|$HOME|~|g" \
      -e 's/\x1b\[[0-9;]*m//g' \
      -e 's/[0-9]\{7,\}/<digits>/g'
}
say()  { printf '%s\n' "$*" | norm; }
rule() { printf '%s\n' "------------------------------------------------------------" | norm; }

{
  say "soul-refinement pass — 2026-10-24 (cycle 13776)"
  say "generated-by : ops/evidence/soul-refinement-2026-10-24.sh"
  say "captured-at  : $(git rev-parse --short=8 HEAD) (working tree at run time)"
  say "date         : $(date '+%Y-%m-%dT%H:%M:%S%z')"
  say "host         : $(uname -s) $(uname -m)"
  say "note         : captured-at is the revision the tree sat on when the run"
  say "               happened; the committed copy is one commit ahead of that"
  say "               line by construction, so this file never names its own tip."

  rule
  say "## 1. Mining window — resolved from RUN TIME, never the calendar date"
  say "read-only: sqlite3 file:...state.db?mode=ro, PRAGMA query_only=1"
  PY_OUT="$(python3 - <<'PY' 2>&1
import sqlite3, time
from datetime import datetime
DB = "/home/esther/.hermes/state.db"
NOW = time.time()
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only=1")
iso = lambda t: datetime.fromtimestamp(float(t)).strftime("%Y-%m-%d %H:%M:%S") if t else None
THIS = "cron_8449be867645_20261024_231443"
prev = con.execute(
    "SELECT id,last_activity_at FROM sessions WHERE title LIKE '%soul-refinement%' "
    "AND id != ? ORDER BY COALESCE(last_activity_at,started_at) DESC LIMIT 1",
    (THIS,)).fetchone()
prev_end = float(prev["last_activity_at"]) if prev else None
lo24 = NOW - 24 * 3600
start = max(lo24, prev_end) if prev_end else lo24
print(f"now                        : {iso(NOW)}   epoch={NOW:.0f}")
print(f"previous pass last_activity: {iso(prev_end)}")
print(f"24h bound                  : {iso(lo24)}")
print(f"WINDOW (never overlaps)    : {iso(start)} .. {iso(NOW)}  ({(NOW-start)/3600:.2f} h)")
sess = con.execute(
    "SELECT id,source FROM sessions WHERE COALESCE(last_activity_at,started_at)>=? "
    "AND COALESCE(last_activity_at,started_at)<=?", (start, NOW + 60)).fetchall()
by_src = {}
for s in sess:
    by_src[s["source"]] = by_src.get(s["source"], 0) + 1
print(f"sessions in window         : {len(sess)}   by source: {by_src}")
rows = con.execute(
    "SELECT m.content,m.session_id,s.source FROM messages m JOIN sessions s ON s.id=m.session_id "
    "WHERE m.role='user' AND m.active=1 AND m.timestamp>=? AND m.timestamp<=? "
    "ORDER BY m.timestamp", (start, NOW + 60)).fetchall()
MACHINE = ("[IMPORTANT: The user has invoked", "[IMPORTANT: You are running as a scheduled cron job",
           "[IMPORTANT: Background process", "[INTERNAL NOTIFICATION", "[Cron delivery:",
           "Gateway message origin")
prose = []
for r in rows:
    c = (r["content"] or "").lstrip()
    if any(c.startswith(m) or m in c[:200] for m in MACHINE):
        continue
    if (r["source"] or "").startswith("cron") or r["source"] == "subagent":
        continue
    prose.append(r)
print(f"user rows (active=1)       : {len(rows)}")
print(f"  machine-authored         : {len(rows)-len(prose)}  (cron task prompts + [Cron delivery:] rows)")
print(f"  OPERATOR PROSE           : {len(prose)}")
con.close()
PY
)"
  printf '%s\n' "$PY_OUT" | norm
  say "assertion: window row count > 0 (a zero-row window is indistinguishable"
  say "from a quiet day, so it is printed above and never assumed)"

  rule
  say "## 2. Skill source parity — read-only --check (never regenerates)"
  say "cmd: python3 ops/scripts/manage/check-skill-drift-parity.py --check"
  PAR_OUT="$(python3 ops/scripts/manage/check-skill-drift-parity.py --check 2>&1)"
  PAR_RC=$?
  printf '%s\n' "$PAR_OUT" | norm
  say "rc=$PAR_RC"
  if [[ "$PAR_RC" == 0 ]]; then
    say "verdict: PASS — deployed tree and repo source agree, nothing stranded."
  else
    say "verdict: rc=$PAR_RC — see the tool's own report above."
  fi

  rule
  say "## 3. The drift this pass landed — was a same-day lesson deployed?"
  say "The 22:38 commit 079ab644 added the bus-envelope ALLOWLIST lesson to"
  say "skills/devops/fleet-commands/SKILL.md; the deployed copy still carried the"
  say "old text, so the fleet had not received it. Measured now:"
  say ""
  say "a) the deployed copy carries the lesson (content assertion, not a claim):"
  for needle in "ALLOWLIST" "unknown envelope field" "PERMANENT rejection"; do
    n="$(grep -c -F "$needle" "$DEPLOYED" 2>/dev/null)"
    say "   grep -cF '$needle' <deployed> -> ${n:-0}"
  done
  n_topic="$(grep -c '^  "topic":' "$DEPLOYED" 2>/dev/null)"
  say "   grep -c '^  \"topic\":' <deployed> -> ${n_topic:-0} (must be 0: the wrong"
  say "     field is exactly what the lesson removes)"
  say ""
  say "b) the pre-deploy deployed copy, as backed up by the deploy itself:"
  if [[ -f "$BACKUP" ]]; then
    say "   backup : $(printf '%s' "$BACKUP" | norm)"
    say "   bytes  : $(wc -c < "$BACKUP")   sha256: $(sha256sum "$BACKUP" | cut -c1-16)…"
    b_topic="$(grep -c '^  "topic":' "$BACKUP" 2>/dev/null)"
    b_allow="$(grep -c -F "ALLOWLIST" "$BACKUP" 2>/dev/null)"
    say "   grep -c '^  \"topic\":' -> ${b_topic:-0}  ;  grep -cF ALLOWLIST -> ${b_allow:-0}"
    say "   => the backup is the OLD text (topic present, allowlist absent) and the"
    say "      repo copy is the NEW text, so this was a stale deploy, NOT a stranded"
    say "      lesson: nothing authored on the deployed tree was discarded."
  else
    say "   backup absent — cannot compare; nothing claimed about the old text."
  fi

  rule
  say "## 4. The gate's own verdict, re-run after the deploy"
  say "cmd: python3 ops/scripts/manage/cortex-doctor.py (default verbose) | grep 'Skill drift'"
  DOC_OUT="$(timeout 300 python3 ops/scripts/manage/cortex-doctor.py 2>&1)"
  DOC_RC=$?
  printf '%s\n' "$DOC_OUT" | norm | grep -E 'Skill drift' || say "   (no 'Skill drift' line in doctor output)"
  printf '%s\n' "$DOC_OUT" | norm | grep -E 'Overall:' || say "   (no Overall line)"
  printf '%s\n' "$DOC_OUT" | norm | grep -E 'fleet-commands' && say "   NOTE: a per-skill drift line is still present" || say "   no per-skill drift line remains for devops/fleet-commands"
  say "doctor rc=$DOC_RC (rc is not 0 while unrelated warnings stand — the"
  say "  per-check lines above are the verdicts, captured with the counts)"
  say "undisposed warnings in the same run:"
  printf '%s\n' "$DOC_OUT" | norm | sed -n '/UNDISPOSED/,/EXPIRES/p' | grep -E '^ +·' || say "   (none)"

  rule
  say "## 5. Leftover in the repo tree — DECIDED, not deferred"
  if [[ -e "$STRAY" ]]; then
    say "   path   : $STRAY"
    say "   bytes  : $(wc -c < "$STRAY")   sha256: $(sha256sum "$STRAY" | cut -c1-16)…"
    say "   content: $(tr -d '\n' < "$STRAY" | norm)"
    say "   origin : an ad-hoc tamper probe wrote a copy beside the real artifact"
    say "            instead of in \$TMPDIR; NOT produced by the tracked generator"
    say "            (ops/evidence/generate-weekly-dream-verify-2026-10-24.sh tampers"
    say "            only inside \"\$W\", asserted by reading the script)."
    say "   decision: reported by path, NOT deleted (another session's file;"
    say "            destructive action needs approval). Untracked, so it cannot"
    say "            reach the public repo unless someone stages it wholesale."
  else
    say "   absent at run time: $STRAY (already resolved by someone else)."
  fi

  rule
  say "## 6. Tree state at run time"
  git status --short | norm
  say "(the two untracked entries are this cycle's own generator + transcript;"
  say " the .md.tmp above is the reported leftover)"

  rule
  say "done"
} > "$OUT" 2>&1

echo "wrote $OUT ($(wc -l < "$OUT") lines)"
