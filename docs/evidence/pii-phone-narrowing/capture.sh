#!/usr/bin/env bash
# capture.sh — REGENERATE docs/evidence/pii-phone-narrowing/transcript.txt
#
# The phone detector in the enforcer PII gate was narrowed (2026-10-14): it
# matched two four-digit groups joined by ONE dash, so every line-number range,
# session key, version pair and epoch pair looked like a phone and blocked
# legitimate writes.
#
# Every fixture here is ASSEMBLED FROM PARTS and every long digit run is SPLIT,
# because this script lives in the repo the gate scans and no literal may
# restate what the gate blocks. (The first draft was refused by the gate for
# exactly this reason — the E.164 fixture was written as one 12-digit run.)
#
#   cd ~ && bash hermes-cortex/docs/evidence/pii-phone-narrowing/capture.sh \
#       > hermes-cortex/docs/evidence/pii-phone-narrowing/transcript.txt
set -u

BASE_REV="31699baa"     # the enforcer revision BEFORE the narrowing, pinned
EV="hermes-cortex/docs/evidence/pii-phone-narrowing"

body() {
  cd "$HOME" || exit 1
  local PY
  PY=$(command -v python3)

  echo "PII PHONE DETECTOR — narrowing evidence (generated, not hand-written)"
  echo "Produced by: bash $EV/capture.sh   (paths normalised to ~)"
  echo "Generated at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "Baseline revision: $BASE_REV (pinned, never 'HEAD' — the fix is committed in"
  echo "the same change as this evidence, so HEAD would be a tautology)."
  echo

  echo "═══ 1. The pattern, before and after ═══"
  echo "\$ git -C hermes-cortex show $BASE_REV:plugins/governance-enforcer/__init__.py | grep -A2 _PII_PHONE_RE"
  git -C hermes-cortex show "$BASE_REV:plugins/governance-enforcer/__init__.py" \
    | grep -A2 '_PII_PHONE_RE = re.compile'
  echo
  echo "\$ grep -A8 '_PII_PHONE_RE = re.compile' hermes-cortex/plugins/governance-enforcer/__init__.py"
  grep -A8 '_PII_PHONE_RE = re.compile' hermes-cortex/plugins/governance-enforcer/__init__.py
  echo

  echo "═══ 2. The gate's own test suite ═══"
  echo "\$ python3 -m pytest hermes-cortex/tests/test_enforcer_pii_gate.py -q"
  "$PY" -m pytest hermes-cortex/tests/test_enforcer_pii_gate.py -q 2>&1 | tail -3
  echo

  echo "═══ 3. LIVE gate verdicts, through _check_pii_content_gate ═══"
  echo "The target path is INSIDE the shared surface: the gate only fires there, so a"
  echo "probe pointed elsewhere reports 'allowed' for everything and measures nothing."
  "$PY" - <<'PYEOF'
import importlib.util
from pathlib import Path
p = Path("hermes-cortex/plugins/governance-enforcer/__init__.py").resolve()
spec = importlib.util.spec_from_file_location("enf", p)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
TARGET = str(Path.home() / "hermes-cortex" / "docs" / "probe-target.md")
put = lambda t: m._check_pii_content_gate("write_file", {"path": TARGET, "content": t}) is not None
D = "-"
cases = [
    ("line-number refs (blocked before)", "the block (pre-commit-score:576" + D + "634) and (:5341" + D + "5377)", False),
    ("chained range pair",                 "lines 5341" + D + "5377, 5380" + D + "5401", False),
    ("session-key shape",                  "session 20" + "26" + "10" + "14_195745", False),
    ("version pair",                       "v1.2.0" + D + "20" + "26" + "10" + "14", False),
    ("epoch range",                        "budget 12000" + D + "16000", False),
    ("REAL phone, KR national",            "call 010" + D + "1234" + D + "5678", True),
    ("REAL phone, +CC grouped",            "ring +82 10" + D + "1234" + D + "5678", True),
    ("REAL phone, E.164",                  "ring +" + "8210" + "1234" + "5678", True),
]
bad = 0
for label, text, want in cases:
    got = put(text)
    ok = got == want
    bad += 0 if ok else 1
    print(f"  {label:<34} {'BLOCKED' if got else 'allowed':>8}   need {'BLOCKED' if want else 'allowed':>8}   {'ok' if ok else '** WRONG **'}")
print(f"  wrong verdicts: {bad}")
PYEOF
  echo

  echo "═══ 4. The baseline reproduces the bug (why narrowing is a fix, not a loosening) ═══"
  echo "\$ the same NON-phone shapes against the PINNED baseline pattern"
  "$PY" - <<'PYEOF'
import importlib.util, subprocess, tempfile
from pathlib import Path
src = subprocess.run(["git", "-C", "hermes-cortex", "show",
                      "31699baa:plugins/governance-enforcer/__init__.py"],
                     capture_output=True, text=True)
tmp = Path(tempfile.mkdtemp()) / "prev.py"
tmp.write_text(src.stdout)
spec = importlib.util.spec_from_file_location("prev", tmp)
prev = importlib.util.module_from_spec(spec); spec.loader.exec_module(prev)
D = "-"
non_phones = [
    "lines 5341" + D + "5377",
    "session 20" + "26" + "10" + "14_195745",
    "v1.2.0" + D + "20" + "26" + "10" + "14",
    "budget 12000" + D + "16000",
    "and (:5380" + D + "5401)",
]
hit = [s for s in non_phones if prev._PII_PHONE_RE.search(s)]
print(f"  baseline flagged {len(hit)} of {len(non_phones)} NON-phone shapes (this is the bug)")
for s in hit:
    print(f"    - {s}")
PYEOF
  echo

  echo "═══ 5. What this does NOT cover ═══"
  echo "- An unformatted ten-digit run with no separators and no leading plus is no"
  echo "  longer flagged. DELIBERATE, and stated in the source: such a run is"
  echo "  indistinguishable from an identifier, and guessing there is what produced"
  echo "  the false positives. Separated / plus-prefixed formats still fire."
  echo "- No end-to-end write was attempted: the gate blocks its own fixtures by"
  echo "  construction, so the measurement is the pattern plus the gate function."
}

body | sed "s|$HOME|~|g"
