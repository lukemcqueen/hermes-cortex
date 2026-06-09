#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — Project Profile Creator
#  Creates a hermetic project profile with isolated brain,
#  Hermes profile, and gbrain source.
#
#  Usage:
#    bash scripts/cortex-profile.sh <project-name> [project-path]
#
#  If project-path is omitted, uses ~/Developer/AI/<project-name>.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_NAME="${1:?Usage: bash scripts/cortex-profile.sh <name> [path]}"
PROJECT_PATH="${2:-${HOME}/Developer/AI/${PROJECT_NAME}}"
BRAIN_BASE="${HOME}/brain"
HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
PROFILES_DIR="${HERMES_HOME}/profiles"
GBRAIN_CMD="${HOME}/.bun/bin/gbrain"

# Resolve absolute path for PROJECT_PATH
PROJECT_PATH="$(cd "$(dirname "$PROJECT_PATH")" 2>/dev/null && echo "$PWD/$(basename "$PROJECT_PATH")")"

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

# 2b. Copy root auth.json into the profile (so profile creds inherit root keys)
ROOT_AUTH="${HERMES_HOME}/auth.json"
if [[ -f "$ROOT_AUTH" ]]; then
  cp "$ROOT_AUTH" "${PROFILE_DIR}/auth.json"
  echo "  ✅ Auth credentials synced to profile"
fi

# 3. Create brain source directory
BRAIN_DIR="${BRAIN_BASE}/${PROJECT_NAME}"
if [[ -d "$BRAIN_DIR" ]]; then
  echo "  ⏭ Brain source already exists: ${BRAIN_DIR}"
else
  mkdir -p "$BRAIN_DIR"
  # Init git — required by gbrain
  git -C "$BRAIN_DIR" init 2>/dev/null || true
  cat > "${BRAIN_DIR}/.gitignore" <<GITEOF
MEMORY.md
USER.md
.env
.env.*
*.pem
*.key
*.cert
GITEOF
  git -C "$BRAIN_DIR" add -A 2>/dev/null || true
  git -C "$BRAIN_DIR" commit -m "init: ${PROJECT_NAME} brain source" 2>/dev/null || true
  echo "  ✅ Brain source: ${BRAIN_DIR}"
fi

# 4. Register as gbrain source (isolated, non-federated)
if command -v "$GBRAIN_CMD" &>/dev/null; then
  if "$GBRAIN_CMD" sources list 2>/dev/null | grep -q "^${PROJECT_NAME}\b"; then
    echo "  ⏭ gbrain source '${PROJECT_NAME}' already registered"
  else
    "$GBRAIN_CMD" sources add "${PROJECT_NAME}" --path "${BRAIN_DIR}" --name "${PROJECT_NAME}" 2>/dev/null || \
      echo "  ⚠ Could not add gbrain source (gbrain may need re-init)"
    echo "  ✅ gbrain source: ${PROJECT_NAME} (isolated)"
  fi
else
  echo "  ⚠ gbrain not installed — skip gbrain source registration"
fi

# 5. Register in cortex-projects.json
PROJECTS_FILE="${HOME}/.cortex-projects.json"
if [[ -f "$PROJECTS_FILE" ]]; then
  python3 -c "
import json
with open('${PROJECTS_FILE}') as f:
    projects = json.load(f)
# Remove old entry if exists
projects = [p for p in projects if p.get('project_name') != '${PROJECT_NAME}']
projects.append({
    'project_name': '${PROJECT_NAME}',
    'location': '${PROJECT_PATH}',
    'brain': '${BRAIN_DIR}',
    'profile': '${PROJECT_NAME}',
    'gbrain_source': '${PROJECT_NAME}'
})
with open('${PROJECTS_FILE}', 'w') as f:
    json.dump(projects, f, indent=2)
" 2>/dev/null || true
else
  cat > "$PROJECTS_FILE" <<JSONEOF
[
  {
    "project_name": "${PROJECT_NAME}",
    "location": "${PROJECT_PATH}",
    "brain": "${BRAIN_DIR}",
    "profile": "${PROJECT_NAME}",
    "gbrain_source": "${PROJECT_NAME}"
  }
]
JSONEOF
fi
echo "  ✅ Registered in ~/.cortex-projects.json"

echo ""
echo "✅ Profile '${PROJECT_NAME}' ready."
echo "   Run: hermes --profile ${PROJECT_NAME}"
echo "   Brain: ${BRAIN_DIR}"
