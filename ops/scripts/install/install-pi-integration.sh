#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  install-pi-integration.sh — Register the cortex SKILLS and the
#  ENFORCEMENT HOOKS for Pi at USER scope, so every Pi session in
#  every project gets them.
#
#  Problem: `hc harness install pi` wires ONE project (it copies the
#  extension into ./extensions and prints a run line with --skill and
#  --tools flags). That is right for a project, but it means the
#  skills and the enforcement hooks are re-copied and re-typed per
#  repo, and a Pi started anywhere else has neither. Pi already reads
#  user-scope config, so the SAME registration pattern that
#  install-pi-mcp.sh uses for the MCP servers applies to the rest:
#
#    ~/.pi/agent/settings.json
#      "extensions": [<cortex-context.ts>]   the enforcement hook
#      "skills":     [<cortex-skills dir>]   the curated always-set
#
#  What each half buys:
#    * extensions — cortex-context.ts owns the LIFECYCLE triggers
#      (turn_end checkpoint, before_agent_start restore) AND records
#      skill_view as gate evidence. The pre-commit reflexion gate asks
#      HC's store "did this session load skill X?"; with no writer a
#      Pi commit is REFUSED no matter how well the agent behaved.
#      MCP cannot provide either half (it is tool-call shaped).
#    * skills — Pi advertises name + description at startup and loads
#      the body on demand, so it must be pointed at a CURATED set.
#      The set is DERIVED from the skills manifest's `always:` section
#      (one definition, shared with Hermes) — never hand-typed here.
#
#  Governance (begin_change/end_change/…) is registered separately by
#  install-pi-mcp.sh (Pi >= 1.0 MCP client, ~/.pi/agent/mcp.json).
#  This script does not duplicate it: one implementation, one way in
#  per capability.
#
#  Usage:
#    bash install-pi-integration.sh            # add/update (idempotent)
#    bash install-pi-integration.sh --check    # is it all registered?
#    bash install-pi-integration.sh --remove   # remove ours only
#
#  macOS + Linux. Backs up settings.json first, preserves every other
#  key and the user's own extension/skill paths.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

PYTHON="${PYTHON:-$(command -v python3)}"
AGENT_DIR="${PI_AGENT_DIR:-${HOME}/.pi/agent}"
SETTINGS="${PI_SETTINGS_FILE:-${AGENT_DIR}/settings.json}"
CURATED_DIR="${PI_CORTEX_SKILLS_DIR:-${AGENT_DIR}/cortex-skills}"
HERMES_SKILLS="${HERMES_SKILLS_DIR:-${HOME}/.hermes/skills}"

# The deployed extension is the thing Pi loads; fall back to the repo copy
# when this host has not deployed yet (the warning below names the fix).
EXTENSION=""
for candidate in \
    "${HOME}/.hermes-cortex/harnesses/pi/extensions/cortex-context.ts" \
    "${HOME}/hermes-cortex/ops/install/harnesses/pi/extensions/cortex-context.ts"; do
  if [[ -f "$candidate" ]]; then EXTENSION="$candidate"; break; fi
done

# The skills manifest is the ONE source of the always-set.
MANIFEST=""
for candidate in \
    "${CORTEX_SKILLS_MANIFEST:-}" \
    "${HOME}/.hermes-cortex/skills.yaml" \
    "${HOME}/hermes-cortex/docs/templates/skills.yaml"; do
  if [[ -n "$candidate" && -f "$candidate" ]]; then MANIFEST="$candidate"; break; fi
done

MODE="add"
case "${1:-}" in
  --check|--list) MODE="check" ;;
  --remove|--uninstall) MODE="remove" ;;
  -h|--help) sed -n '2,50p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  "") ;;
  *) echo "install-pi-integration: unknown argument '$1' (try --check / --remove)" >&2; exit 2 ;;
esac

if [[ -z "$MANIFEST" ]]; then
  echo "install-pi-integration: skills manifest not found." >&2
  echo "  Looked for ~/.hermes-cortex/skills.yaml and the repo copy." >&2
  echo "  The manifest is the ONE source of the always-set — without it this" >&2
  echo "  would have to hand-type the list, which is the drift this avoids." >&2
  echo "  Fix: run cortex-update.sh (it deploys skills.yaml)." >&2
  exit 1
fi

if [[ "$MODE" != "remove" && -z "$EXTENSION" ]]; then
  echo "install-pi-integration: cortex-context.ts not found (deployed or repo)." >&2
  echo "  Fix: run cortex-update.sh, then this script." >&2
  exit 1
fi

if [[ "$MODE" != "check" ]]; then
  mkdir -p "$(dirname "$SETTINGS")"
  [[ -f "$SETTINGS" ]] && cp -p "$SETTINGS" "${SETTINGS}.bak.cortex"
fi

"$PYTHON" - "$MODE" "$SETTINGS" "$CURATED_DIR" "$MANIFEST" "$HERMES_SKILLS" "${EXTENSION:-}" <<'PYEOF'
import json, os, sys

mode, settings_path, curated_dir, manifest_path, skills_root, extension = sys.argv[1:7]

try:
    import yaml
except ImportError:
    print("install-pi-integration: PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(1)


def fail(msg, code=1):
    print(f"install-pi-integration: {msg}", file=sys.stderr)
    sys.exit(code)


def load_manifest():
    with open(manifest_path) as fh:
        data = yaml.safe_load(fh) or {}
    always = data.get("always") or []
    names = [s.get("name") for s in always if isinstance(s, dict) and s.get("name")]
    if not names:
        fail(f"manifest {manifest_path} declares no 'always:' skills — refusing to "
             "register an empty skill set (it would look wired and do nothing)")
    return names


def resolve_skill(name):
    """Find <skills_root>/*/<name>/SKILL.md — the dir Pi registers."""
    for entry in sorted(os.scandir(skills_root), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        candidate = os.path.join(entry.path, name)
        if os.path.isfile(os.path.join(candidate, "SKILL.md")):
            return candidate
    return None


def read_settings():
    if not os.path.exists(settings_path):
        return {}
    try:
        with open(settings_path) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"{settings_path} is not valid JSON ({exc}) — fix it first, "
             "this script will not overwrite a config it cannot read")
    return data if isinstance(data, dict) else {}


def write_settings(data):
    with open(settings_path, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def strip_ours(entries):
    return [e for e in entries
            if not (isinstance(e, str) and (e.startswith(curated_dir)
                                            or e.endswith("cortex-context.ts")))]


names = load_manifest()
data = read_settings()
exts = [e for e in data.get("extensions", []) if isinstance(e, str)]
skills = [e for e in data.get("skills", []) if isinstance(e, str)]

if mode == "check":
    problems = []
    if not any(e.endswith("cortex-context.ts") for e in exts):
        problems.append("extension not registered in settings.json")
    if not any(e.startswith(curated_dir) for e in skills):
        problems.append("curated skills dir not registered in settings.json")
    if not os.path.isdir(curated_dir):
        problems.append(f"curated skills dir missing: {curated_dir}")
    else:
        present = {e.name for e in os.scandir(curated_dir) if e.is_dir()}
        missing = [n for n in names if n not in present]
        if missing:
            problems.append(f"skills not registered: {', '.join(missing)}")
    if problems:
        for p in problems:
            print(f"  ✗ {p}")
        print("install-pi-integration: NOT registered")
        sys.exit(1)
    print(f"  ✓ extension registered, {len(names)} curated skills present")
    print("install-pi-integration: registered")
    sys.exit(0)

if mode == "remove":
    data["extensions"] = strip_ours(exts)
    data["skills"] = strip_ours(skills)
    write_settings(data)
    removed_dir = False
    if os.path.isdir(curated_dir):
        for entry in os.scandir(curated_dir):
            if entry.is_symlink() or entry.is_file():
                os.unlink(entry.path)
            else:
                import shutil
                shutil.rmtree(entry.path)
        os.rmdir(curated_dir)
        removed_dir = True
    print(f"Removed cortex registration from {settings_path} "
          f"(curated dir {'removed' if removed_dir else 'absent'})")
    sys.exit(0)

# ── add/update ───────────────────────────────────────────────────
missing = []
os.makedirs(curated_dir, exist_ok=True)
for name in names:
    target = resolve_skill(name)
    if target is None:
        missing.append(name)
        continue
    link = os.path.join(curated_dir, name)
    if os.path.islink(link):
        if os.path.realpath(link) == os.path.realpath(target):
            continue
        os.unlink(link)
    elif os.path.exists(link):
        import shutil
        shutil.rmtree(link)
    os.symlink(target, link)

if missing:
    fail("skills in the manifest's always-set were not found under "
         f"{skills_root}: {', '.join(missing)}\n"
         "  A partial set would silently under-load Pi. Fix the skill library "
         "(or cortex-update.sh) and re-run.")

# Prune links for skills that left the manifest — otherwise a stale link keeps
# a skill Pi loads but the manifest no longer sanctions.
for entry in os.scandir(curated_dir):
    if entry.is_symlink() and entry.name not in names:
        os.unlink(entry.path)

exts = [e for e in strip_ours(exts) if e != extension]
exts.append(extension)
skills = [e for e in strip_ours(skills) if e != curated_dir]
skills.append(curated_dir)
data["extensions"] = exts
data["skills"] = skills
write_settings(data)
print(f"Registered in {settings_path} (user scope — applies to EVERY Pi project):")
print(f"  extension: {extension}")
print(f"  skills:    {curated_dir}  ({len(names)} skills from {manifest_path})")
print("Restart any running Pi session (or /reload) to pick this up.")
PYEOF
