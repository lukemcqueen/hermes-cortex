#!/usr/bin/env bash
# setup-agent-registry.sh — First-time setup for agent-registry.json
#
# Creates ~/.hermes-cortex/state/agent-registry.json from the template
# by filling in real server URLs. Skips if file already exists.
#
# Usage:
#   Interactive:  bash setup-agent-registry.sh
#   Auto (env):   CORTEX_DOMAIN=mydomain.com CORTEX_HEALTH_PORT=13007 \
#                   ESTHER_DOMAIN=other.com ESTHER_HEALTH_PORT=13007 \
#                   ... bash setup-agent-registry.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CORTEX_HOME="${CORTEX_HOME:-$HOME/hermes-cortex}"
STATE_DIR="$HOME/.hermes-cortex/state"
TEMPLATE="$CORTEX_HOME/ops/install/deploy/agent-registry.template.json"
TARGET="$STATE_DIR/agent-registry.json"
LOCAL_OVERRIDE="$HOME/.hermes-cortex/state/agent-registry.local.json"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}ℹ${NC} $1"; }
ok()    { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
err()   { echo -e "${RED}✗${NC} $1"; }

if [ ! -f "$TEMPLATE" ]; then
    err "Template not found at $TEMPLATE"
    exit 1
fi

if [ -f "$TARGET" ]; then
    info "Agent registry already exists at $TARGET"
    ok "Current agents:"
    python3 -c "
import json; d=json.load(open('$TARGET'))
for k,v in d.get('agents',{}).items():
    url = v.get('health_url','')
    marker = '🟢' if '{{' not in url else '🟡'
    print(f'  {marker} {k}: {url}')
"
    exit 0
fi

mkdir -p "$STATE_DIR"

# Use Python for all substitution — handles env vars correctly
python3 << PYEOF
import json, os, re
from pathlib import Path

template_path = Path("$TEMPLATE")
target_path = Path("$TARGET")

data = json.loads(template_path.read_text())

# Per-agent env var mapping
# Template uses {{CORTEX_DOMAIN}} etc. — env vars match these names
PREFIX_MAP = {
    "moses":  "CORTEX",
    "esther": "ESTHER",
    "joseph": "JOSEPH",
    "kustos": "KUSTOS",
    "gisu":   "GISU",
}

for agent_name, agent_data in data.get("agents", {}).items():
    url = agent_data.get("health_url", "")
    if "{{" not in url:
        continue  # already filled in

    agent_prefix = PREFIX_MAP.get(agent_name, agent_name.upper())
    domain = os.environ.get(f"{agent_prefix}_DOMAIN", "").strip()
    port = os.environ.get(f"{agent_prefix}_HEALTH_PORT", "").strip()

    if domain and port:
        agent_data["health_url"] = f"https://{domain}:{port}/health"
    elif not os.environ.get("CI"):
        # Interactive prompt
        print(f"\nAgent: {agent_name}")
        print(f"  Current: {url}")
        user_input = input(f"  Enter health URL (or Enter to skip): ").strip()
        if user_input:
            agent_data["health_url"] = user_input
        else:
            warn(f"  Skipping {agent_name}")
            continue

target_path.write_text(json.dumps(data, indent=2) + "\n")
PYEOF

echo
ok "Registry written to $TARGET"
python3 -c "
import json; d=json.load(open('$TARGET'))
for k,v in d.get('agents',{}).items():
    url = v.get('health_url','')
    marker = '🟢' if '{{' not in url else '🟡 placeholder'
    print(f'  {marker} {k}: {url}')
"

# Create local override example if not present
if [ ! -f "$LOCAL_OVERRIDE" ]; then
    cat > "$LOCAL_OVERRIDE" << 'EOF'
{
  "_comment": "Per-machine local overrides merge on top of agent-registry.json",
  "_example": {
    "moses": { "health_url": "http://localhost:13007/health" }
  }
}
EOF
    info "Created example local override at $LOCAL_OVERRIDE"
fi

echo
info "To re-run: rm $TARGET && bash $0"
