#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Steadfaste Fleet — Project Profile Creator
#  Creates a hermetic project profile with isolated brain,
#  Hermes profile, and mycortex source.
#
#  Usage:
#    bash scripts/fleet-profile.sh <project-name> [project-path]
#
#  If project-path is omitted, defaults to ~/Developer/AI/<project-name>.
#  Override with DEV_DIR env var for custom project locations.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_NAME="${1:?Usage: bash ops/scripts/install/fleet-profile.sh <name> [path]}"
PROJECT_PATH="${2:-${DEV_DIR:-${HOME}/Developer/AI}/${PROJECT_NAME}}"
BRAIN_BASE="${HOME}/brain"
HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
PROFILES_DIR="${HERMES_HOME}/profiles"
MYCORTEX_CLI="${HOME}/.steadfaste-fleet/scripts/mycortex"

# Resolve absolute path for PROJECT_PATH — refuse rather than leave it empty
# (an empty PROJECT_PATH would make mkdir -p operate on ./ and proceed broken).
_parent="$(dirname "$PROJECT_PATH")"
if [[ ! -d "$_parent" ]]; then
  echo "⚠ parent directory does not exist: ${_parent}" >&2
  exit 1
fi
PROJECT_PATH="$(cd "$_parent" && echo "$PWD/$(basename "$PROJECT_PATH")")"

echo "=== Creating project profile: ${PROJECT_NAME} ==="
echo "  Project path: ${PROJECT_PATH}"

# 1. Create the project directory if it doesn't exist
mkdir -p "$PROJECT_PATH"

# 2. Create Hermes profile
PROFILE_DIR="${PROFILES_DIR}/${PROJECT_NAME}"
if [[ -d "$PROFILE_DIR" ]]; then
  echo "  ⏭ Hermes profile already exists: ${PROFILE_DIR}"
else
  mkdir -p "${PROFILE_DIR}/skills" "${PROFILE_DIR}/plugins" "${PROFILE_DIR}/memories" "${PROFILE_DIR}/cron"
  # Seed empty memory files
  echo "# ${PROJECT_NAME} — MEMORY.md" > "${PROFILE_DIR}/memories/MEMORY.md"
  echo "# ${PROJECT_NAME} — USER.md" > "${PROFILE_DIR}/memories/USER.md"
  echo "  ✅ Hermes profile: ${PROFILE_DIR}"
fi

# 3. Create brain source directory
BRAIN_DIR="${BRAIN_BASE}/${PROJECT_NAME}"
if [[ -d "$BRAIN_DIR" ]]; then
  echo "  ⏭ Brain source already exists: ${BRAIN_DIR}"
else
  mkdir -p "$BRAIN_DIR"
  # Init git — required by mycortex. Fail and say so if git cannot do it
  # (a silent `git init || true` leaves a non-repo the mycortex brain needs).
  if ! command -v git >/dev/null 2>&1; then
    echo "⚠ git is required but not on PATH — brain source not usable by mycortex" >&2
  elif ! git -C "$BRAIN_DIR" init >/dev/null 2>&1; then
    echo "⚠ git init failed for ${BRAIN_DIR} — brain source not usable by mycortex" >&2
  else
    cat > "${BRAIN_DIR}/.gitignore" <<GITEOF
MEMORY.md
USER.md
.env
.env.*
*.pem
*.key
*.cert
GITEOF
    git -C "$BRAIN_DIR" add -A >/dev/null 2>&1 || \
      echo "⚠ git add failed (identity unset?) — the initial commit did not land; add it before relying on the brain repo" >&2
    git -C "$BRAIN_DIR" commit -m "init: ${PROJECT_NAME} brain source" >/dev/null 2>&1 || \
      echo "⚠ git commit failed (set user.name/user.email?) — brain not committed yet" >&2
    echo "  ✅ Brain source: ${BRAIN_DIR}"
  fi
fi

# 4. Register as mycortex source (isolated, non-federated)
if [[ -x "$MYCORTEX_CLI" ]]; then
  if "$MYCORTEX_CLI" sources list 2>/dev/null | grep -q "\"name\": \"${PROJECT_NAME}\""; then
    echo "  ⏭ mycortex source '${PROJECT_NAME}' already registered"
  elif "$MYCORTEX_CLI" sources add "${PROJECT_NAME}" "${BRAIN_DIR}" 2>/dev/null; then
    echo "  ✅ mycortex source: ${PROJECT_NAME} (isolated)"
  else
    echo "  ⚠ Could not add mycortex source (mycortex may need re-init)" >&2
  fi
else
  echo "  ⚠ mycortex not installed — skip source registration"
fi

# 5. Register in cortex-projects.json (legacy host config — kept path)
PROJECTS_FILE="${HOME}/.cortex-projects.json"
_registered=0
if [[ -f "$PROJECTS_FILE" ]]; then
  if python3 -c "
import json, sys
path='${PROJECTS_FILE}'
try:
    with open(path) as f:
        projects = json.load(f)
except (json.JSONDecodeError, OSError) as e:
    print('could not parse ' + path + ': ' + str(e), file=sys.stderr)
    sys.exit(1)
projects = [p for p in projects if p.get('project_name') != '${PROJECT_NAME}']
projects.append({
    'project_name': '${PROJECT_NAME}',
    'location': '${PROJECT_PATH}',
    'brain': '${BRAIN_DIR}',
    'profile': '${PROJECT_NAME}',
    'mycortex_source': '${PROJECT_NAME}'
})
with open(path, 'w') as f:
    json.dump(projects, f, indent=2)
"; then
    _registered=1
  else
    echo "  ⚠ could not update ${PROJECTS_FILE} — fix it and re-run" >&2
  fi
else
  cat > "$PROJECTS_FILE" <<JSONEOF
[
  {
    "project_name": "${PROJECT_NAME}",
    "location": "${PROJECT_PATH}",
    "brain": "${BRAIN_DIR}",
    "profile": "${PROJECT_NAME}",
    "mycortex_source": "${PROJECT_NAME}"
  }
]
JSONEOF
  _registered=1
fi
[[ "$_registered" -eq 1 ]] && echo "  ✅ Registered in ${PROJECTS_FILE}"

echo ""
echo "✅ Profile '${PROJECT_NAME}' ready."
echo "   Run: hermes --profile ${PROJECT_NAME}"
echo "   Brain: ${BRAIN_DIR}"
