#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  collect-agent-skills.sh — Agent-side skill manifest reporter
#
#  Finds skills in ~/.hermes-cortex/skills/ that are NOT from the
#  upstream hermes-cortex repo and reports them to Moses.
#
#  no_agent-safe: silent exit (0) when nothing new to report.
#  Includes full SKILL.md content so Moses can evaluate quality
#  without needing to request the file separately.
#
#  Relies on two env vars (or ~/.hermes/hermes-inbox.conf):
#    CORTEX_INBOX_URL  — Moses inbox MCP endpoint (POST via internal API)
#    CORTEX_INBOX_AUTH — "user:pass" for Basic Auth on that
#      endpoint (optional — skips POST if absent)
#
#  Deployed to agents via cortex-update.sh.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="${CORTEX_REPO:-$HOME/hermes-cortex}"
SKILLS_DIR="${CORTEX_DEPLOY_HOME:-$HOME/.hermes-cortex}/skills"
REPO_SKILLS_DIR="$REPO_DIR/src/skills"
STATE_DIR="${CORTEX_DEPLOY_HOME:-$HOME/.hermes-cortex}/state"
CONFIG_FILE="$HOME/.hermes/hermes-inbox.conf"
MANIFEST_FILE="$STATE_DIR/skills-manifest.json"

# Optional Moses inbox config
if [[ -f "$CONFIG_FILE" ]]; then
  source "$CONFIG_FILE"
fi

# ── Find custom skills ───────────────────────────────────────
# A skill is "custom" if it exists in ~/.hermes/skills/ but
# NOT in the upstream repo's src/skills/ directory.

CUSTOM_SKILLS=()
SKILL_CONTENTS=()
SKILL_COUNT=0

while IFS= read -r -d '' skill_file; do
  rel_path="${skill_file#$SKILLS_DIR/}"
  SKILL_COUNT=$((SKILL_COUNT + 1))

  # Check if this exact SKILL.md exists in the repo
  repo_skill="$REPO_SKILLS_DIR/$rel_path"
  if [[ -f "$repo_skill" ]]; then
    continue
  fi

  # Extract skill name and category from directory path
  skill_dir="$(dirname "$rel_path")"      # e.g. "devops/my-skill"
  name="$(basename "$skill_dir")"           # e.g. "my-skill"
  category="$(dirname "$skill_dir")"        # e.g. "devops"
  [[ "$category" == "." ]] && category=""   # uncategorised

  lines=$(wc -l < "$skill_file" 2>/dev/null || echo 0)
  summary=$(grep -m1 '^description:' "$skill_file" 2>/dev/null | sed 's/^description: *//' || echo "")
  [[ -z "$summary" ]] && summary="(no description)"

  # File age in days
  if [[ "$(uname)" == "Darwin" ]]; then
    birth=$(stat -f "%B" "$skill_file" 2>/dev/null || echo 0)
  else
    birth=$(stat -c "%W" "$skill_file" 2>/dev/null || echo 0)
  fi
  now=$(date +%s)
  age_days=$(( (now - birth) / 86400 ))
  [[ $age_days -lt 0 ]] && age_days=0

  # Read full SKILL.md content for evaluation
  content=$(cat "$skill_file" 2>/dev/null || echo "(unreadable)")

  CUSTOM_SKILLS+=("{\"name\":\"$name\",\"category\":\"$category\",\"lines\":$lines,\"age_days\":$age_days,\"summary\":\"$summary\"}")
  SKILL_CONTENTS+=("$content")
done < <(find -L "$SKILLS_DIR" -name "SKILL.md" -type f -print0 2>/dev/null || true)

# ── Build manifest ───────────────────────────────────────────
HOSTNAME="$(hostname 2>/dev/null || echo 'unknown')"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
TOTAL=${#CUSTOM_SKILLS[@]}

# Build JSON safely without jq dependency
build_manifest() {
  echo "{"
  echo "  \"sender\": \"$HOSTNAME\","
  echo "  \"type\": \"skill-report\","
  echo "  \"generated\": \"$TIMESTAMP\","
  echo "  \"total_skills\": $SKILL_COUNT,"
  echo "  \"custom_skills\": $TOTAL,"
  echo "  \"skills\": ["
  local first=true
  for skill in "${CUSTOM_SKILLS[@]}"; do
    $first || echo ","
    first=false
    echo -n "    $skill"
  done
  echo ""
  echo "  ]"
  echo "}"
}

MANIFEST=$(build_manifest)

# Write local manifest (always, for auditing)
mkdir -p "$STATE_DIR"
echo "$MANIFEST" > "$MANIFEST_FILE"

# ── Silent exit when nothing to report (watchdog pattern) ──
if [[ $TOTAL -eq 0 ]]; then
  exit 0
fi

# ── Send to Moses inbox (if configured) ─────────────────────
if [[ -n "${CORTEX_INBOX_URL:-}" ]]; then
  AUTH_ARGS=()
  if [[ -n "${CORTEX_INBOX_AUTH:-}" ]]; then
    AUTH_ARGS=(-u "$CORTEX_INBOX_AUTH")
  fi

  # Build body: summary overview + full content for each skill
  BODY="━━━ Skill Report — $HOSTNAME ━━━
Generated: $TIMESTAMP
Total skills installed: $SKILL_COUNT
Custom skills (not upstream): $TOTAL

"

  idx=0
  for skill in "${CUSTOM_SKILLS[@]}"; do
    name=$(echo "$skill" | grep -o '"name":"[^"]*"' | cut -d'"' -f4)
    catg=$(echo "$skill" | grep -o '"category":"[^"]*"' | cut -d'"' -f4)
    lines=$(echo "$skill" | grep -o '"lines":[0-9]*' | cut -d: -f2)
    summary=$(echo "$skill" | grep -o '"summary":"[^"]*"' | cut -d'"' -f4)

    BODY+="== Skill: $name"
    [[ -n "$catg" ]] && BODY+=" ($catg)"
    BODY+=" ==
Lines: $lines | Age: $(echo "$skill" | grep -o '"age_days":[0-9]*' | cut -d: -f2)d
Description: $summary

--- Full content ---
${SKILL_CONTENTS[$idx]:-(unreadable)}
--- End skill ---

"
    idx=$((idx + 1))
  done

  # Write body to temp file to avoid "Argument list too long" on curl -d
  BODY_FILE=$(mktemp)
  cat > "$BODY_FILE" <<- BODYEOF
from=$HOSTNAME&topic=reports&subject=Skill Report: $TOTAL custom skills&body=$BODY&priority=normal
BODYEOF

  curl -sk -X POST "$CORTEX_INBOX_URL" \
    "${AUTH_ARGS[@]}" \
    --data-binary @"$BODY_FILE" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --connect-timeout 10 \
    --max-time 15

  rm -f "$BODY_FILE"
  echo "Sent $TOTAL custom skills to Moses inbox" >&2
fi