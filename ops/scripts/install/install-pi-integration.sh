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
#      skill loads as gate evidence. The pre-commit reflexion gate asks
#      HC's store "did this session load skill X?"; with no writer a
#      Pi commit is REFUSED no matter how well the agent behaved.
#      The load it records is Pi's OWN mechanism — a `read` of the
#      skill's SKILL.md — not `skill_view`, which Pi does not have
#      (Pi's system prompt: "Use the read tool to load a skill's
#      file..."). MCP cannot provide either half (it is tool-call shaped).
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

PYTHON="${PYTHON:-}"
# Reading the manifest needs PyYAML, and a bare `python3` is usually the interpreter that
# LACKS it (measured on esther: the Hermes tools python has no yaml, and the fleet venv had
# none until it was filled). Choosing one by PATH existence and then failing with "PyYAML
# required" blames the host and skips the skills half — so ask the shared resolver which
# interpreter can actually import it, and never pick one on the strength of its path.
_RESOLVER="${HOME}/.hermes-cortex/scripts/lib/python-with-module.sh"
if [[ ! -f "$_RESOLVER" ]]; then
  _RESOLVER="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)/lib/python-with-module.sh"
fi
if [[ -z "$PYTHON" && -f "$_RESOLVER" ]]; then
  PYTHON="$(bash "$_RESOLVER" --print yaml 2>/dev/null || true)"
fi
PYTHON="${PYTHON:-$(command -v python3)}"
AGENT_DIR="${PI_AGENT_DIR:-${HOME}/.pi/agent}"
SETTINGS="${PI_SETTINGS_FILE:-${AGENT_DIR}/settings.json}"
CURATED_DIR="${PI_CORTEX_SKILLS_DIR:-${AGENT_DIR}/cortex-skills}"
HERMES_SKILLS="${HERMES_SKILLS_DIR:-${HOME}/.hermes/skills}"

# ── WEB SEARCH — the pi agent must be able to look things up online ────────
# Measured 2026-10-15: pi ships read/bash/edit/write/grep/find/ls and the five
# cortex MCP servers expose no search, so "research this" or "review this repo"
# had NO online path at all — the gateway-served agent included, because the
# gateway only spawns this same pi. pi-web-access adds web_search,
# source_check, fetch_content and get_search_content (URL/GitHub/PDF/YouTube).
#
# FREE, no API key: Exa's keyless MCP free tier first, DuckDuckGo's keyless
# HTML endpoint as the fallback. Both were reachability-probed from this host
# (mcp.exa.ai answered an MCP initialize; html.duckduckgo.com answered 202) and
# a real search returned real URLs. Version-PINNED because a pi package
# executes inside the agent: bumps go through the 14-day age gate
# (ops/scripts/health/check-package-age.py npm pi-web-access==<version>).
PI_WEB_SEARCH_PACKAGE="${PI_WEB_SEARCH_PACKAGE:-npm:pi-web-access@0.35.0}"
WEB_SEARCH_FILE="${PI_WEB_SEARCH_FILE:-${AGENT_DIR}/web-search.json}"
# The launcher is a symlink into a bin dir that need not be on PATH, so it is
# resolved by path (never `command -v` alone) — see the pi skill's "presence
# probe can be wrong about a managed install".
PI_LAUNCHER="${PI_LAUNCHER:-}"
if [[ -z "$PI_LAUNCHER" ]]; then
  if [[ -x "${AGENT_DIR}/bin/pi" ]]; then PI_LAUNCHER="${AGENT_DIR}/bin/pi"
  else PI_LAUNCHER="$(command -v pi 2>/dev/null || true)"; fi
fi

# The deployed extensions are the thing Pi loads; fall back to the repo copies
# when this host has not deployed yet (the warning below names the fix).
#
# TWO extensions, and they do different jobs:
#   cortex-context.ts    — the LIFECYCLE triggers (checkpoint/restore/evidence)
#   cortex-governance.ts — the WRITE GATE for pi's NATIVE tools. Hermes enforces
#                          at the tool level via its enforcer plugin; pi's
#                          read/bash/edit/write never cross that plugin, so
#                          without this file a pi session could edit and write
#                          with no governance lock at all (titus, 2026-10-14).
# Resolve each by name; a missing one is a wiring fault, never a silent skip.
resolve_ext() {
  for candidate in \
      "${HOME}/.hermes-cortex/harnesses/pi/extensions/$1" \
      "${HOME}/hermes-cortex/ops/install/harnesses/pi/extensions/$1"; do
    if [[ -f "$candidate" ]]; then printf '%s' "$candidate"; return 0; fi
  done
  return 1
}
EXTENSION="$(resolve_ext cortex-context.ts || true)"
GOVERNANCE_EXTENSION="$(resolve_ext cortex-governance.ts || true)"

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

if [[ "$MODE" != "remove" && ( -z "$EXTENSION" || -z "$GOVERNANCE_EXTENSION" ) ]]; then
  echo "install-pi-integration: a cortex extension was not found (deployed or repo)." >&2
  echo "  cortex-context.ts    : ${EXTENSION:-MISSING}" >&2
  echo "  cortex-governance.ts : ${GOVERNANCE_EXTENSION:-MISSING}" >&2
  echo "  Both are required — the second is what gates pi's native write tools," >&2
  echo "  and registering only one would look wired while leaving writes open." >&2
  echo "  Fix: run cortex-update.sh, then this script." >&2
  exit 1
fi

if [[ "$MODE" != "check" ]]; then
  mkdir -p "$(dirname "$SETTINGS")"
  [[ -f "$SETTINGS" ]] && cp -p "$SETTINGS" "${SETTINGS}.bak.cortex"
fi

"$PYTHON" - "$MODE" "$SETTINGS" "$CURATED_DIR" "$MANIFEST" "$HERMES_SKILLS" "${EXTENSION:-}" "${GOVERNANCE_EXTENSION:-}" "$PI_WEB_SEARCH_PACKAGE" "$WEB_SEARCH_FILE" <<'PYEOF'
import json, os, sys

(mode, settings_path, curated_dir, manifest_path, skills_root, extension,
 governance_extension, package_spec, web_search_file) = sys.argv[1:10]

# Every cortex-owned extension, by basename. ONE list: registration, the
# strip/replace path and the check all read it, so a new extension cannot be
# added to one and forgotten in another (the pre-2026-10-14 bug: the check
# asserted one filename, so a second extension looked wired and was not).
OURS = ("cortex-context.ts", "cortex-governance.ts")

# The pi package that gives the agent web_search/fetch_content. Matched by
# NAME, not by the pinned spec, so bumping the pin does not leave the old
# declaration behind (that is how a host ends up loading two versions).
OUR_PACKAGE_PREFIX = "npm:pi-web-access"

# The keyless provider chain written when the operator has no config of their
# own. Ordered: Exa's keyless MCP free tier, then DuckDuckGo's keyless HTML
# endpoint — both verified reachable and key-free on this fleet.
KEYLESS_PROVIDERS = ["exa", "duckduckgo"]

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
                                            or e.endswith(OURS)))]


names = load_manifest()
data = read_settings()
exts = [e for e in data.get("extensions", []) if isinstance(e, str)]
skills = [e for e in data.get("skills", []) if isinstance(e, str)]
packages = [p for p in data.get("packages", []) if isinstance(p, str)]


def read_web_search():
    """Parse web-search.json; None when absent, 'INVALID' when unparseable."""
    if not os.path.exists(web_search_file):
        return None
    try:
        with open(web_search_file) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return "INVALID"


def keyless_route_ok(cfg) -> bool:
    """Does this config give the agent a KEYLESS search path?

    Either an explicit chain naming at least one keyless provider, or a
    top-level provider that is keyless. A config that names only keyed
    providers is valid for its owner but is NOT a free setup, and on a host
    with no keys it fails at the first search — which is the failure this
    check exists to catch.
    """
    if not isinstance(cfg, dict):
        return False
    route = cfg.get("searchRouting", {}).get("providers", []) if isinstance(cfg.get("searchRouting"), dict) else []
    chosen = [p for p in route if isinstance(p, str)] or [cfg.get("provider")]
    return any(p in KEYLESS_PROVIDERS for p in chosen if isinstance(p, str))


if mode == "check":
    problems = []
    for wanted in OURS:
        if not any(e.endswith(wanted) for e in exts):
            problems.append(f"extension not registered in settings.json: {wanted}")
    if not any(e.startswith(curated_dir) for e in skills):
        problems.append("curated skills dir not registered in settings.json")
    if not os.path.isdir(curated_dir):
        problems.append(f"curated skills dir missing: {curated_dir}")
    else:
        present = {e.name for e in os.scandir(curated_dir) if e.is_dir()}
        missing = [n for n in names if n not in present]
        if missing:
            problems.append(f"skills not registered: {', '.join(missing)}")
    if not any(p.startswith(OUR_PACKAGE_PREFIX) for p in packages):
        problems.append(f"web search package not declared in settings.json "
                        f"(expected {package_spec}) — the agent has no web tool")
    cfg = read_web_search()
    if cfg is None:
        problems.append(f"web search not configured: {web_search_file} is missing "
                        f"(keyless chain {KEYLESS_PROVIDERS})")
    elif cfg == "INVALID":
        problems.append(f"web search config is not valid JSON: {web_search_file}")
    elif not keyless_route_ok(cfg):
        problems.append(f"web search has no keyless provider: {web_search_file} "
                        f"names none of {KEYLESS_PROVIDERS} — every search will "
                        f"fail on a host with no API key")
    if problems:
        for p in problems:
            print(f"  ✗ {p}")
        print("install-pi-integration: NOT registered")
        sys.exit(1)
    print(f"  ✓ extensions registered ({', '.join(OURS)}), "
          f"{len(names)} curated skills present")
    print(f"  ✓ web search: {package_spec} declared, "
          f"keyless chain {KEYLESS_PROVIDERS} configured")
    print("install-pi-integration: registered")
    sys.exit(0)

if mode == "remove":
    data["extensions"] = strip_ours(exts)
    data["skills"] = strip_ours(skills)
    # Only OUR declaration goes; the operator's own packages are theirs.
    data["packages"] = [p for p in packages if not p.startswith(OUR_PACKAGE_PREFIX)]
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

exts = strip_ours(exts)
for ext in (extension, governance_extension):
    # Idempotent: replace the entry for this path if present, else append. Both
    # extensions are registered in ONE pass so a second one cannot be dropped.
    exts = [e for e in exts if e != ext]
    if ext:
        exts.append(ext)
skills = [e for e in strip_ours(skills) if e != curated_dir]
skills.append(curated_dir)
data["extensions"] = exts
data["skills"] = skills
# Replace any earlier declaration of the SAME package (a pinned spec bumps by
# being written over, not appended beside) and keep the operator's own.
data["packages"] = [p for p in packages if not p.startswith(OUR_PACKAGE_PREFIX)]
data["packages"].append(package_spec)
write_settings(data)

# web-search.json: WRITE ONLY WHEN ABSENT. An operator's own file may carry a
# paid key, an internal SearXNG endpoint or a curated provider order — silently
# replacing it would change what their agent searches with (and could cost
# money). Reporting the gap instead leaves that decision with the operator.
web_search_state = "already present (left untouched)"
if read_web_search() is None:
    os.makedirs(os.path.dirname(web_search_file), exist_ok=True)
    with open(web_search_file, "w") as fh:
        json.dump({
            "_comment": ("Free-tier web search for pi — written by "
                         "ops/scripts/install/install-pi-integration.sh when no "
                         "config existed. No API keys: Exa's keyless MCP free "
                         "tier, then DuckDuckGo's keyless HTML endpoint. Edit "
                         "the installer, not this file, if it should hold for "
                         "every host."),
            "searchRouting": {"providers": KEYLESS_PROVIDERS,
                              "fallbackOn": ["unsupported", "transient", "quota",
                                             "network", "invalid-response"]},
            "workflow": "none",
        }, fh, indent=2)
        fh.write("\n")
    os.chmod(web_search_file, 0o600)
    web_search_state = "written (keyless chain)"
print(f"Registered in {settings_path} (user scope — applies to EVERY Pi project):")
for ext in (extension, governance_extension):
    if ext:
        print(f"  extension: {ext}")
print(f"  skills:    {curated_dir}  ({len(names)} skills from {manifest_path})")
print(f"  package:   {package_spec}")
print(f"  web search config: {web_search_file} — {web_search_state}")
print("Restart any running Pi session (or /reload) to pick this up.")
PYEOF

# ── install the package itself (the declaration above only DECLARES it) ────
# A declaration in settings.json with nothing on disk is exactly the
# "registered is not executed" failure: pi would load no extension and the
# agent would report a missing web tool. Pi manages its own npm tree, so the
# install goes through pi's launcher; a host with no pi SKIPS (rc 0) — a
# missing coding agent is not a fault, and it must not look like a failed run.
if [[ "$MODE" == "add" ]]; then
  PKG_NAME="${PI_WEB_SEARCH_PACKAGE#npm:}"
  PKG_NAME="${PKG_NAME%@*}"
  PKG_DIR="${AGENT_DIR}/npm/node_modules/${PKG_NAME}"
  if [[ -d "$PKG_DIR" ]]; then
    echo "  package already installed: $PKG_DIR"
  elif [[ -n "$PI_LAUNCHER" && -x "$PI_LAUNCHER" ]]; then
    echo "  installing $PI_WEB_SEARCH_PACKAGE via $PI_LAUNCHER ..."
    # Capture the launcher's output instead of discarding it. It is the only
    # thing that says WHY an install failed (npm 404, no network, a yanked
    # version), and a bare "run it by hand to see why" makes the operator
    # re-run the whole thing to find out what the script already knew.
    INSTALL_LOG="$(mktemp "${TMPDIR:-/tmp}/pi-web-search-install.XXXXXX")"
    if "$PI_LAUNCHER" install "$PI_WEB_SEARCH_PACKAGE" >"$INSTALL_LOG" 2>&1; then
      echo "  ✓ installed $PI_WEB_SEARCH_PACKAGE"
      rm -f "$INSTALL_LOG"
    else
      rc_install=$?
      echo "install-pi-integration: package install FAILED for $PI_WEB_SEARCH_PACKAGE (rc=$rc_install)" >&2
      echo "  --- $PI_LAUNCHER said (last 20 lines) ---" >&2
      tail -n 20 "$INSTALL_LOG" >&2
      echo "  --- end of installer output ---" >&2
      echo "  The declaration stays in ${SETTINGS}; re-run this script to retry." >&2
      rm -f "$INSTALL_LOG"
      exit 1
    fi
  else
    echo "  no pi launcher on this host — declared only, nothing installed"
    echo "  (a host without pi is not a fault; re-run after pi is installed)"
  fi
fi
