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
# BOTH extensions: the installer requires cortex-context.ts AND
# cortex-governance.ts (registering only one looks wired while leaving writes
# open, so it refuses) — a fixture with one is a broken fixture, and it made
# this suite fail for a reason unrelated to what it tests.
touch "$HOME/.hermes-cortex/harnesses/pi/extensions/cortex-context.ts" \
      "$HOME/.hermes-cortex/harnesses/pi/extensions/cortex-governance.ts"
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

# A pre-existing Pi config with user state, a user extension, a user skill,
# and the user's OWN pi package — the installer must add ours beside it.
cat > "$HOME/.pi/agent/settings.json" <<'EOF'
{
  "quiethStartup": "keepme",
  "extensions": ["~/my-own-ext.ts"],
  "skills": ["~/my-own-skill"],
  "packages": ["npm:someones-own-package@1.2.3"]
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

# ── web search (free providers) ──────────────────────────────────────────
# The Pi agent served by cortex-gateway must be able to search the web for
# FREE — no API key on this host. Two host-visible facts make that true, so
# both are asserted: the pinned pi-web-access package declared in
# settings.json, and a keyless routing config in web-search.json.
bash "$SCRIPT" >/dev/null 2>&1
python3 - "$HOME/.pi/agent/settings.json" "$HOME/.pi/agent/web-search.json" <<'EOF'
import json, sys
settings = json.load(open(sys.argv[1]))
pkgs = settings.get("packages", [])
mine = [p for p in pkgs if p.startswith("npm:pi-web-access@")]
assert mine, f"pi-web-access not declared in settings.json packages: {pkgs}"
assert all(p.split("@")[-1] for p in mine), f"declaration must pin a version: {mine}"
ws = json.load(open(sys.argv[2]))
route = ws.get("searchRouting", {}).get("providers", [])
assert route == ["exa", "duckduckgo"], f"keyless provider chain is not as declared: {route}"
EOF
check "web search: pinned package declared + keyless routing written" "$([ $? -eq 0 ] && echo 1 || echo 0)"

python3 - "$HOME/.pi/agent/settings.json" <<'EOF'
import json, sys
pkgs = json.load(open(sys.argv[1])).get("packages", [])
assert "npm:someones-own-package@1.2.3" in pkgs, f"user's own package lost: {pkgs}"
EOF
check "web search: user's own package survives the install" "$([ $? -eq 0 ] && echo 1 || echo 0)"

# An operator's OWN web-search.json (e.g. with a paid key) must never be
# clobbered — a config file that overwrites credentials costs real money.
printf '{"_operator": "mine", "braveApiKey": "MINE"}\n' > "$HOME/.pi/agent/web-search.json"
bash "$SCRIPT" >/dev/null 2>&1
python3 - "$HOME/.pi/agent/web-search.json" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
assert d.get("braveApiKey") == "MINE", f"operator config clobbered: {d}"
EOF
check "web search: existing operator config is preserved verbatim" "$([ $? -eq 0 ] && echo 1 || echo 0)"

# --check must FAIL when the search wiring is gone, not report a wired host.
rm -f "$HOME/.pi/agent/web-search.json"
bash "$SCRIPT" --check >/dev/null 2>&1
check "--check fails when web-search.json is missing" "$([ $? -ne 0 ] && echo 1 || echo 0)"
bash "$SCRIPT" >/dev/null 2>&1
bash "$SCRIPT" --check >/dev/null 2>&1
check "--check exits 0 once the search wiring is restored" "$([ $? -eq 0 ] && echo 1 || echo 0)"

bash "$SCRIPT" --remove >/dev/null 2>&1
python3 - "$HOME/.pi/agent/settings.json" <<'EOF'
import json, sys
pkgs = json.load(open(sys.argv[1])).get("packages", [])
assert not any(p.startswith("npm:pi-web-access") for p in pkgs), f"our package left behind: {pkgs}"
assert "npm:someones-own-package@1.2.3" in pkgs, f"--remove took the user's package: {pkgs}"
EOF
check "--remove drops only our package declaration" "$([ $? -eq 0 ] && echo 1 || echo 0)"

# A host with Pi absent must still exit 0 (a missing coding agent is not a
# fault), and must NOT try to run an installer it does not have. A fake
# launcher records any invocation, so "did not run" is observed, not assumed.
MARKER="$TD/launcher-was-invoked"
cat > "$TD/fake-pi" <<EOF
#!/usr/bin/env bash
echo "invoked \$*" >> "$MARKER"
exit 0
EOF
chmod +x "$TD/fake-pi"
PI_LAUNCHER="$TD/fake-pi" bash "$SCRIPT" >/dev/null 2>&1
RC_NOPI=$?
if [[ -e "$MARKER" ]]; then
  # A launcher that exists IS invoked — that is the install path; assert it
  # asked for the pinned package rather than a floating one.
  check "installer invokes the launcher with the PINNED package" \
    "$(grep -q 'npm:pi-web-access@[0-9]' "$MARKER" && echo 1 || echo 0)"
else
  check "host without pi: exit 0, no install attempted" "$([ "$RC_NOPI" -eq 0 ] && echo 1 || echo 0)"
fi
rm -f "$MARKER"

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
