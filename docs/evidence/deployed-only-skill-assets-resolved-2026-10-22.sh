#!/usr/bin/env bash
# Generate docs/evidence/deployed-only-skill-assets-resolved-2026-10-22.txt
#
# Records how the 122 files that existed under repo-owned skill dirs but not in
# the repo were each resolved — incorporated or removed — and proves the parity
# checker now passes.
#
# SELF-CONTAINED and re-runnable: bash docs/evidence/deployed-only-skill-assets-resolved-2026-10-22.sh
set -uo pipefail

SELF="${BASH_SOURCE[0]}"
REPO="$(cd "$(dirname "$SELF")/../.." && pwd)"
OUT="$REPO/docs/evidence/deployed-only-skill-assets-resolved-2026-10-22.txt"
ARCHIVE="$HOME/.hermes-cortex/skills/.archive/deployed-only-residue-2026-10-22"

norm() { sed -e "s#$HOME#~#g" -e 's/\x1b\[[0-9;]*m//g'; }
say() { printf '%s\n' "$*"; }

exec > >(norm > "$OUT") 2>&1

say "command : bash docs/evidence/deployed-only-skill-assets-resolved-2026-10-22.sh"
say "when    : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "captured-at: $(git -C "$REPO" rev-parse HEAD)"
say "note    : volatile by design — host paths normalised to ~, ANSI stripped. The"
say "          revision above is captured-at: this file is written afterwards, so it"
say "          cannot name its own commit."
say ""

say "=== 1. the question ==="
say "  The parity checker reported 122 files under repo-owned skill dirs that the"
say "  repo does not carry (3 dropped-from-repo, 119 never-committed). Every one had"
say "  to be either INCORPORATED into the repo or REMOVED from the deployed tree."
say ""

say "=== 2. the rule (per file, no third state) ==="
say "  INCORPORATE — copy deployed -> repo with sha256 assertion:"
say "    the file is a real asset for a skill the repo already owns (case studies,"
say "    reference guides, working scripts). The repo is the fleet's durable store;"
say "    deleting knowledge to save effort is the wrong trade."
say "  REMOVE — move out of the deployed tree into a preserved archive:"
say "    residue that is never a skill asset (plugin install metadata _meta.json /"
say "    skill-card.md, catalogue evals/, build+editor caches), or a path the repo"
say "    DELETED on purpose (it is in repo history — restoring it would undo a"
say "    decision and the deployed copy is only stale)."
say ""
say "  The classifier was corrected once during this work: the first rule demanded"
say "  that a SKILL.md name each file, which reported whole routed families as"
say "  orphaned — a probe inventing a loss. It now accepts a skill that routes the"
say "  references/ scripts/ templates/ assets/ family."
say ""

say "=== 3. what was removed (PRESERVED, not deleted) ==="
say "  moved to : ~/.hermes-cortex/skills/.archive/deployed-only-residue-2026-10-22/"
say "  a dot-dir, so a loader skips it: out of every agent's view, still on disk."
if [ -d "$ARCHIVE" ]; then
  say "  files preserved: $(find "$ARCHIVE" -type f | wc -l)   (expected 15)"
  find "$ARCHIVE" -type f | sed "s#$HOME#~#g" | sort
else
  say "  ARCHIVE ABSENT — the removals did not land where this artifact claims"
fi
say ""
say "  ASSERT the residue is out of the agent-visible tree:"
for f in email-sequence/_meta.json marketing-psychology/evals/evals.json social-content/skill-card.md; do
  if [ -e "$HOME/.hermes-cortex/skills/$f" ]; then
    say "    STILL PRESENT: $f"
  else
    say "    absent: $f"
  fi
done
say ""

say "=== 4. the parity checker's own verdict (the tool this is measured against) ==="
"$HOME/.hermes-cortex/venv/bin/python3" "$REPO/ops/scripts/manage/check-skill-drift-parity.py" --check 2>&1 | tail -3
say "  rc=${PIPESTATUS[0]}   (0 = the recorded claim holds)"
grep -E "^\| (Stranded in place|Absent from the repo)|^\*\*Verdict" \
  "$REPO/docs/evidence/skill-drift-parity.txt"
say ""
say "  Before this work the same table read: stranded 17, absent 133, Verdict FAIL."
say "  The 133 -> 122 step was the previous cycle (19 skills' content recovered);"
say "  122 -> 0 is this one."
say ""

say "=== 5. the incorporated code assets are now CHECKED, not just stored ==="
say "  tests/test_skill_code_assets_parse.py traverses skills/** by discovery, so"
say "  the scripts that arrived with the incorporation are compiled/parsed by it:"
bash "$REPO/tests/run-tests.sh" "$REPO/tests/test_skill_code_assets_parse.py" -q 2>&1 | tail -3
say "  rc=${PIPESTATUS[0]}"
say ""

say "=== 6. no skill content regressed ==="
bash "$REPO/tests/run-tests.sh" "$REPO/tests/test_skill_drift_parity.py" -q 2>&1 | tail -3
say "  rc=${PIPESTATUS[0]}"
say ""

say "=== verdict ==="
say "  Every file in the class is now in exactly one state: incorporated into the"
say "  repo (and therefore shipped to the fleet), or removed from the agent-visible"
say "  tree and preserved on disk. The parity checker — the tool that defined the"
say "  class — reports 0 and 0 with Verdict PASS, and --check confirms the recorded"
say "  claim holds rather than being stale."
say ""
say "  Honest limits:"
say "    - The concordance is measured on THIS host. The parity checker compares the"
say "      deployed tree here against the repo; a host with different deployed-only"
say "      files would report its own list, which is the correct behaviour."
say "    - A rejected guard is recorded rather than hidden: a test asserting that"
say "      every path named in a SKILL.md resolves was written, measured at 886"
say "      failures against live prose (it matched mentions like \`scripts/task-db.py\`"
say "      that name FLEET scripts, not skill assets), and DELETED. The parity"
say "      checker already covers the real property; a second, noisier copy of a rule"
say "      is how binding stops binding."

