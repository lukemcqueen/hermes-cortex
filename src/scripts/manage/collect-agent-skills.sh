#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  collect-agent-skills.sh — Agent-side skill manifest reporter
#
#  Scans BOTH ~/.hermes/skills/ (Hermes native) AND
#  ~/.hermes-cortex/skills/ (cortex deploy) for SKILL.md files
#  that are NOT from the upstream hermes-cortex repo and
#  reports them as custom skills to Moses via inbox.
#
#  no_agent-safe: silent exit (0) when nothing new to report.
#  Deduplicates across both paths (no double reporting).
#  Sends full SKILL.md content for quality evaluation via the
#  JSON /api/send endpoint.
#
#  Requires (from ~/hermes-cortex/.env or ~/.hermes/hermes-inbox.conf):
#    CORTEX_INBOX_URL  — Moses inbox API base URL
#    CORTEX_INBOX_AUTH — "user:pass" for Basic Auth (optional)
#
#  Deployed to agents via cortex-update.sh.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="${CORTEX_REPO:-$HOME/hermes-cortex}"

# Primary: Hermes-native skill location (~/.hermes/skills/)
# Fallback: cortex deploy skills (~/.hermes-cortex/skills/)
HERMES_SKILLS_DIR="$HOME/.hermes/skills"
CORTEX_SKILLS_DIR="${CORTEX_DEPLOY_HOME:-$HOME/.hermes-cortex}/skills"
REPO_SKILLS_DIR="$REPO_DIR/src/skills"
STATE_DIR="${CORTEX_DEPLOY_HOME:-$HOME/.hermes-cortex}/state"
MANIFEST_FILE="$STATE_DIR/skills-manifest.json"
CONTENTS_FILE="$STATE_DIR/skills-contents.json"

# ── Source config ───────────────────────────────────────────
# Try ~/hermes-cortex/.env first, fallback to ~/.hermes/hermes-inbox.conf
if [[ -f "${HOME}/hermes-cortex/.env" ]]; then
  set -a; source "${HOME}/hermes-cortex/.env"; set +a
elif [[ -f "${HOME}/.hermes/hermes-inbox.conf" ]]; then
  source "${HOME}/.hermes/hermes-inbox.conf"
fi

# ── Find custom skills ───────────────────────────────────────
# A skill is "custom" if it exists in ~/.hermes/skills/ or
# ~/.hermes-cortex/skills/ but NOT in the upstream repo's
# src/skills/ directory.
# Dedup: same relative path across both paths counted once.

CUSTOM_SKILLS=()
SKILL_CONTENTS=()
SKILL_COUNT=0
declare -A SEEN_RELPATHS

find_skills_in() {
  local search_dir="$1"
  [[ -d "$search_dir" ]] || return 0
  while IFS= read -r -d '' skill_file; do
    rel_path="${skill_file#$search_dir/}"
    # Skip if already seen (from the other path)
    [[ -n "${SEEN_RELPATHS[$rel_path]:-}" ]] && continue
    SEEN_RELPATHS["$rel_path"]=1
    SKILL_COUNT=$((SKILL_COUNT + 1))

    # Check if this exact SKILL.md exists in the repo
    repo_skill="$REPO_SKILLS_DIR/$rel_path"
    if [[ -f "$repo_skill" ]]; then
      continue  # Not custom — from upstream repo
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
  done < <(find -L "$search_dir" -name "SKILL.md" -type f -print0 2>/dev/null || true)
}

# Search both paths (primary first, fallback second)
find_skills_in "$HERMES_SKILLS_DIR"
find_skills_in "$CORTEX_SKILLS_DIR"

# ── Build and write manifest ─────────────────────────────────
HOSTNAME="$(hostname 2>/dev/null || echo 'unknown')"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
TOTAL=${#CUSTOM_SKILLS[@]}

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

mkdir -p "$STATE_DIR"
build_manifest > "$MANIFEST_FILE"

# Write contents JSON for Python sender to read
python3 -c "
import json, sys
contents = []
for line in sys.stdin:
    contents.append(line.rstrip('\n'))
json.dump(contents, sys.stdout)
" <<< "$(printf '%s\n' "${SKILL_CONTENTS[@]}")" > "$CONTENTS_FILE"

# ── Silent exit when nothing to report (watchdog pattern) ──
if [[ $TOTAL -eq 0 ]]; then
  exit 0
fi

# ── Send to Moses inbox via JSON API ────────────────────────
if [[ -n "${CORTEX_INBOX_URL:-}" ]]; then
  python3 << 'PYEOF'
import json, os, urllib.request, urllib.error, base64
from pathlib import Path

hostname = os.uname().nodename
inbox_url = os.environ.get("CORTEX_INBOX_URL", "").rstrip("/") + "/api/send"
auth_creds = os.environ.get("CORTEX_INBOX_AUTH", "")
state_dir = Path(os.environ.get("HOME")) / ".hermes-cortex" / "state"
manifest_file = state_dir / "skills-manifest.json"
contents_file = state_dir / "skills-contents.json"

if not manifest_file.exists():
    exit(0)

manifest = json.loads(manifest_file.read_text())
contents = []
if contents_file.exists():
    contents = json.loads(contents_file.read_text())

custom_total = manifest.get("custom_skills", 0)
if custom_total == 0:
    exit(0)

# Build body text
parts = []
parts.append(f"━━━ Skill Report — {manifest.get('sender', hostname)} ━━━")
parts.append(f"Generated: {manifest.get('generated', '')}")
parts.append(f"Total skills installed: {manifest.get('total_skills', 0)}")
parts.append(f"Custom skills (not upstream): {custom_total}")
parts.append("")

for i, s in enumerate(manifest.get("skills", [])):
    name = s.get("name", "?")
    catg = s.get("category", "")
    lines_count = s.get("lines", 0)
    age = s.get("age_days", 0)
    summary = s.get("summary", "")
    tag = f" ({catg})" if catg else ""
    parts.append(f"== Skill: {name}{tag} ==")
    parts.append(f"Lines: {lines_count} | Age: {age}d")
    parts.append(f"Description: {summary}")
    parts.append("")
    parts.append("--- Full content ---")
    parts.append(contents[i] if i < len(contents) else "(content unavailable)")
    parts.append("--- End skill ---")
    parts.append("")

body_text = "\n".join(parts)
payload = {
    "from": hostname,
    "subject": f"Skill Report: {custom_total} custom skills",
    "body": body_text,
    "topic": "reports",
    "priority": "normal",
}

# Send JSON POST to inbox API
req = urllib.request.Request(
    inbox_url,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
if auth_creds and ":" in auth_creds:
    encoded = base64.b64encode(auth_creds.encode()).decode()
    req.add_header("Authorization", f"Basic {encoded}")

try:
    resp = urllib.request.urlopen(req, timeout=30)
    print(f"Sent {custom_total} custom skills to Moses inbox", flush=True)
except urllib.error.URLError as e:
    print(f"WARN: Failed to send skill report: {e}", file=sys.stderr, flush=True)
    exit(1)
PYEOF
fi
