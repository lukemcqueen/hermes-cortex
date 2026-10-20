#!/usr/bin/env bash
# test-verify-stranded-skill-sync.sh — NEGATIVE harness for verify-stranded-skill-sync.sh.
#
# A green run proves the check works; only a demonstrated failure proves it would
# NOTICE a broken one. Each case induces exactly ONE failure and asserts the check
# reports it: non-zero exit AND a named reason. Runs in a throwaway tree so the
# live repo is never touched.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CHECK="$HERE/verify-stranded-skill-sync.sh"
[ -f "$CHECK" ] || { echo "harness: check script not found at $CHECK"; exit 2; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
probes=0; misses=0

mk_fixture() {
  # repo + deployed trees with a stub reconciler that prints a chosen count
  local count="$1"
  rm -rf "$TMP/fx"
  mkdir -p "$TMP/fx/repo/ops/scripts/manage" "$TMP/fx/repo/skills/devops/x" "$TMP/fx/deployed/devops/x"
  cat > "$TMP/fx/repo/ops/scripts/manage/reconcile-stranded-skills.py" <<PY
print("Detector verdict: FAIL · stranded: ${count}")
print("applied=0 need-review=0 missing=0")
PY
  printf '# x\n\n```sh\necho hi\n```\n' > "$TMP/fx/repo/skills/devops/x/SKILL.md"
  cp "$TMP/fx/repo/skills/devops/x/SKILL.md" "$TMP/fx/deployed/devops/x/SKILL.md"
}

run_case() {
  local name="$1" expect_rc="$2" want_reason="$3"; shift 3
  probes=$((probes+1))
  out="$("$@" 2>&1)"; rc=$?
  if [ "$rc" -eq "$expect_rc" ] && printf '%s' "$out" | grep -q "$want_reason"; then
    echo "PASS [$name]: rc=$rc, reason matched '$want_reason'"
  else
    echo "MISS [$name]: rc=$rc (wanted $expect_rc), reason '$want_reason' not found"
    printf '%s\n' "$out" | sed 's/^/      | /'
    misses=$((misses+1))
  fi
}

# --- probe 1: stranded count non-zero must FAIL by name
mk_fixture 3
run_case "stranded>0 fails" 1 "stranded=3" \
  env REPO="$TMP/fx/repo" DEPLOYED_ROOT="$TMP/fx/deployed" \
      SKILLS="devops/x/SKILL.md" bash "$CHECK"

# --- probe 2: deployed copy diverged must FAIL by name
mk_fixture 0
printf '# x\n\nCHANGED\n' > "$TMP/fx/deployed/devops/x/SKILL.md"
run_case "deployed drift fails" 1 "FAIL: devops/x/SKILL.md differs" \
  env REPO="$TMP/fx/repo" DEPLOYED_ROOT="$TMP/fx/deployed" \
      SKILLS="devops/x/SKILL.md" bash "$CHECK"

# --- probe 3: reconciler CRASH (rc=3) must be COULD NOT VERIFY, not a pass
mk_fixture 0
printf 'import sys\nsys.exit(3)\n' > "$TMP/fx/repo/ops/scripts/manage/reconcile-stranded-skills.py"
run_case "reconciler crash" 2 "COULD NOT VERIFY" \
  env REPO="$TMP/fx/repo" DEPLOYED_ROOT="$TMP/fx/deployed" \
      SKILLS="devops/x/SKILL.md" bash "$CHECK"

# --- probe 4: malformed reconciler output (no stranded line) -> unverifiable
mk_fixture 0
printf 'print("something else entirely")\n' > "$TMP/fx/repo/ops/scripts/manage/reconcile-stranded-skills.py"
run_case "malformed output" 2 "COULD NOT VERIFY" \
  env REPO="$TMP/fx/repo" DEPLOYED_ROOT="$TMP/fx/deployed" \
      SKILLS="devops/x/SKILL.md" bash "$CHECK"

# --- probe 5: missing deployed file must FAIL by name
mk_fixture 0
rm -f "$TMP/fx/deployed/devops/x/SKILL.md"
run_case "missing deployed file" 1 "deployed file missing" \
  env REPO="$TMP/fx/repo" DEPLOYED_ROOT="$TMP/fx/deployed" \
      SKILLS="devops/x/SKILL.md" bash "$CHECK"

# --- probe 6: odd fence count must FAIL by name
mk_fixture 0
printf '# x\n\n```sh\necho hi\n' > "$TMP/fx/repo/skills/devops/x/SKILL.md"
cp "$TMP/fx/repo/skills/devops/x/SKILL.md" "$TMP/fx/deployed/devops/x/SKILL.md"
run_case "odd fences fails" 1 "ODD fence count" \
  env REPO="$TMP/fx/repo" DEPLOYED_ROOT="$TMP/fx/deployed" \
      SKILLS="devops/x/SKILL.md" bash "$CHECK"

echo
echo "probing the probe: $probes probes, $misses blind spots"
[ "$misses" -eq 0 ] || exit 1
