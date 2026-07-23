#!/usr/bin/env bash
# setup-fleet-langfuse.sh — Wire a fleet agent to the shared Langfuse instance.
#
# Usage:
#   bash setup-fleet-langfuse.sh <agent-name>
#
# Example:
#   bash setup-fleet-langfuse.sh esther
#
# The shared Langfuse instance must be reachable via the fleet's PGMQ gateway
# at the configured base_url below.
#
# This script:
#   1. Generates (or reuses) a Langfuse API key via the shared Langfuse API
#   2. Sets HERMES_LANGFUSE_* in the agent's ~/.hermes/.env
#   3. Installs the langfuse Python SDK
#   4. Enables the Hermes Langfuse plugin
#   5. Restarts the Hermes gateway

set -euo pipefail

SCRIPT_NAME=$(basename "$0")
AGENT_NAME="${1:-}"

if [ -z "$AGENT_NAME" ]; then
    echo "Usage: $SCRIPT_NAME <agent-name>"
    echo "  e.g. $SCRIPT_NAME esther"
    exit 1
fi

# ── Configuration ──────────────────────────────────────────────
# Point this to the external URL of the shared Langfuse instance.
# Langfuse is typically behind nginx on port 13002 with auth_basic.
# Change to match your fleet deployment.
SHARED_LANGFUSE_URL="${SHARED_LANGFUSE_URL:-http://localhost:3000}"
SHARED_LANGFUSE_PUBLIC_KEY="${SHARED_LANGFUSE_PUBLIC_KEY:-}"
SHARED_LANGFUSE_SECRET_KEY="${SHARED_LANGFUSE_SECRET_KEY:-}"

HERMES_HOME="${HOME}/.hermes"
ENV_FILE="${HERMES_HOME}/.env"

echo "━━━ Setting up Langfuse tracing for agent: ${AGENT_NAME} ━━━"

# ── Step 1: Generate or use API keys ─────────────────────────
if [ -z "$SHARED_LANGFUSE_PUBLIC_KEY" ] || [ -z "$SHARED_LANGFUSE_SECRET_KEY" ]; then
    echo "❌ SHARED_LANGFUSE_PUBLIC_KEY and SHARED_LANGFUSE_SECRET_KEY must be set."
    echo "   Export them before running this script, or pass via .env."
    echo ""
    echo "   To generate a new key pair on Moses:"
    echo "     docker exec langfuse-postgres-1 psql -U postgres -d postgres -c \""
    echo "       INSERT INTO api_keys (id, project_id, public_key, hashed_secret_key,"
    echo "         fast_hashed_secret_key, display_secret_key, note, created_at)"
    echo "       SELECT"
    echo "         'cmqkey-' || gen_random_uuid()::text,"
    echo "         'default-project',"
    echo "         'pk-lf-' || encode(gen_random_bytes(16), 'hex'),"
    echo "         crypt('sk-lf-' || encode(gen_random_bytes(16), 'hex'), gen_salt('bf')),"
    echo "         encode(sha256('sk-lf-' || encode(gen_random_bytes(16), 'hex')::bytea), 'hex'),"
    echo "         'sk-lf-' || encode(gen_random_bytes(16), 'hex'),"
    echo "         '${AGENT_NAME} tracing key',"
    echo "         CURRENT_TIMESTAMP;"
    echo "   \""
    echo ""
    echo "   Then capture the displayed public and secret keys."
    exit 1
fi

# ── Step 2: Set env vars ──────────────────────────────────────
echo "→ Setting Hermes Langfuse env vars for ${AGENT_NAME}..."

# Remove any old HERMES_LANGFUSE_* lines
if [ -f "$ENV_FILE" ]; then
    sed -i '/^HERMES_LANGFUSE_/d' "$ENV_FILE"
fi

cat >> "$ENV_FILE" <<EOF

# Langfuse tracing (set by ${SCRIPT_NAME} on $(date +%Y-%m-%d))
HERMES_LANGFUSE_PUBLIC_KEY=${SHARED_LANGFUSE_PUBLIC_KEY}
HERMES_LANGFUSE_SECRET_KEY=${SHARED_LANGFUSE_SECRET_KEY}
HERMES_LANGFUSE_BASE_URL=${SHARED_LANGFUSE_URL}
HERMES_LANGFUSE_ENV=${AGENT_NAME}
HERMES_LANGFUSE_RELEASE=v1
HERMES_LANGFUSE_SAMPLE_RATE=1.0
EOF

echo "   ✓ Env vars written to ${ENV_FILE}"
echo "     Environment tag: ${AGENT_NAME} (appears in Langfuse traces)"

# ── Step 3: Install Python SDK ────────────────────────────────
echo "→ Installing langfuse Python SDK..."
pip3 install --break-system-packages langfuse 2>/dev/null || \
    pip3 install langfuse 2>/dev/null || \
    echo "   ⚠️ Could not install langfuse SDK. Hermes will silently skip tracing."

python3 -c "import langfuse; print(f'   ✓ langfuse SDK v{langfuse.__version__}')" 2>/dev/null || \
    echo "   ⚠️ langfuse SDK not importable."

# ── Step 4: Enable the plugin ─────────────────────────────────
echo "→ Enabling Hermes Langfuse plugin..."
hermes plugins enable observability/langfuse 2>/dev/null && \
    echo "   ✓ Plugin enabled" || \
    echo "   ⚠️ Plugin enable command failed (may already be enabled)."

hermes plugins list 2>/dev/null | grep -q langfuse && \
    echo "   ✓ Langfuse plugin confirmed active" || \
    echo "   ⚠️ Langfuse plugin not listed."

# ── Step 5: Enable token analytics ────────────────────────────
echo "→ Enabling token analytics display..."
hermes config set dashboard.show_token_analytics true 2>/dev/null || true
hermes config set display.show_cost true 2>/dev/null || true
echo "   ✓ Token analytics and cost display enabled"

# ── Step 6: Verify connectivity ───────────────────────────────
echo "→ Testing Langfuse connectivity..."
AUTH=$(echo -n "${SHARED_LANGFUSE_PUBLIC_KEY}:${SHARED_LANGFUSE_SECRET_KEY}" | base64 -w0)
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Basic ${AUTH}" \
    "${SHARED_LANGFUSE_URL}/api/public/projects" 2>/dev/null || echo "000")

if [ "$HEALTH" = "200" ]; then
    echo "   ✓ Langfuse API reachable (HTTP ${HEALTH})"
else
    echo "   ⚠️ Langfuse API returned HTTP ${HEALTH}"
    echo "     Check that ${SHARED_LANGFUSE_URL} is reachable from this host."
    echo "     The agent will try to send traces but may silently fail."
fi

# ── Step 7: Restart Hermes gateway ────────────────────────────
echo "→ Restarting Hermes gateway (required for new env vars)..."
if systemctl --user list-units --output=name 2>/dev/null | grep -q hermes-gateway; then
    cat > /tmp/restart-hermes-${AGENT_NAME}.sh << 'RESTART'
#!/bin/bash
sleep 3
systemctl --user restart hermes-gateway.service
RESTART
    chmod +x /tmp/restart-hermes-${AGENT_NAME}.sh
    nohup setsid /tmp/restart-hermes-${AGENT_NAME}.sh </dev/null >/dev/null 2>&1 &
    echo "   ↻ Gateway restart triggered (delayed 3s). Session will reconnect momentarily."
else
    echo "   ⚪ No systemd gateway service found — env vars will take effect on next session start."
fi

echo ""
echo "━━━ Setup complete for ${AGENT_NAME} ━━━"
echo ""
echo "Next: Verify traces reach Langfuse after the next session:"
echo "  1. Start a new Hermes session on ${AGENT_NAME}"
echo "  2. Check Langfuse at ${SHARED_LANGFUSE_URL}"
echo "     Filter by environment=${AGENT_NAME}"
echo ""
echo "To test immediately:"
echo "  python3 -c \""
echo "from langfuse import Langfuse"
echo "import requests, time"
echo ""
echo "PK = '${SHARED_LANGFUSE_PUBLIC_KEY}'"
echo "SK = '${SHARED_LANGFUSE_SECRET_KEY}'"
echo "client = Langfuse(public_key=PK, secret_key=SK, base_url='${SHARED_LANGFUSE_URL}')"
echo "trace_id = client.create_trace_id(seed='fleet-test')"
echo "with client.start_as_current_observation(trace_context={'trace_id': trace_id}, name='fleet-connect-test', as_type='chain', input='test', end_on_exit=True):"
echo "    pass"
echo "client.flush()"
echo "time.sleep(2)"
echo "auth = requests.auth.HTTPBasicAuth(PK, SK)"
echo "r = requests.get('${SHARED_LANGFUSE_URL}/api/public/observations?trace_id=' + trace_id, auth=auth)"
echo "if r.json().get('data'): print('TRACES FLOWING OK')"
echo "\""
