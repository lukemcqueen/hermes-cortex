#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  test_pi_registration_installer.sh — regression test for
#  ops/scripts/install/install-pi-integration.sh
#
#  The installer registers the cortex SKILLS and the ENFORCEMENT
#  HOOKS for Pi at USER scope, the same way install-pi-mcp.sh
#  registers the MCP servers: one file (~/.pi/agent/settings.json),
#  idempotent, preserving every key the user owns.
#
#  Proves:
#    1. `extensions` gets the cortex-context.ts path (the lifecycle
#       hook that records gate evidence for the pre-commit reflexion
#       gate — without it a Pi commit is refused).
#    2. `skills` gets a curated dir containing ONE entry per skill in
#       the manifest's `always:` section — derived, never hand-typed.
#    3. Every pre-existing key and every user-owned path survives.
#    4. Idempotent; --check exits 0; --remove strips only ours.
#    5. A missing manifest / extension FAILS LOUDLY (no silent partial
#       registration that looks complete).
#
#  Runs against a temp HOME — never touches the real ~/.pi.
#  Run:  bash tests/test_pi_registration_installer.sh
# ─────────────────────────────────────────────────────────────
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO/ops/scripts/install/install-pi-integration.sh"
FAILS=0

check() { # check <name> <0|1>
  if [[ "$2" == "1" ]]; then echo "  PASS  $1"; else echo "  FAIL  $1"; FAILS=$((FAILS+1)); fi
}

if [[ ! -f "$SCRIPT" ]]; then
  echo "  FAIL  installer exists at $SCRIPT"
  echo "installer missing — nothing else can be tested"
  exit 1
fi

TD="$(mktemp -d)"
trap 'rm -rf "$TD"' EXIT
export HOME="$TD/home"
mkdir -p "$HOME/.pi/agent" "$HOME/.hermes-cortex/harnesses/pi/extensions" "$HOME/.hermes/skills/workflow" "$HOME/.hermes/skills/software-development"

# A real deployed extension + a fake skills library (only names matter here).
touch "$HOME/.hermes-cortex/harnesses/pi/extensions/cortex-context.ts"
for s in task-start agent-flow reflexion-check change-checklist survey-before-action agent-contract test-driven-development; do
  if [[ "$s" == "task-start" ]]; then d="$HOME/.hermes/skills/workflow/$s"; else d="$HOME/.hermes/skills/software-development/$s"; fi
  mkdir -p "$d"; printf -- '---\nname: %s\ndescription: test\n---\n' "$s" > "$d/SKILL.md"
done

# The manifest is the ONE source of the always-set.
mkdir -p "$HOME/.hermes-cortex"
cat > "$HOME/.hermes-cortex/skills.yaml" <<'EOF'
always:
  - name: task-start
    why: first
  - name: agent-flow
    why: router
  - name: reflexion-check
    why: critique
  - name: change-checklist
    why: ship
  - name: survey-before-action
    why: preflight
  - name: agent-contract
    why: rules
  - name: test-driven-development
    why: iron law
EOF

# A pre-existing Pi config with user state, a user extension and a user skill.
cat > "$HOME/.pi/agent/settings.json" <<'EOF'
{
  "quiethStartup": "keepme",
  "extensions": ["~/my-own-ext.ts"],
  "skills": ["~/my-own-skill"]
}
EOF

export PI_MCP_FILE_IGNORED=1
bash "$SCRIPT" >/dev/null 2>&1
python3 - "$HOME/.pi/agent/settings.json" <<'EOF'
import json, os, sys
p = sys.argv[1]
d = json.load(open(p))
assert d["quiethStartup"] == "keepme", "unrelated key lost"
exts = d["extensions"]
assert "~/my-own-ext.ts" in exts, f"user extension lost: {exts}"
assert any(e.endswith("harnesses/pi/extensions/cortex-context.ts") for e in exts), \
    f"cortex extension not registered: {exts}"
skills = d["skills"]
assert "~/my-own-skill" in skills, f"user skill lost: {skills}"
curated = next((s for s in skills if s.endswith("cortex-skills")), None)
assert curated, f"no curated skills dir registered: {skills}"
d2 = os.path.expanduser(curated)
names = sorted(os.path.basename(x) for x in os.listdir(d2)) if os.path.isdir(d2) else []
want = ["agent-contract", "agent-flow", "change-checklist", "reflexion-check",
        "survey-before-action", "task-start", "test-driven-development"]
assert names == want, f"curated skills must be EXACTLY the manifest always-set: {names}"
for n in names:
    assert os.path.isfile(os.path.join(d2, n, "SKILL.md")), f"{n} not a skill dir"
EOF
check "run1: user keys/paths preserved + extension + curated always-set" "$([ $? -eq 0 ] && echo 1 || echo 0)"

BEFORE="$(python3 -c "import json;d=json.load(open('$HOME/.pi/agent/settings.json'));print(sorted(d['extensions']),sorted(d['skills']))")"
bash "$SCRIPT" >/dev/null 2>&1
AFTER="$(python3 -c "import json;d=json.load(open('$HOME/.pi/agent/settings.json'));print(sorted(d['extensions']),sorted(d['skills']))")"
check "run2: idempotent (no duplicate entries)" "$([ "$BEFORE" = "$AFTER" ] && echo 1 || echo 0)"

bash "$SCRIPT" --check >/dev/null 2>&1
check "--check exits 0 when registered" "$([ $? -eq 0 ] && echo 1 || echo 0)"

bash "$SCRIPT" --remove >/dev/null 2>&1
python3 - "$HOME/.pi/agent/settings.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
assert "~/my-own-ext.ts" in d.get("extensions", []), "user extension removed by --remove"
assert "~/my-own-skill" in d.get("skills", []), "user skill removed by --remove"
assert not any("cortex" in x for x in d.get("extensions", [])), f"cortex extension left: {d['extensions']}"
assert not any("cortex" in x for x in d.get("skills", [])), f"cortex skill left: {d['skills']}"
EOF
check "--remove strips only ours, keeps user entries" "$([ $? -eq 0 ] && echo 1 || echo 0)"

# Fail loudly, never silently-half-register: break the manifest.
mv "$HOME/.hermes-cortex/skills.yaml" "$HOME/.hermes-cortex/skills.yaml.bak"
set +e
OUT="$(bash "$SCRIPT" 2>&1)"; RC=$?
set -e
check "missing manifest → non-zero exit" "$([ "$RC" -ne 0 ] && echo 1 || echo 0)"
check "missing manifest → says why" "$(echo "$OUT" | grep -qi 'skills.yaml\|manifest' && echo 1 || echo 0)"
mv "$HOME/.hermes-cortex/skills.yaml.bak" "$HOME/.hermes-cortex/skills.yaml"

echo
if [[ "$FAILS" -eq 0 ]]; then echo "ALL PASS"; exit 0; else echo "$FAILS FAILURE(S)"; exit 1; fi
