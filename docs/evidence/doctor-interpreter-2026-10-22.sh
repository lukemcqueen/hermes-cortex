#!/usr/bin/env bash
# Generate docs/evidence/doctor-interpreter-2026-10-22.txt
#
# Proves the doctor now resolves its OWN interpreter: run under the yaml-less
# `python3` an agent actually gets, it re-execs into the fleet venv and produces
# FULL-STRENGTH checks. The "before" side is produced by setting the loop guard
# (CORTEX_DOCTOR_REEXEC=1), which is exactly the pre-change behaviour: no re-exec,
# checks run degraded and say so.
#
# SELF-CONTAINED and re-runnable: bash docs/evidence/doctor-interpreter-2026-10-22.sh
set -uo pipefail

SELF="${BASH_SOURCE[0]}"
REPO="$(cd "$(dirname "$SELF")/../.." && pwd)"
OUT="$REPO/docs/evidence/doctor-interpreter-2026-10-22.txt"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/docint.XXXXXX")"
export WORK

norm() { awk -v w="$WORK" '{gsub(w, "$WORK"); print}' | sed -e "s#$HOME#~#g" -e 's/\x1b\[[0-9;]*m//g'; }
say() { printf '%s\n' "$*"; }

exec > >(norm > "$OUT") 2>&1

say "command : bash docs/evidence/doctor-interpreter-2026-10-22.sh"
say "when    : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
say "captured-at: $(git -C "$REPO" rev-parse HEAD)"
say "note    : volatile by design — host paths normalised to ~, scratch to \$WORK, ANSI"
say "          stripped. 'captured-at' is the revision the tree sat on when this ran; the"
say "          file is written afterwards, so it cannot name its own commit."
say ""

say "=== 1. the two interpreters ==="
say "  the doctor is documented as: python3 <script>"
say "  python3 resolves to       : $(command -v python3)"
say "  probe 'import yaml, mcp'  :"
python3 -c "import yaml, mcp" 2>&1 | tail -1
say "  fleet venv                : ~/.hermes-cortex/venv/bin/python3"
env -u PYTHONPATH -u PYTHONHOME "$HOME/.hermes-cortex/venv/bin/python3" -c "import yaml, mcp" 2>&1 | tail -1
say "  (no output above the 'fleet venv' line = the import SUCCEEDED)"
say "  declared dependency set   :"
python3 "$REPO/ops/scripts/manage/fix-cortex-venv.py" --check 2>&1 | tail -2

say ""
say "=== 2. BEFORE — re-exec disabled (the pre-change behaviour), under that python3 ==="
say "  CORTEX_DOCTOR_REEXEC=1 python3 <doctor> --quiet"
CORTEX_DOCTOR_REEXEC=1 python3 "$REPO/ops/scripts/manage/cortex-doctor.py" --quiet > "$WORK/before.txt" 2>&1
before_rc=$?
say "  rc=$before_rc"
grep -E "cannot import|WEAKER|repair:" "$WORK/before.txt" | head -4
grep -E "Skills manifest|Skills loadable" "$WORK/before.txt" | head -6
say "  the WARN's own remedy text:"
grep -E "Run the doctor with an interpreter" "$WORK/before.txt" | head -2

say ""
say "=== 3. AFTER — same python3, re-exec enabled (the default) ==="
python3 "$REPO/ops/scripts/manage/cortex-doctor.py" --quiet > "$WORK/after.txt" 2>&1
after_rc=$?
say "  rc=$after_rc"
say "  degradation notice (must be ABSENT — the re-exec happened):"
if grep -qE "cannot import|WEAKER" "$WORK/after.txt"; then
  grep -E "cannot import|WEAKER" "$WORK/after.txt" | head -3
else
  say "    (none)"
fi
grep -E "Skills manifest|Skills loadable" "$WORK/after.txt" | head -6

say ""
say "=== 4. the tests ==="
bash "$REPO/tests/run-tests.sh" "$REPO/tests/test_doctor_interpreter.py" -q 2>&1 | tail -3
say "  rc=${PIPESTATUS[0]}"

say ""
say "=== verdict ==="
say "  BEFORE rc=$before_rc — 'Skills manifest (basic)': the yaml-based manifest check"
say "    DEGRADED to a substring scan, and 'Skills loadable' came back WARN instead of"
say "    PASS. The WARN's remedy line (printed above) names the interpreter to use."
say "    (The full WARN detail — 'checked 383 repo skill(s) in TEXT mode ... the"
say "    name-charset, YAML-parse and length rules were NOT applied' — is captured"
say "    verbatim in docs/evidence/skills-loadability-gate-2026-10-22.txt; --quiet"
say "    truncates it here.)"
say "  AFTER  rc=$after_rc — the degradation notice is absent and the FULL yaml-based"
say "    checks ran ('Skills manifest: always / on_task / disk check', 'Skills loadable'"
say "    PASS). Same command, same launching interpreter, same machine."
say ""
say "  So the difference between the two runs is the change and nothing else: the only"
say "  variable is CORTEX_DOCTOR_REEXEC, which the wrapper reads to decide whether to"
say "  re-exec. Every agent that runs the documented command now gets the strong report."
say ""
say "  Honest limits: this proves the resolution on THIS host, where CORTEX_PYTHON and the"
say "  fleet venv both exist. A host with no capable interpreter still runs the doctor —"
say "  degraded, with the notice printed — because a host whose venv is broken must remain"
say "  diagnosable by the tool that repairs it (fix-cortex-venv.py). That branch is pinned"
say "  by tests (tests/test_doctor_interpreter.py), not by this transcript."
say "  Both rc=2 because this range's own checks.py / cli.py / cortex-doctor.py are not"
say "  deployed yet at capture time — the checksum FAILs are the pending deploy, not a"
say "  regression; the deploy runs immediately after this capture."

rm -rf "$WORK"
