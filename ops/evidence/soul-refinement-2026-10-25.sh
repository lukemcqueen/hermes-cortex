#!/usr/bin/env bash
# Re-runnable evidence for the soul-refinement pass of 2026-10-25 (cycle 13791).
#
# The pass's deliverable was a STALE-REFERENCE fix, not a principle: the mining
# window held no operator corrections (11 cron sessions, 13 machine-authored
# rows, 0 operator prose), so the work was the wrong instruction the day's own
# activity exposed — four places teaching that a DEPLOYED script copy is
# lock-free because `~/.hermes-cortex` is not a git repo. It is not a git repo,
# and that is not why it ever worked. This generator re-measures every claim the
# cycle note makes and writes docs/evidence/soul-refinement-2026-10-25.txt
# itself, so `generated-by` is a fact about the file rather than a claim about
# who typed it.
#
# Every emitted line goes through ONE normaliser (home paths -> ~, ANSI colour
# stripped, runs of 7+ digits masked). Regenerate with:
#     bash ops/evidence/soul-refinement-2026-10-25.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 2

OUT="${OUT:-$REPO/docs/evidence/soul-refinement-2026-10-25.txt}"

# The pass's OWN resolved mining window, frozen at the moment the pass resolved
# it (see §1). Recomputing it live moves the end bound with the clock, so the
# artifact would then disagree with the cycle it documents. Override both to
# re-run the derivation for another pass.
WIN_START="${WINDOW_START:-2026-10-24 23:42:30}"
WIN_END="${WINDOW_END:-2026-10-25 23:16:42}"
export WIN_START WIN_END

# The baseline revision is PINNED as a literal, not resolved from a ref:
# `git merge-base origin/main HEAD` equals this SHA only until the range is
# pushed, after which it resolves to the FIXED tip and the comparison silently
# stops testing what it claims. 3d6d20c4 is the revision the working tree sat
# on when this pass began.
BASE_SHA="${BASE_SHA:-3d6d20c4}"
# The marker the fix REMOVED — unique to this change, so its presence in the
# baseline proves the extracted copy really is the pre-change revision.
OLD_MARKER="repo gate never engages"
WT="${WT:-${TMPDIR:-/tmp}/soul-base-$$}"

# ONE normaliser for every emitted line: ~ paths, ANSI colour, 7+ digit runs.
norm() {
  sed -e "s|$HOME|~|g" \
      -e 's/\x1b\[[0-9;]*m//g' \
      -e 's/[0-9]\{7,\}/<digits>/g'
}
# The revision token is the ONE exemption from the digit mask: a short sha that
# happens to be all digits is unresolvable if masked, and `captured-at` exists
# precisely so a reader can re-run this file against that revision.
say_rev() { printf '%s\n' "$*" | sed -e "s|$HOME|~|g" -e 's/\x1b\[[0-9;]*m//g'; }
say()  { printf '%s\n' "$*" | norm; }
rule() { printf '%s\n' "------------------------------------------------------------" | norm; }

cleanup() { git worktree remove --force "$WT" >/dev/null 2>&1; }
trap cleanup EXIT

{
  say "soul-refinement pass — 2026-10-25 (cycle 13791)"
  say "generated-by : ops/evidence/soul-refinement-2026-10-25.sh"
  say_rev "captured-at  : $(git rev-parse --short=8 HEAD) (working tree at run time)"
  say "date         : $(date '+%Y-%m-%dT%H:%M:%S%z')"
  say "host         : $(uname -s) $(uname -m)"
  say "masking      : every line below has ~ paths, ANSI colour and runs of 7+"
  say "               digits masked; the captured-at revision above is the one"
  say "               exemption, so it stays resolvable for a re-run."
  say "note         : captured-at is the revision the tree sat on when the run"
  say "               happened; the committed copy is one commit ahead of that"
  say "               line by construction, so this file never names its own tip."

  rule
  say "## 1. Mining window — resolved from RUN TIME, never the calendar date"
  say "Bounds are the window THIS PASS resolved, frozen so a re-run reproduces"
  say "them. A ROW is selected by its own timestamp and a SESSION by"
  say "COALESCE(last_activity_at,started_at), so the two are different sets by"
  say "construction; the counts are reconciled explicitly rather than left"
  say "looking inconsistent."
  say "cmd: sqlite3 file:~/.hermes/state.db?mode=ro, PRAGMA query_only=1"
  PY_OUT="$(python3 - <<'PY' 2>&1
import os, sqlite3, time
from datetime import datetime
DB = os.path.expanduser("~/.hermes/state.db")
FMT = "%Y-%m-%d %H:%M:%S"
start = time.mktime(time.strptime(os.environ["WIN_START"], FMT))
end = time.mktime(time.strptime(os.environ["WIN_END"], FMT))
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
con.execute("PRAGMA query_only=1")
iso = lambda t: datetime.fromtimestamp(float(t)).strftime("%Y-%m-%d %H:%M:%S") if t else None
print(f"WINDOW (frozen)             : {iso(start)} .. {iso(end)}   ({(end-start)/3600:.2f} h)")
prev = con.execute(
    "SELECT last_activity_at FROM sessions WHERE title LIKE '%soul-refinement%' "
    "AND COALESCE(last_activity_at,started_at) < ? "
    "ORDER BY COALESCE(last_activity_at,started_at) DESC LIMIT 1",
    (end - 3600,)).fetchone()
prev_end = float(prev["last_activity_at"]) if prev else None
print(f"previous pass last_activity : {iso(prev_end)}")
print("non-overlap assertion       : "
      + ("PASS (window starts at the previous pass's own end, by "
         f"{(end - start) / 3600:.2f} h of coverage)" if prev_end
         and abs(prev_end - start) < 2 else "REVIEW — start is not the previous end"))
sess = con.execute(
    "SELECT source FROM sessions WHERE COALESCE(last_activity_at,started_at)>=? "
    "AND COALESCE(last_activity_at,started_at)<=?", (start, end)).fetchall()
by_src = {}
for s in sess:
    by_src[s["source"]] = by_src.get(s["source"], 0) + 1
print(f"sessions, activity bound in window : {len(sess)}   by source: {by_src}")
rows = con.execute(
    "SELECT m.content,m.timestamp,m.session_id,s.source,"
    "COALESCE(s.last_activity_at,s.started_at) AS act "
    "FROM messages m JOIN sessions s ON s.id=m.session_id "
    "WHERE m.role='user' AND COALESCE(m.active,1)=1 AND m.timestamp>=? AND m.timestamp<=? "
    "ORDER BY m.timestamp", (start, end)).fetchall()
MACHINE = ("[IMPORTANT: The user has invoked", "[IMPORTANT: You are running as a scheduled cron job",
           "[IMPORTANT: Background process", "[INTERNAL NOTIFICATION", "[Cron delivery:",
           "Gateway message origin", "[OUT-OF-BAND USER MESSAGE")
prose = []
for r in rows:
    c = (r["content"] or "").lstrip()
    if any(c.startswith(m) for m in MACHINE):
        continue
    if (r["source"] or "").startswith("cron") or r["source"] == "subagent":
        continue
    prose.append(r)
in_bound = [r for r in rows if r["act"] is not None and start <= float(r["act"]) <= end]
print(f"user rows (active=1) in window     : {len(rows)}"
      f"   from {len({r['session_id'] for r in rows})} distinct session(s)")
print(f"  row's session bound ALSO in window : {len(in_bound)}")
print(f"  row's session bound outside window : {len(rows)-len(in_bound)}"
      "  (a gateway carrier session whose bound is stale, or this run)")
print(f"  machine-authored         : {len(rows)-len(prose)}  (cron task prompts + [Cron delivery:] rows)")
print(f"  OPERATOR PROSE           : {len(prose)}")
print("window-non-empty assertion : " + ("PASS" if len(sess) and len(rows) else "FAIL"))
tot = con.execute("SELECT COUNT(*) FROM messages WHERE timestamp>=? AND timestamp<=?",
                  (start, end)).fetchone()[0]
print(f"all rows in window (any role)      : {tot}   (the window is non-empty; the"
      " 13 user rows above are the only human-transport candidates)")
con.close()
PY
)"
  printf '%s\n' "$PY_OUT" | norm

  rule
  say "## 2. Skill source parity — read-only --check (never regenerates)"
  say "cmd: python3 ops/scripts/manage/check-skill-drift-parity.py --check"
  PAR_OUT="$(python3 ops/scripts/manage/check-skill-drift-parity.py --check 2>&1)"
  PAR_RC=$?
  printf '%s\n' "$PAR_OUT" | norm
  say "rc=$PAR_RC"
  if [[ "$PAR_RC" == 0 ]]; then
    say "verdict: PASS — this is the STRANDED direction only. §6 reads the"
    say "         doctor's own Skill drift line, which measures the opposite"
    say "         (repo-ahead) direction; a PASS here is not a deploy being"
    say "         current, so both are captured."
  else
    say "verdict: rc=$PAR_RC — see the tool's own report above."
  fi

  rule
  say "## 3. What this pass landed — the stale instruction, all 4 instances"
  say "The claim removed (byte-exact, extracted from the baseline revision, not"
  say "retyped from memory):"
  say "   cmd: git show $BASE_SHA:skills/devops/loop-governance/SKILL.md | grep -F '<marker>'"
  B_LINE="$(git show "$BASE_SHA:skills/devops/loop-governance/SKILL.md" 2>/dev/null | grep -F "$OLD_MARKER" | head -1)"
  if [[ -n "$B_LINE" ]]; then
    printf '%s\n' "$B_LINE" | norm | cut -c1-420
  else
    say "   MARKER ABSENT at $BASE_SHA — nothing about the old wording is claimed."
  fi
  say ""
  say "Why it is wrong: it says the deployed copy's LOCATION makes the call"
  say "lock-free. The classifier does not look at the script's path — a"
  say "write-class call needs a RESOLVED GOVERNED REPO (a path-like argument on"
  say "the call, else the repo the SESSION already resolved). Measured below."
  say ""
  say "Instances corrected (grep -cF of the removed marker, must be 0 in each):"
  for f in skills/devops/loop-governance/SKILL.md \
           skills/devops/approval-gate-debugging/SKILL.md \
           ops/scripts/install/install-orch-crons.sh \
           ops/install/cron-manifest.yaml; do
    n="$(grep -cF "$OLD_MARKER" "$f" 2>/dev/null)"
    s="$(grep -cF 'stay lock-free' "$f" 2>/dev/null)"
    say "   $f :: '$OLD_MARKER'=${n:-0}  'stay lock-free'=${s:-0}"
  done
  say ""
  say "Tree-wide sweep (same two phrases, excluding evidence + archive):"
  REM="$(grep -rn -e 'stay lock-free' -e "$OLD_MARKER" skills docs ops 2>/dev/null \
          | grep -v '/.archive/' | grep -v '/evidence/' | wc -l)"
  say "   matching lines remaining : ${REM:-0}"
  say ""
  say "The rule the four files now carry (from the loop-governance copy):"
  grep -F 'A DEPLOYED copy is NOT lock-free' skills/devops/loop-governance/SKILL.md \
    | head -1 | norm | cut -c1-420 || say "   (absent — the fix did not land)"
  say ""
  say "The pass's OWN recipe gap, added to the skill this pass runs:"
  grep -F "dies on the enforcer's third block shape" skills/hermes-agent/soul-refinement/SKILL.md \
    | head -1 | norm | cut -c1-300 || say "   (absent)"

  rule
  say "## 4. The mechanism, measured — the old reason refuted"
  say "a) '~/.hermes-cortex is not a git repo' is TRUE, and irrelevant:"
  say "   cmd: git -C ~/.hermes-cortex rev-parse --show-toplevel"
  R1="$(git -C "$HOME/.hermes-cortex" rev-parse --show-toplevel 2>&1)"
  RC1=$?
  printf '%s\n' "$R1" | norm
  say "   rc=$RC1  (128 = not a repository, so the deployed path resolves no repo"
  say "   and cannot be the reason any call ever passed)"
  say ""
  say "b) the deployed-copy read DOES pass from a non-governed cwd — with a cycle"
  say "   open, which is what gives the SESSION its repo:"
  say "   cmd: python3 ~/.hermes-cortex/scripts/task-db.py list --repo ALL --claimable --limit 3"
  say "   (from cwd=~, run while this cycle holds its lock)"
  R2="$(cd "$HOME" && python3 "$HOME/.hermes-cortex/scripts/task-db.py" list --repo ALL --claimable --limit 3 2>&1)"
  RC2=$?
  printf '%s\n' "$R2" | norm
  say "   rc=$RC2"
  if [[ "$RC2" == 0 ]]; then
    say "   => the 'DEPLOYED copy' is not what made it work; the session's resolved"
    say "      repo is. Order (begin_change first) is the fix, not the path."
  else
    say "   => rc=$RC2: this run could NOT reproduce the positive case; the"
    say "      correction in §3 rests on the refusal shape only."
  fi
  say ""
  say "c) provenance of the REFUSAL side, labelled because it is NOT re-runnable"
  say "   from here: the refusal quoted in the cycle note — 'No governed repo"
  say "   could be resolved for this call' — was captured from this pass's FIRST"
  say "   tool call, before any repo was resolved. It cannot be re-produced in"
  say "   this artifact because the session now holds a lock; an independent"
  say "   measurement of the same shape was made by the orch-task-morning-pass job"
  say "   earlier the same day. Stated as provenance, not as a count measured here."

  rule
  say "## 5. Checks on the changed files"
  say "cmd: bash -n ops/scripts/install/install-orch-crons.sh"
  bash -n ops/scripts/install/install-orch-crons.sh 2>&1 | norm
  SYN_RC=${PIPESTATUS[0]}
  say "rc=$SYN_RC"
  say ""
  say "cmd: python-with-module.sh yaml <validator> ops/install/cron-manifest.yaml"
  say "     (bare python3 here has no PyYAML, so the repo's own resolver picks one)"
  YCHK="${YCHK:-${TMPDIR:-/tmp}/soul-yamlcheck-$$.py}"
  cat > "$YCHK" <<'PY'
import sys, yaml
doc = yaml.safe_load(open(sys.argv[1]))
jobs = doc.get("crons") or doc.get("jobs")
names = [j.get("name") for j in jobs if isinstance(j, dict)]
print("yaml ok: keys=%s jobs=%d" % (sorted(doc), len(names)))
print("orch-task-morning-pass present:", "orch-task-morning-pass" in names)
PY
  Y_OUT="$(bash ops/scripts/lib/python-with-module.sh yaml "$YCHK" ops/install/cron-manifest.yaml 2>&1)"
  Y_RC=$?
  printf '%s\n' "$Y_OUT" | norm
  say "rc=$Y_RC  (3 would mean no interpreter could import yaml)"
  rm -f "$YCHK"
  say ""
  say "cmd: adversarial-verify.py --file ops/scripts/install/install-orch-crons.sh --level A4 --gate"
  AV_OUT="$(python3 "$HOME/.hermes-cortex/scripts/adversarial-verify.py" \
              --file ops/scripts/install/install-orch-crons.sh --level A4 --gate 2>&1)"
  AV_RC=$?
  printf '%s\n' "$AV_OUT" | norm | grep -E 'Summary|GATE|finding' || printf '%s\n' "$AV_OUT" | norm
  say "rc=$AV_RC"
  say ""
  say "cron_manifest.py --check — the orphan count is PRE-EXISTING, not this"
  say "range's. The baseline revision is extracted into a worktree and the same"
  say "check is run on BOTH sides; the baseline is ASSERTED to be the pre-change"
  say "revision by the marker the fix removed."
  if git worktree add --detach "$WT" "$BASE_SHA" >/dev/null 2>&1; then
    got="$(git -C "$WT" rev-parse --short=8 HEAD 2>/dev/null)"
    say "   baseline worktree HEAD : $got   (asserted == $BASE_SHA)"
    if [[ "$got" == "$BASE_SHA" ]]; then
      b_mark="$(grep -cF "$OLD_MARKER" "$WT/skills/devops/loop-governance/SKILL.md" 2>/dev/null)"
      say "   baseline carries the removed marker : ${b_mark:-0} (must be >=1, else"
      say "     the extraction is not the pre-change revision and nothing is claimed)"
      B_CNT="$(cd "$WT" && python3 ops/scripts/manage/cron_manifest.py --check 2>&1 | grep -c ORPHAN)"
      M_CNT="$(python3 ops/scripts/manage/cron_manifest.py --check 2>&1 | grep -c ORPHAN)"
      say "   ORPHAN lines at $BASE_SHA : $B_CNT"
      say "   ORPHAN lines in working tree     : $M_CNT"
      if [[ "$B_CNT" == "$M_CNT" ]]; then
        say "   => identical, so the check's rc=1 predates this range. It is NOT"
        say "      evidence about this change in either direction."
      else
        say "   => DIFFERS, and the difference is NOT attributed: re-run at the"
        say "      pinned baseline before concluding anything."
      fi
    else
      say "   comparison NOT RUN — the worktree did not resolve to $BASE_SHA;"
      say "   nothing claimed."
    fi
  else
    say "   comparison NOT RUN — worktree creation failed (network/git state);"
    say "   the pre-existence of the orphan count is NOT established here."
  fi

  rule
  say "## 6. The gate's own verdict (deploy happens AFTER this capture)"
  say "cmd: python3 ops/scripts/manage/cortex-doctor.py --quiet"
  DOC_OUT="$(timeout 300 python3 ops/scripts/manage/cortex-doctor.py --quiet 2>&1)"
  DOC_RC=$?
  printf '%s\n' "$DOC_OUT" | norm | grep -E 'Skill drift|Overall:|UNDISPOSED' || say "   (no verdict lines matched)"
  say "doctor rc=$DOC_RC (rc=1 while warnings stand; the per-check lines above"
  say "  are the verdicts and are captured with their counts)"

  rule
  say "## 7. Leftovers — DECIDED, not deferred"
  for p in docs/evidence/morning-task-pass-2026-10-25 \
           docs/evidence/weekly-dream-content-2026-10-24.md.tmp; do
    if [[ -e "$p" ]]; then
      say "   $p"
      say "      untracked, NOT this pass's: another session's in-flight work."
      say "      decision: reported by path, left untouched — landing or deleting"
      say "      a peer's file needs their action or operator approval (SOUL P9/P7)."
    else
      say "   $p — absent at run time (resolved by its owner)."
    fi
  done

  rule
  say "## 8. Tree state at run time"
  git status --short | norm
  say "(untracked entries are §7's peers' work, named rather than described so"
  say " the lines above stay checkable)"

  rule
  say "done"
} > "$OUT" 2>&1

echo "wrote $OUT ($(wc -l < "$OUT") lines)"
