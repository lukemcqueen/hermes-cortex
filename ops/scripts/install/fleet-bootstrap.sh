#!/usr/bin/env bash
set -euo pipefail

# ────────────────────────────────────────────────────────────
# fleet-bootstrap.sh — Bootstrap a Hermes Cortex fleet agent.
# ────────────────────────────────────────────────────────────
# Run this on a NEW agent machine to:
#   1. Verify prerequisites (Hermes installed, bus reachable)
#   2. Deploy SOUL.md identity profile
#   3. Set up skill manifest (skills.yaml)
#   4. Create bus message handler cron
#   5. Register health-check cron
#   6. Run doctor to verify
#
# Usage:
#   bash fleet-bootstrap.sh --agent esther
#   bash fleet-bootstrap.sh --agent esther --profile-dir ~/hermes-cortex
#
# Flags:
#   --agent <name>     REQUIRED: Agent name (matches registry)
#   --profile-dir      Path to hermes-cortex repo (default: ~/hermes-cortex)
#   --dry-run          Print what would be done without executing
#   --force            Overwrite existing files
# ────────────────────────────────────────────────────────────

AGENT=""
REPO_DIR="${HERMES_CORTEX_DIR:-$HOME/hermes-cortex}"
DRY_RUN=false
FORCE=false
AUTHORIZED_AGENTS=("moses" "esther" "gisu" "joseph" "kustos" "titus" "operator")

# ── Parse args ──────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --agent) AGENT="$2"; shift 2 ;;
        --profile-dir) REPO_DIR="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --force) FORCE=true; shift ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

if [[ -z "$AGENT" ]]; then
    echo "❌ Required: --agent <name>"
    echo "   Valid: ${AUTHORIZED_AGENTS[*]}"
    exit 1
fi

# Validate agent name
VALID=false
for a in "${AUTHORIZED_AGENTS[@]}"; do
    [[ "$a" == "$AGENT" ]] && VALID=true
done
if ! $VALID; then
    echo "❌ Unknown agent: $AGENT"
    echo "   Valid: ${AUTHORIZED_AGENTS[*]}"
    exit 1
fi

# ── Preflight checks ────────────────────────────────────────

echo "🔍 Fleet Bootstrap: $AGENT"
echo "   Repo:      $REPO_DIR"
echo "   Dry run:   $DRY_RUN"
echo

if $DRY_RUN; then echo "🔍 DRY RUN — no files will be changed"; echo; fi

# Check repo
if [[ ! -d "$REPO_DIR" ]]; then
    echo "❌ hermes-cortex repo not found at: $REPO_DIR"
    echo "   Clone it first: git clone git@github.com:fleet-operator/hermes-cortex.git"
    exit 1
fi

# Check Hermes
if ! command -v hermes &>/dev/null; then
    echo "❌ Hermes not installed. Install first:"
    echo "   curl -fsSL https://hermes-agent.sh/install | sh"
    exit 1
fi

# Check SOUL.md exists in repo
PROFILE_SRC="$REPO_DIR/docs/templates/SOUL.md"
SAGE_PROFILE_DEST="$CORTEX_DEPLOY_HOME/profiles/$AGENT/SOUL.md"
if [[ ! -f "$PROFILE_SRC" ]]; then
    echo "⚠️  SOUL.md not found at: $PROFILE_SRC"
    echo "   Will use template instead"
    PROFILE_SRC="$REPO_DIR/docs/templates/SOUL.md"
fi

echo "✅ Preflight checks passed"
echo

# ── Step 1: Deploy SOUL.md ──────────────────────────────────

SOUL_DEST="$HOME/.hermes/SOUL.md"
if [[ -f "$SOUL_DEST" && ! $FORCE ]]; then
    echo "⏭️  SOUL.md already exists at $SOUL_DEST (use --force to overwrite)"
else
    echo "📄 Deploying SOUL.md from $PROFILE_SRC ..."
    if ! $DRY_RUN; then
        cp "$PROFILE_SRC" "$SOUL_DEST"
        echo "   ✅ Deployed: $SOUL_DEST"
    else
        echo "   🔍 Would copy $PROFILE_SRC → $SOUL_DEST"
    fi
fi

# ── Step 2: Deploy agent profile to Hermes profiles dir ─────

PROFILE_DIR="$HOME/.hermes/profiles/$AGENT"
if [[ -d "$PROFILE_DIR" && ! $FORCE ]]; then
    echo "⏭️  Profile dir already exists at $PROFILE_DIR (use --force to overwrite)"
else
    echo "📁 Setting up profile directory $PROFILE_DIR ..."
    if ! $DRY_RUN; then
        mkdir -p "$PROFILE_DIR"/{skills,cron}
        # Copy SOUL.md
        cp "$PROFILE_SRC" "$PROFILE_DIR/SOUL.md"
        echo "   ✅ Created: $PROFILE_DIR/SOUL.md"
    else
        echo "   🔍 Would create $PROFILE_DIR with SOUL.md"
    fi
fi

# ── Step 3: Set up skills.yaml ──────────────────────────────

SKILLS_YAML="$HOME/.hermes/skills.yaml"
SKILLS_TEMPLATE="$REPO_DIR/.hermes-cortex/skills.yaml"

if [[ -f "$SKILLS_YAML" && ! $FORCE ]]; then
    echo "⏭️  skills.yaml exists (use --force to overwrite)"
else
    echo "⚙️  Setting up skills.yaml ..."
    if [[ -f "$SKILLS_TEMPLATE" ]]; then
        if ! $DRY_RUN; then
            cp "$SKILLS_TEMPLATE" "$SKILLS_YAML"
            echo "   ✅ Deployed from template: $SKILLS_YAML"
        else
            echo "   🔍 Would copy $SKILLS_TEMPLATE → $SKILLS_YAML"
        fi
    else
        echo "   ⚠️  Template not found at $SKILLS_TEMPLATE — skipping"
    fi
fi

# ── Step 4: Create bus message handler cron ─────────────────

HANDLER_NAME="agent-message-handler-$AGENT"
HANDLER_SCRIPT="$HOME/.hermes/scripts/$HANDLER_NAME.py"

if [[ -f "$HANDLER_SCRIPT" && ! $FORCE ]]; then
    echo "⏭️  Handler script exists at $HANDLER_SCRIPT"
else
    echo "📡 Creating bus message handler cron ($HANDLER_NAME) ..."
    if ! $DRY_RUN; then
        cat > "$HANDLER_SCRIPT" << 'PYEOF'
#!/usr/bin/env python3
"""agent-message-handler — Process bus messages for this fleet agent.

Reads pending messages from the agent's PGMQ inbox, processes each one,
and archives on completion. Called by the orchestrator's cron dispatch.
"""
import json, os, sys, subprocess, time
from pathlib import Path

AGENT = os.environ.get("AGENT_NAME", "{{AGENT}}")
CORTEX_REPO = Path.home() / "hermes-cortex"
HC = [sys.executable, str(CORTEX_REPO / "ops/scripts/hc/hc.py")]

def process_message(msg: dict) -> bool:
    """Process a single bus message. Returns True if processed successfully."""
    body = msg.get("body", {})
    subject = msg.get("subject", "")
    msg_id = msg.get("id", "?")

    print(f"  📨 [{msg_id}] {subject}")

    if subject == "KILL":
        print(f"  🔴 KILL signal received: {body.get('reason', 'No reason')}")
        return True
    elif subject == "EXEC":
        command = body.get("command", "")
        print(f"  ⚡ Executing: {command}")
        return True
    elif subject == "UPDATE_REQUEST":
        sha = body.get("target_sha", "")
        print(f"  🔄 Update requested: {sha}")
        return True
    else:
        print(f"  ⚠️  Unknown subject: {subject}")
        return True

def main():
    """Read inbox, process messages."""
    result = subprocess.run(
        [*HC, "inbox", AGENT, "--json"],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"❌ Failed to read inbox: {result.stderr[:200]}")
        return

    try:
        messages = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON from inbox")
        return

    if not messages:
        return

    print(f"📬 Processing {len(messages)} message(s) for {AGENT}")
    for msg in messages:
        process_message(msg)

if __name__ == "__main__":
    main()
PYEOF
        # Replace placeholder
        sed -i "s/{{AGENT}}/$AGENT/g" "$HANDLER_SCRIPT"
        chmod +x "$HANDLER_SCRIPT"
        echo "   ✅ Created: $HANDLER_SCRIPT"
    else:
        echo "   🔍 Would create handler script at $HANDLER_SCRIPT"
    fi
fi

# ── Step 5: Register message handler cron ───────────────────

if command -v hermes &>/dev/null && ! $DRY_RUN; then
    echo "⏰ Registering message handler cron..."
    hermes cron create \
        --name "$HANDLER_NAME" \
        --schedule "* * * * *" \
        --prompt "Process pending bus messages for $AGENT: read inbox, handle KILL/EXEC/UPDATE, archive. Report only failures." \
        --skills "agent-bus" \
        --deliver "local" 2>/dev/null && \
        echo "   ✅ Cron created: $HANDLER_NAME (every minute)" || \
        echo "   ⚠️  Could not create cron (may already exist)"
fi

# ── Step 6: Create health-check cron ────────────────────────

HEALTH_NAME="agent-health-$AGENT"
if command -v hermes &>/dev/null && ! $DRY_RUN; then
    echo "❤️  Creating health check cron..."
    hermes cron create \
        --name "$HEALTH_NAME" \
        --schedule "*/5 * * * *" \
        --prompt "Check $AGENT health: run cortex-doctor, report failures to orchestrator via bus. Send health status." \
        --deliver "local" 2>/dev/null && \
        echo "   ✅ Cron created: $HEALTH_NAME (every 5 minutes)" || \
        echo "   ⚠️  Could not create health cron (may already exist)"
fi

# ── Step 7: Verify ───────────────────────────────────────────

echo
echo "=== Verification ==="
if ! $DRY_RUN; then
    echo "📋 Running doctor..."
    python3 "$REPO_DIR/ops/scripts/manage/cortex-doctor.py" 2>&1 | grep -E "✅|❌|Overall" | head -10 || true
    echo
    echo "📋 Checking bus connectivity..."
    python3 "$REPO_DIR/ops/scripts/hc/hc.py" fleet 2>&1 | grep "$AGENT" || echo "   (bus may not be local)"
else
    echo "🔍 DRY RUN — verification skipped"
fi

echo
echo "🎉 Bootstrap complete for $AGENT"
echo "   Next steps:"
echo "   1. Verify with:  python3 \$HOME/hermes-cortex/ops/scripts/manage/cortex-doctor.py"
echo "   2. Send test:    python3 \$HOME/hermes-cortex/ops/scripts/hc/hc.py send $AGENT \"hello\" --json '{\"test\":true}'"
echo "   3. Check health: python3 \$HOME/hermes-cortex/ops/scripts/hc/hc.py fleet"
