#!/usr/bin/env bash
# Generate docs/evidence/skills-loadability-gate-2026-10-22.txt
#
# Proves the new doctor check DISCRIMINATES: it must FAIL on the pre-change tree
# and PASS on the fixed one. A check verified only on the healthy input is a happy
# path with a name; only a demonstrated failure shows it would NOTICE a regression.
#
# SELF-CONTAINED: the probe is an embedded heredoc, so this file re-runs on its
# own with nothing but the cortex venv. It writes the committed artifact itself.
#
# Re-run:  bash docs/evidence/skills-loadability-gate-2026-10-22.sh
set -uo pipefail

SELF="${BASH_SOURCE[0]}"
REPO="$(cd "$(dirname "$SELF")/../.." && pwd)"
OUT="$REPO/docs/evidence/skills-loadability-gate-2026-10-22.txt"
BASE="d4cf306e15bafef23a02d56da149717c483f5a2e"   # pinned literal; pre-fix revision
WORK="$(mktemp -d "${TMPDIR:-/tmp}/skillsgate.XXXXXX")"
export WORK
PY="$HOME/.hermes-cortex/venv/bin/python3"

norm() { awk -v w="$WORK" '{gsub(w, "$WORK"); print}' | sed -e "s#$HOME#~#g" -e 's/\x1b\[[0-9;]*m//g'; }
say() { printf '%s\n' "$*"; }

cat > "$WORK/probe.py" <<'PYEOF'
"""Run the doctor's own check against a tree and report its verdicts.

Read-only. argv[1] = repo root to point CORTEX_REPO at.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[3]) / "ops" / "scripts" / "manage"))
from cortex_doctor import checks            # noqa: E402
from cortex_doctor.results import Results   # noqa: E402

checks.CORTEX_REPO = Path(sys.argv[1])
res = Results()
checks.check_skills_loadable(res)

fails = [c for c in res.checks if c["status"] == "FAIL"]
warns = [c for c in res.checks if c["status"] == "WARN"]
passes = [c for c in res.checks if c["status"] == "PASS"]
infos = [c for c in res.checks if c["status"] == "INFO"]
print(f"  FAIL={len(fails)}  WARN={len(warns)}  PASS={len(passes)}  INFO={len(infos)}")
for c in fails[:4]:
    print(f"    FAIL: {c['detail'][:110]}")
if len(fails) > 4:
    print(f"    ... and {len(fails) - 4} more FAIL line(s)")
for c in warns:
    print(f"    WARN: {c['detail'][:110]}")
for c in passes:
    print(f"    PASS: {c['detail'][:110]}")
for c in infos:
    print(f"    INFO: {c['detail'][:110]}")
sys.exit(1 if fails else 0)
PYEOF

exec > >(norm > "$OUT") 2>&1

say "command : bash docs/evidence/skills-loadability-gate-2026-10-22.sh"
say "when    : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "base    : $BASE  (pinned literal; the pre-change revision)"
say "captured-at: $(git -C "$REPO" rev-parse HEAD)"
say "check   : cortex_doctor.checks.check_skills_loadable (registered in cli.py)"
say "note    : volatile by design — host paths normalised to ~, scratch dir to \$WORK,"
say "          ANSI stripped. 'captured-at' is the revision the tree sat on when this"
say "          ran; the file is written afterwards, so it cannot name its own commit."
say ""

say "=== 1. materialise the BASE (pre-change) skills tree ==="
mkdir -p "$WORK/base"
if ! git -C "$REPO" archive --format=tar "$BASE" skills | tar -x -C "$WORK/base"; then
  say "comparison NOT RUN, nothing claimed"
  rm -rf "$WORK"; exit 2
fi
say "  base SKILL.md count: $(find "$WORK/base/skills" -name SKILL.md | wc -l)"
say ""
say "  ASSERT the extraction really is pre-change: the fixed stubs carry"
say "    description: \"DEPRECATED alias — merged into cortex-bus. Load cortex-bus instead.\""
MARK='description: "DEPRECATED alias — merged into cortex-bus. Load cortex-bus instead."'
n=$(grep -rlF "$MARK" "$WORK/base/skills" 2>/dev/null | wc -l)
say "  files carrying it at BASE: $n  (must be 0)"
if [ "$n" -ne 0 ]; then
  say "ASSERTION FAILED — comparison NOT RUN, nothing claimed"
  rm -rf "$WORK"; exit 2
fi

say ""
say "=== 2. the check against the PRE-CHANGE tree (must FAIL) ==="
"$PY" "$WORK/probe.py" "$WORK/base" x "$REPO"
base_rc=$?
say "  rc=$base_rc   (1 = FAIL lines present, which is the point)"

say ""
say "=== 3. the check against the CURRENT repo tree (must PASS) ==="
"$PY" "$WORK/probe.py" "$REPO" x "$REPO"
cur_rc=$?
say "  rc=$cur_rc   (0 = no FAIL lines)"

say ""
say "=== 4. the check's own tests ==="
bash "$REPO/tests/run-tests.sh" "$REPO/tests/test_skills_loadable_check.py" -q 2>&1 | tail -3
say "  rc=${PIPESTATUS[0]}"

say ""
say "=== 5. the same check under an interpreter with NO PyYAML (the real default) ==="
say "  the doctor is documented as 'python3 <script>', and on this host python3 is"
say "  $(command -v python3)"
say "  which cannot import yaml — so the check must REPORT the degradation, never"
say "  report a PASS over files it could not read."
command -v python3
python3 -c "import yaml" 2>&1 | tail -1
python3 "$WORK/probe.py" "$REPO" x "$REPO"
deg_rc=$?
say "  rc=$deg_rc   (0 = no FAIL lines; the WARN is the degradation notice)"

say ""
say "=== verdict ==="
say "  pre-change tree : rc=$base_rc   (FAILs — the check NOTICES the defect class)"
say "  current tree    : rc=$cur_rc   (clean — no false alarm on a healthy tree)"
say "  yaml-less python: rc=$deg_rc   (no FAIL, but a WARN naming the skipped rules)"
say ""
say "  The directions together are the evidence: a green run alone would prove only"
say "  that the check is quiet, and quiet is also what a deleted check does. And a"
say "  run under an interpreter missing PyYAML proves the degradation is ANNOUNCED:"
say "  the first cut of this check reported 'unchecked=383' alongside a PASS line"
say "  claiming all 383 skills passed — a green tick over files it never read."
say "  Read-only: none of these runs writes to the tree it measures."

rm -rf "$WORK"
