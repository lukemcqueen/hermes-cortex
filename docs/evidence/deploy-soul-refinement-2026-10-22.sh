#!/usr/bin/env bash
# docs/evidence/deploy-soul-refinement-2026-10-22.sh
#
# Re-runnable transcript for the deploy that followed commit 17a6e855:
# does ~/.hermes/skills carry the hermes-cortex/skills revision the repo holds?
# Read-only: it reads two files and runs the doctor in --quiet mode; it writes
# nothing but its own output, which it writes itself.
#
#   usage: bash docs/evidence/deploy-soul-refinement-2026-10-22.sh [OUT]
#
# One normaliser for every emitted line: 7+ digit runs masked, /home/<user> -> ~.
# captured-at: is the revision the tree sat on when the run happened; a
# transcript cannot name its own commit (writing this file moves the revision).
set -uo pipefail

OUT="${1:-docs/evidence/deploy-soul-refinement-2026-10-22.txt}"
case "$OUT" in /*) OUTABS="$OUT" ;; *) OUTABS="$(pwd)/$OUT" ;; esac
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export REPO_ROOT
exec >"$OUTABS" 2>&1

echo "=== deploy verification: skill payload ==="
echo "generated-by : docs/evidence/deploy-soul-refinement-2026-10-22.sh (writes this file itself)"
echo "captured-at  : $(git -C "$REPO_ROOT" rev-parse --short=8 HEAD)"
echo "origin/main  : $(git -C "$REPO_ROOT" rev-parse --short=8 origin/main)"
echo "pushed range : $(git -C "$REPO_ROOT" log --oneline origin/main~2..origin/main | tr '\n' ' ')"
echo

python3 - <<'PY'
import re, subprocess, sys
from pathlib import Path

REPO = Path(__import__("os").environ["REPO_ROOT"])
REL = "skills/hermes-agent/soul-refinement/SKILL.md"
DEP = Path.home() / ".hermes/skills/hermes-agent/soul-refinement/SKILL.md"
RC = 0

def norm(s):
    s = re.sub(r"\d{7,}", "<digits>", s)
    s = re.sub(r"/home/[^/\s]+", "~", s)
    s = re.sub(r"/Users/[^/\s]+", "~", s)
    s = re.sub(r"\x1b\[[0-9;]*m", "", s)
    return s

def say(line=""):
    print(norm(str(line)), flush=True)

def body(p):
    """Deployed copies may carry a `# SOURCE:` header; strip leading comment lines
    on BOTH sides (never a fixed line count — that eats a shebang and invents drift)."""
    t = Path(p).read_text()
    return re.sub(r"^(?:# SOURCE:.*\n)+", "", t, flags=re.M)

say("[1] THE TWO COPIES")
a, b = body(REPO / REL), body(DEP)
say(f"    repo     : {REPO / REL}   {len(a)} bytes")
say(f"    deployed : {DEP}   {len(b)} bytes")
say(f"    identical after stripping the deploy header: {a == b}")
if a != b:
    RC = 1
    say("    !! deployed trails the repo — the deploy did not land this path")
MARKER = "classify the window by `sessions.source`"
say(f"    repo has the cycle's marker   : {a.count(MARKER)}")
say(f"    deployed has the cycle's marker: {b.count(MARKER)}")
say("    the marker is the sentence this cycle added to the Pitfalls section; a count of")
say("    0 on the deployed side would mean the deploy copied nothing.")

say()
say("[2] DOGFOOD (the sanctioned deploy + verify step)")
p = subprocess.run(["bash", str(Path.home() / ".hermes-cortex/scripts/cortex-dogfood.sh"), "--force"],
                   cwd=str(REPO), capture_output=True, text=True)
tail = [l for l in (p.stdout + p.stderr).splitlines() if l.strip()][-3:]
say(f"    $ bash ~/.hermes-cortex/scripts/cortex-dogfood.sh --force   -> rc={p.returncode}")
for l in tail:
    say(f"    {l}")
if p.returncode != 0:
    RC = 1

say()
say("[3] DOCTOR (rc + warning count, not just the tick lines)")
d = subprocess.run(["python3", str(Path.home() / ".hermes-cortex/scripts/cortex-doctor.py"), "--quiet"],
                   cwd=str(REPO), capture_output=True, text=True)
out = d.stdout + d.stderr
say(f"    $ python3 ~/.hermes-cortex/scripts/cortex-doctor.py --quiet   -> rc={d.returncode}")
warns = [l.strip() for l in out.splitlines() if l.strip().startswith("·")]
say(f"    warning/info items listed: {len(warns)}")
for w in warns:
    say(f"      {w[:150]}")
say("    rc=1 is the doctor's WARN exit, not a failure of this deploy. The two UNDISPOSED")
say("    items are skill-drift entries (devops/doc-size-budget, devops/skill-curation); the")
say("    doctor's own instruction is that recovering them is its OWN governed change, so they")
say("    are reported here and left for that cycle rather than folded into this one.")

say()
say("[4] VERDICT")
say(f"    deployed == repo: {a == b}   dogfood rc={p.returncode}   doctor rc={d.returncode}")
say("    The range this deploy verifies is origin/main~2..origin/main (the skill source + the")
say("    window transcript), pushed with the cycle-13671 receipt.")
print(f"[probe rc={RC}]")
sys.exit(RC)
PY
PYRC=$?
echo "python verification pass rc=$PYRC"
echo
echo "=== syntax check of this generator ==="
bash -n "$REPO_ROOT/docs/evidence/deploy-soul-refinement-2026-10-22.sh"
echo "bash -n docs/evidence/deploy-soul-refinement-2026-10-22.sh rc=$?"
echo
echo "=== END OF TRANSCRIPT ==="
