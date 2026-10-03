#!/usr/bin/env bash
# run-evidence.sh — regenerate EVIDENCE.md, the committed proof for the pi extension.
#
# The change's claims are meant to be EXECUTABLE, not prose a reader has to take
# on trust. This script re-runs the two checks and writes their real output to
# EVIDENCE.md, including the RED case (the same guard against the PRE-FIX
# extension, which must fail) so the guard is demonstrably a guard.
#
#   bash ops/install/harnesses/pi/run-evidence.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# HERE is <repo>/ops/install/harnesses/pi — FOUR levels below the repo root
# (pi → harnesses → install → ops → repo). Three levels lands on ops/, where
# node finds no such file and pytest collects 0 tests.
REPO="$(cd "$HERE/../../../.." && pwd)"
OUT="$HERE/EVIDENCE.md"
PREFIX_COMMIT="${PREFIX_COMMIT:-48e85271}"   # the commit before the fix
OLD_EXT_PATH="ops/install/harnesses/pi/extensions/cortex-context.ts"

echo "→ wiring guard (fixed extension)"
node_out="$(cd "$REPO" && node ops/install/harnesses/pi/verify-extension.mjs 2>&1)"; node_rc=$?

echo "→ test suite (context harnesses + gateway agent registry)"
py_out="$(cd "$REPO" && python3 -m pytest tests/test_context_harnesses.py \
  tests/test_gateway_agent_registry.py -q 2>&1)"; py_rc=$?

echo "→ wiring guard (PRE-FIX extension — must FAIL)"
tmp="$(mktemp -d)"; mkdir -p "$tmp/extensions"
cp "$HERE/verify-extension.mjs" "$tmp/"
(cd "$REPO" && git show "${PREFIX_COMMIT}:${OLD_EXT_PATH}") > "$tmp/extensions/cortex-context.ts" 2>/dev/null
old_out="$(node "$tmp/verify-extension.mjs" 2>&1)"; old_rc=$?
rm -rf "$tmp"

verdict() { [ "$1" -eq 0 ] && echo "PASS (exit 0)" || echo "FAIL (exit $1)"; }

# ── Assert on the FULL captured output ──────────────────────────────────────
# A `tail` window can hide a failure above it, so the pass/fail markers are
# matched against the whole capture, and a missing marker is a hard error.
grep -q "EXTENSION OK" <<<"$node_out" \
  || { echo "❌ guard did not report a passing extension (full output above)"; exit 1; }
grep -qE "[0-9]+ passed" <<<"$py_out" \
  || { echo "❌ test suite did not report passing tests"; exit 1; }
grep -q "EXTENSION BROKEN" <<<"$old_out" \
  || { echo "❌ guard did not reject the pre-fix extension — it is not discriminating"; exit 1; }

# Pin the artifacts: a reviewer whose diff is truncated can still confirm that
# the file this evidence was produced from is the file that is committed.
EXT_SHA="$(sha256sum "$REPO/$OLD_EXT_PATH" | cut -d' ' -f1)"
GUARD_SHA="$(sha256sum "$HERE/verify-extension.mjs" | cut -d' ' -f1)"
EVID_SHA="$(sha256sum "$HERE/run-evidence.sh" | cut -d' ' -f1)"

# ── Captured RUNTIME state ──────────────────────────────────────────────────
# These sections record what the host reports RIGHT NOW. They are capture, not
# guard: the re-runnable guards are the test suite and verify-extension.mjs,
# which need no prior state.
#
# Chat ids are PERSONAL IDENTIFIERS and this is a public repo, so the pinned key
# is shown with its id REDACTED — the shape (`hc-pi-<chat>`) is the evidence, the
# specific id is not.
PI_BIN="${PI_BIN:-$HOME/.pi/agent/bin/pi}"
CTX_CLI="${HOME}/.hermes-cortex/scripts/cortex-context.py"
if [ -x "$PI_BIN" ]; then
  mcp_out="$("$PI_BIN" mcp list 2>&1 | grep -A2 'cortex-context' || true)"
else
  mcp_out="(pi not installed here)"
fi
if [ -f "$CTX_CLI" ]; then
  key_out="$(python3 "$CTX_CLI" session_list '{}' 2>&1 \
    | grep -o 'hc-pi-[0-9]*' | sed -E 's/[0-9]+$/NNNNNNNNNN/' | sort -u | head -5 || true)"
  [ -n "$key_out" ] || key_out="(no hc-pi-* session keys recorded yet)"
else
  key_out="(cortex-context CLI not deployed here)"
fi

{
  echo "# pi extension — committed, re-runnable evidence"
  echo
  echo "Regenerate with: \`bash ops/install/harnesses/pi/run-evidence.sh\`"
  echo
  echo "Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')  ·  host: $(hostname)"
  echo
  echo "Artifacts this evidence was produced from (verify with \`sha256sum\`):"
  echo
  echo '```'
  echo "$EXT_SHA  ${OLD_EXT_PATH}"
  echo "$GUARD_SHA  ops/install/harnesses/pi/verify-extension.mjs"
  echo "$EVID_SHA  ops/install/harnesses/pi/run-evidence.sh"
  echo '```'
  echo
  echo "The guard loads the REAL extension through pi's own jiti loader, hands it"
  echo "a stub \`pi\`, and CALLS \`execute(id, params)\` against a throwaway CLI — the"
  echo "store is never touched. A static grep cannot see a tool signature or a"
  echo "schema shape, which is why the bug shipped; this can."
  echo
  echo "## 1. Fixed extension — wiring executes: $(verdict "$node_rc")"
  echo
  echo '```'
  echo "$node_out" | tail -6
  echo '```'
  echo
  echo "## 2. Test suite — the two files this change touches: $(verdict "$py_rc")"
  echo
  echo '```'
  echo "$py_out" | tail -4
  echo '```'
  echo
  echo "## 3. PRE-FIX extension (${PREFIX_COMMIT}) — same guard, must fail: $(verdict "$old_rc")"
  echo
  echo "The pre-fix extension registered 11 tools BY HAND. The one-way-in invariant"
  echo "rejects that — which is what makes this a guard rather than a happy path:"
  echo
  echo '```'
  echo "$old_out" | grep -E 'ZERO tools|EXTENSION BROKEN' | head -3
  echo '```'
  echo
  echo "---"
  echo
  echo "## 4. MCP registration on this host (captured, not a guard)"
  echo
  echo "The tool surface is a CONFIG entry pointing at the shared server. The"
  echo "re-runnable guard for this is"
  echo "\`tests/test_context_harnesses.py::test_pi_context_tools_are_registered_as_the_shared_MCP_server\`."
  echo
  echo '```'
  echo "$mcp_out"
  echo '```'
  echo
  echo "## 5. Pinned per-chat session keys (captured, not a guard)"
  echo
  echo "The gateway declares \`env: {CORTEX_SESSION_KEY: {session_id}}\` on the command"
  echo "backend, so each chat gets its OWN key instead of the shared fallback. Ids are"
  echo "redacted — a chat id is a personal identifier and this is a public repo. The"
  echo "re-runnable guard for the seam is"
  echo "\`tests/test_gateway_agent_registry.py::test_command_backend_pins_session_identity_via_spec_env\`."
  echo
  echo '```'
  echo "$key_out"
  echo '```'
  echo
  echo "---"
  echo
  echo "## What this does and does not prove"
  echo
  echo "Proves: the tool definitions the extension hands pi have a callable"
  echo "\`execute\` with the pi 1.0.0 AgentTool shape, \`parameters\` is a valid object"
  echo "schema, and the model's arguments reach the CLI and come back as an"
  echo "\`AgentToolResult\`."
  echo
  echo "Does not prove: model-side behaviour inside a live pi session, or that the"
  echo "store returned particular data. Those are exercised by running pi itself"
  echo "(\`pi --session-id <id> \"call mem_context\"\`); the store is separately covered"
  echo "by \`tests/test_context_harnesses.py::test_cli_reaches_the_store_and_exits_zero\`."
} > "$OUT"

echo "→ wrote $OUT"
[ "$node_rc" -eq 0 ] || { echo "❌ fixed-extension guard failed"; exit 1; }
[ "$py_rc" -eq 0 ] || { echo "❌ test suite failed"; exit 1; }
[ "$old_rc" -ne 0 ] || { echo "❌ guard passed on the PRE-FIX extension — it is not a guard"; exit 1; }
echo "✅ evidence regenerated and consistent"
