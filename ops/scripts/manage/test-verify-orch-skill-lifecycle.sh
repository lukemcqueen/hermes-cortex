#!/usr/bin/env bash
# test-verify-orch-skill-lifecycle.sh — probe the probe.
#
# Induces ONE failure per case in a throwaway overlay and asserts
# verify-orch-skill-lifecycle.sh NOTICES (non-zero exit, or an explicit
# COULD NOT VERIFY for the unverifiable cases). A check that stays green on a
# broken input is a blind spot and fails this harness.
#
# Run: bash ops/scripts/manage/test-verify-orch-skill-lifecycle.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK="$HERE/verify-orch-skill-lifecycle.sh"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/vosl-probe.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
pass=0; blind=0

probe() { # name, expected (fail|could-not-verify), setup-cmd, env...
  local name="$1" expect="$2" setup="$3"; shift 3
  local root="$TMP/$name"; mkdir -p "$root/repo/ops/scripts/manage" "$root/deployed"
  # minimal overlay: real repo scripts, fake trees
  env REPO="$root/repo" DEPLOYED="$root/deployed" SKILLS="probe-skill" "$setup" "$root" >/dev/null 2>&1
  local out rc
  out="$(env REPO="$root/repo" DEPLOYED="$root/deployed" SKILLS="probe-skill" \
         PATH="$PATH" "$@" bash "$CHECK" 2>&1)"; rc=$?
  case "$expect" in
    fail)
      if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
        echo "  OK   $name -> rc=$rc (noticed)"; pass=$((pass+1))
      elif [ "$rc" -eq 2 ]; then
        echo "  OK   $name -> rc=2 COULD NOT VERIFY (noticed, not silently green)"; pass=$((pass+1))
      else
        echo "  BLIND $name -> rc=0, the check stayed green on a broken input"; blind=$((blind+1))
      fi ;;
    could-not-verify)
      if printf '%s' "$out" | grep -q 'COULD NOT VERIFY'; then
        echo "  OK   $name -> COULD NOT VERIFY"; pass=$((pass+1))
      else
        echo "  BLIND $name -> no COULD NOT VERIFY in output"; blind=$((blind+1))
      fi ;;
  esac
}

mk_repo() { # $1=root — copy the real checker so only the DATA is faked
  local r="$1"
  cp "$HERE/verify-orch-skill-lifecycle.sh" "$r/repo/ops/scripts/manage/"
  mkdir -p "$r/repo/skills/devops/probe-skill" "$r/deployed/devops/probe-skill"
}
# The checker locates its scripts via $REPO. Run the COPIED checker with a PATH
# shim, so each probe's stubs are what actually execute — and every probe uses a
# check identical in behaviour to the committed one.
run_check() { # $1=root  — run the COPIED checker with $REPO/$DEPLOYED pointed at the overlay
  local r="$1"
  env REPO="$r/repo" DEPLOYED="$r/deployed" SKILLS="${SKILLS:-probe-skill}" \
      bash "$r/repo/ops/scripts/manage/verify-orch-skill-lifecycle.sh" 2>&1
}

# The harness' own copy of verify-orch-skill-lifecycle.sh lives in $HERE (symlink-
# resolved, so cp works). mk_repo copies the REAL scripts; the stub trees below
# overwrite them per-probe. Build each stub once, with a self-contained loop.
mk_stub_recon() { # $1=path  $2="stranded: N" — the checker runs these via `python3 <path>`
  mkdir -p "$(dirname "$1")"
  { printf 'import sys\n'
    printf 'print("Detector verdict: PASS - %s")\n' "$2"
  } > "$1"
  python3 "$1" >/dev/null 2>&1 || { echo "HARNESS BUG: recon stub not runnable" >&2; exit 1; }
}
mk_stub_doctor() { # $1=path  $2=drift text — emits >=100 lines so the run-evidence bar is met
  mkdir -p "$(dirname "$1")"
  { printf 'print("  %s")\n' "$2"
    printf 'for _ in range(120): print("  x")\n'
  } > "$1"
  n=$(python3 "$1" 2>/dev/null | wc -l)
  [ "$n" -ge 100 ] || { echo "HARNESS BUG: doctor stub emits $n lines" >&2; exit 1; }
}

# ---- case 1: healthy tree -> PASS -------------------------------------------
r1="$TMP/green"; mkdir -p "$r1/repo/ops/scripts/manage" "$r1/deployed"; mk_repo "$r1"
echo "hello" > "$r1/repo/skills/devops/probe-skill/SKILL.md"
echo "hello" > "$r1/deployed/devops/probe-skill/SKILL.md"
mk_stub_doctor "$r1/repo/ops/scripts/manage/cortex-doctor.py" "✅ Skill drift — stub"
mk_stub_recon "$r1/repo/ops/scripts/manage/reconcile-stranded-skills.py" "stranded: 0"
# prove the harness' own stubs are trustworthy BEFORE trusting the probes
[ "$(python3 "$r1/repo/ops/scripts/manage/cortex-doctor.py" | wc -l)" -ge 100 ] \
  && echo "  OK   stub doctor emits >=100 lines" \
  || { echo "  HARNESS BUG: stub doctor too short"; exit 1; }

echo "probe 1: green tree"
out="$(run_check "$r1")"; rc=$?
if [ "$rc" -eq 0 ]; then echo "  OK   green -> rc=0"; pass=$((pass+1)); else echo "  BLIND green tree did not pass: $out"; blind=$((blind+1)); fi

echo "probe 2: deployed copy diverges (a deploy is outstanding)"
echo "changed" > "$r1/deployed/devops/probe-skill/SKILL.md"
out="$(run_check "$r1")"; rc=$?
if [ "$rc" -eq 1 ]; then echo "  OK   divergence -> rc=1 (FAIL, a deploy is outstanding)"; pass=$((pass+1)); else echo "  BLIND divergence rc=$rc (expected 1, not 2-unverifiable): $out"; blind=$((blind+1)); fi

echo "probe 3: reconciler crashes (rc=3, no stranded line) -> COULD NOT VERIFY, never green"
r3="$TMP/rc3"; mkdir -p "$r3/repo/ops/scripts/manage" "$r3/deployed"; mk_repo "$r3"
echo h > "$r3/repo/skills/devops/probe-skill/SKILL.md"; echo h > "$r3/deployed/devops/probe-skill/SKILL.md"
mk_stub_doctor "$r3/repo/ops/scripts/manage/cortex-doctor.py" "✅ Skill drift — stub"
printf 'import sys\nprint("boom", file=sys.stderr)\nsys.exit(3)\n' > "$r3/repo/ops/scripts/manage/reconcile-stranded-skills.py"
chmod +x "$r3/repo/ops/scripts/manage/reconcile-stranded-skills.py"
out="$(run_check "$r3")"; rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q 'COULD NOT VERIFY: reconciler printed no'; then echo "  OK   reconciler crash -> COULD NOT VERIFY"; pass=$((pass+1)); else echo "  BLIND crash read as rc=$rc: $out"; blind=$((blind+1)); fi

echo "probe 4: doctor runs but never prints a per-check verdict -> COULD NOT VERIFY"
r4="$TMP/trunc"; mkdir -p "$r4/repo/ops/scripts/manage" "$r4/deployed"; mk_repo "$r4"
echo h > "$r4/repo/skills/devops/probe-skill/SKILL.md"; echo h > "$r4/deployed/devops/probe-skill/SKILL.md"
{ printf 'for _ in range(120): print("  not a check line")\n'; } > "$r4/repo/ops/scripts/manage/cortex-doctor.py"
mk_stub_recon "$r4/repo/ops/scripts/manage/reconcile-stranded-skills.py" "stranded: 0"
chmod +x "$r4/repo/ops/scripts/manage/cortex-doctor.py"
out="$(run_check "$r4")"; rc=$?
if [ "$rc" -eq 2 ] && printf '%s' "$out" | grep -q 'COULD NOT VERIFY'; then echo "  OK   doctor without a verdict line -> COULD NOT VERIFY"; pass=$((pass+1)); else echo "  BLIND verdict-less doctor read as rc=$rc: $out"; blind=$((blind+1)); fi

echo "probe 5: stranded: 6 (content only on the deployed tree) while the verdict line still says PASS"
r5="$TMP/stranded"; mkdir -p "$r5/repo/ops/scripts/manage" "$r5/deployed"; mk_repo "$r5"
echo h > "$r5/repo/skills/devops/probe-skill/SKILL.md"; echo h > "$r5/deployed/devops/probe-skill/SKILL.md"
mk_stub_doctor "$r5/repo/ops/scripts/manage/cortex-doctor.py" "✅ Skill drift — stub"
mk_stub_recon "$r5/repo/ops/scripts/manage/reconcile-stranded-skills.py" "stranded: 6"
out="$(run_check "$r5")"; rc=$?
if [ "$rc" -ne 0 ]; then echo "  OK   stranded:6 with PASS verdict -> rc=$rc (count judged, not the verdict word)"; pass=$((pass+1)); else echo "  BLIND stranded:6 stayed green"; blind=$((blind+1)); fi

echo "probe 6: deployed file missing entirely -> FAIL, not skipped"
r6="$TMP/nodep"; mkdir -p "$r6/repo/ops/scripts/manage" "$r6/deployed"; mk_repo "$r6"
echo h > "$r6/repo/skills/devops/probe-skill/SKILL.md"; rmdir "$r6/deployed/devops/probe-skill"
mk_stub_doctor "$r6/repo/ops/scripts/manage/cortex-doctor.py" "✅ Skill drift — stub"
mk_stub_recon "$r6/repo/ops/scripts/manage/reconcile-stranded-skills.py" "stranded: 0"
out="$(run_check "$r6")"; rc=$?
if [ "$rc" -eq 1 ]; then echo "  OK   missing deployed -> rc=1 (a real failure, not 'unverifiable')"; pass=$((pass+1)); else echo "  BLIND missing deployed rc=$rc (expected 1): $out"; blind=$((blind+1)); fi

echo "probe 7: archived-category reports are skipped, live ones are still judged"
# The collector walks INTO ~/.hermes/skills/.archive/ and reports retired skills as
# "[NEW] <name> (.archive)". Those have no repo source by design and must NOT
# redden the check. The filter must be NARROW: a genuinely repo-missing live skill
# reported in the SAME batch must STILL fail — otherwise the exclusion is a bypass.
# Drives the derivation path (no SKILLS= override) by pointing HOME at the overlay,
# since the enumerator reads $HOME/.hermes-cortex/state/learning-reports/*.md.
r7="$TMP/archived"; mkdir -p "$r7/repo/ops/scripts/manage" "$r7/deployed" "$r7/home/.hermes-cortex/state/learning-reports"
mk_repo "$r7"
# live skill present on BOTH sides
mkdir -p "$r7/repo/skills/devops/live-skill" "$r7/deployed/devops/live-skill"
echo h > "$r7/repo/skills/devops/live-skill/SKILL.md"
echo h > "$r7/deployed/devops/live-skill/SKILL.md"
# a skill deployed HERE but absent from the repo = the unapplied-work gap (case (a))
mkdir -p "$r7/deployed/devops/ghost-missing"
echo h > "$r7/deployed/devops/ghost-missing/SKILL.md"
mk_stub_doctor "$r7/repo/ops/scripts/manage/cortex-doctor.py" "✅ Skill drift — stub"
mk_stub_recon "$r7/repo/ops/scripts/manage/reconcile-stranded-skills.py" "stranded: 0"
now_iso="$(date -u '+%Y-%m-%dT%H:%M:%S+00:00')"
printf '{"text": "Learning Report — probehost\\nGenerated: %s\\nType: full\\n== Skills (3 changed) ==\\n  [NEW] live-skill (devops)\\n  [NEW] ghost-archived (.archive)\\n  [NEW] ghost-missing (devops)\\n"}' "$now_iso" \
  > "$r7/home/.hermes-cortex/state/learning-reports/probe-1.md"
out="$(env HOME="$r7/home" REPO="$r7/repo" DEPLOYED="$r7/deployed" \
        bash "$r7/repo/ops/scripts/manage/verify-orch-skill-lifecycle.sh" 2>&1)"; rc=$?
# (a) the .archive item must not appear in the checked set at all
if printf '%s' "$out" | grep -q 'ghost-archived'; then
  echo "  BLIND .archive item was judged: $out"; blind=$((blind+1))
# (b) the missing LIVE skill must still be checked and still FAIL
elif [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q 'ghost-missing' && printf '%s' "$out" | grep -q 'live-skill'; then
  echo "  OK   .archive skipped, live+missing still judged -> rc=1 (narrow filter)"; pass=$((pass+1))
else
  echo "  BLIND archived/missing mix rc=$rc: $out"; blind=$((blind+1))
fi

echo "probe 8: reported name is a CATEGORY dir in the repo (exists, no SKILL.md of its own) -> tolerated WARN, not FAIL"
# A repo category dir (e.g. skills/github/ holding commit-message/pr-review, no
# SKILL.md at its own level) is not a tracked skill; demanding a repo file for it
# is a false FAIL (the .archive parse filter above only catches the .archive
# suffix, not an unsuffixed category collision). Doctor Skill-drift + reconciler
# own real drift; FAIL on them, never on this shape.
r8="$TMP/catdir"; mkdir -p "$r8/repo/ops/scripts/manage" "$r8/deployed"; mk_repo "$r8"
mkdir -p "$r8/repo/skills/cat/probe-cat" "$r8/deployed/cat/probe-cat"   # dirs, no SKILL.md
mk_stub_doctor "$r8/repo/ops/scripts/manage/cortex-doctor.py" "✅ Skill drift — stub"
mk_stub_recon "$r8/repo/ops/scripts/manage/reconcile-stranded-skills.py" "stranded: 0"
out="$(SKILLS=probe-cat run_check "$r8")"; rc=$?
if [ "$rc" -eq 0 ]; then echo "  OK   category dir -> rc=0 (tolerated, not a repo skill)"; pass=$((pass+1)); else echo "  BLIND category dir rc=$rc (expected 0): $out"; blind=$((blind+1)); fi

echo
echo "probes run: 8 · noticed: $pass · blind spots: $blind"
[ "$blind" -eq 0 ] || { echo "HARNESS FAIL: $blind blind spot(s) — the check is not trustworthy"; exit 1; }
echo "HARNESS PASS: 8 probes, 0 blind spots"
