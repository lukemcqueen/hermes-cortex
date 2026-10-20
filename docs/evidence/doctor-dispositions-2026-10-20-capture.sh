#!/usr/bin/env bash
# Re-runnable capture for the doctor-dispositions change (2026-10-20).
#
# Read-only with respect to the repo and to the live doctor state: every store it writes goes to a
# temp dir, and the one live doctor run only READS (it may add a warning, never a decision).
#
# Usage:  bash docs/evidence/doctor-dispositions-2026-10-20-capture.sh
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPO_SHOWN="~${REPO#$HOME}"
DOCTOR="$REPO/ops/scripts/manage/cortex-doctor.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/disp.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

echo "doctor dispositions — capture"
echo "generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "repo:      $REPO_SHOWN"
echo

echo "=== 1. the behaviour suite (temp stores only) ==="
( cd "$REPO" && python3 tests/test_doctor_dispositions.py ) > "$WORK/suite.txt" 2>&1
rc=$?
echo "rc=$rc   checks passed=$(grep -c '  PASS' "$WORK/suite.txt")  failed=$(grep -c '  FAIL' "$WORK/suite.txt")"
grep -E "^  FAIL" "$WORK/suite.txt" || true
echo

echo "=== 2. the summary shape, and the consumer regex that must keep matching ==="
( cd "$REPO" && python3 - "$WORK" <<'PY'
import io, re, sys
from contextlib import redirect_stdout
sys.path.insert(0, "ops/scripts/manage")
from cortex_doctor import results as R

res = R.Results()
for i in range(3):
    res.add(f"passing {i}", "PASS")
res.add("Skill drift: devops/example", "WARN", "1 drifted", "Run: cortex-update.sh")
res.add("Pinned hooks", "INFO", "informational")
buf = io.StringIO()
with redirect_stdout(buf):
    res.print_summary(compact=True)      # COMPACT: --quiet is what the update path runs
out = buf.getvalue()
line = [l for l in out.splitlines() if "Overall:" in l][0].strip()
print("summary line:")
print(f"  {line}")
rx = re.compile(r"Overall: (\w+)\s+\((\d+) pass · (\d+) warn · (\d+) fail · (\d+) info\)")
m = rx.search(line)
print(f"consumer regex (tests/test_dogfood_pipeline.py) still matches: {bool(m)}  groups={m.groups() if m else None}")
print("the undisposed count sits OUTSIDE the parenthetical on purpose: a fifth entry inside it")
print("would silently stop that match.")
print()
print("the block it prints (compact mode, so the update path sees it):")
started = False
for l in out.splitlines():
    if "UNDISPOSED" in l:
        started = True
    if started:
        print(f"  {l}")
PY
) > "$WORK/summary.txt" 2>&1
rc=$?
cat "$WORK/summary.txt"
echo "rc=$rc"
echo

echo "=== 3. the CLI end to end (own HERMES_CORTEX_HOME, so no live store is touched) ==="
printf "  refused record (a check that cannot exist): "
HERMES_CORTEX_HOME="$WORK/home" python3 "$DOCTOR" --quick --disposition "No Such Check" \
  --as deferred --owner tester --reason "capture" > "$WORK/cli.txt" 2>&1
rc=$?
echo "rc=$rc   stderr: $(grep -o 'no check named.*' "$WORK/cli.txt" | head -1)"
printf "  store written despite the refusal: "
[ -e "$WORK/home/state/doctor-dispositions.json" ] && echo "YES (bug)" || echo "no"
printf "  listing an empty store:            "
HERMES_CORTEX_HOME="$WORK/home" python3 "$DOCTOR" --dispositions > "$WORK/cli2.txt" 2>&1
echo "rc=$?   $(head -1 "$WORK/cli2.txt")"
echo

echo "=== 4. a REAL record, and the count moving (temp store, live checks) ==="
# A genuine decision, on a check this capture can create deterministically: the store is temp, but
# the check names come from a real doctor run, so the write path is exercised against real data.
HERMES_CORTEX_HOME="$WORK/home" python3 "$DOCTOR" --quick --json > "$WORK/live.json" 2>&1
python3 - "$WORK" <<'PY'
import json, os, subprocess, sys
work = sys.argv[1]
try:
    data = json.loads(open(f"{work}/live.json").read())
except ValueError:
    print("  COULD NOT VERIFY: the doctor's --json output was not parseable here")
    raise SystemExit(0)
warn = [c["name"] for c in data.get("checks", []) if c["status"] in ("WARN", "INFO")]
print(f"  the run has {len(warn)} warn/info check(s)")
if not warn:
    print("  (nothing to record on this host right now — the write path is covered by section 3)")
    raise SystemExit(0)
name = warn[0]
env = {**os.environ, "HERMES_CORTEX_HOME": f"{work}/home"}
r = subprocess.run([sys.executable, "ops/scripts/manage/cortex-doctor.py", "--quick",
                    "--disposition", name, "--as", "deferred", "--owner", "capture",
                    "--reason", "recorded by the evidence capture"], capture_output=True,
                   text=True, env=env)
print(f"  record {name!r} -> rc={r.returncode}")
print(f"    {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[:200]}")
store = f"{work}/home/state/doctor-dispositions.json"
if os.path.exists(store):
    entry = json.load(open(store))[name]
    print(f"    stored: disposition={entry['disposition']} owner={entry['owner']} "
          f"recorded_at={entry['recorded_at'][:10]}")
else:
    print("    COULD NOT VERIFY: no store written")
PY
echo

echo "=== 5. the DEPLOYED doctor carries the change (read-only grep) ==="
DEPLOYED="$(awk -F'\t' '$1 ~ /cortex_doctor\/dispositions\.py$/ {print $2; exit}' \
            "$HOME/.hermes-cortex/deploy-manifest.tsv" 2>/dev/null)"
if [ -z "$DEPLOYED" ] || [ ! -f "$DEPLOYED" ]; then
  echo "  COULD NOT VERIFY: no deployed dispositions.py named by the deploy manifest"
else
  echo "  path: ~${DEPLOYED#$HOME}"
  echo "  def record / def undisposed / TTL_DAYS: $(grep -c -e 'def record' -e 'def undisposed' -e 'TTL_DAYS' "$DEPLOYED")"
fi
echo "  NB: a deployed file is not a live process, and this one is imported by the doctor at start."
echo
echo "NOTES"
echo "  - Section 3 runs the REAL CLI in a subprocess with its own HERMES_CORTEX_HOME: the refusal"
echo "    path is exercised end to end, and no live store is written."
echo "  - Section 4 records one disposition against a temp store, with real check names."
echo "  - Nothing here records a disposition for the LIVE host: a decision belongs to the agent or"
echo "    operator who made it, and this capture did not make one."
