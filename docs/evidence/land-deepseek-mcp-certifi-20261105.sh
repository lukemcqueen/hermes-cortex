#!/usr/bin/env bash
# land-deepseek-mcp-certifi-20261105.sh — re-runnable capture for the
# ops(deepseek-mcp) certifi pin + TLS-guard landing (commit 60caf765).
#
# Every command prints its own rc. Read-only: bash -n, the hermetic guard
# test (temp HOME), the A4 gate (read-only scan), the guard against esther's
# real mcp.json (read-only), and fix-cortex-venv --check (import verification,
# changes nothing).
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AV="$HOME/.steadfaste-fleet/scripts/adversarial-verify.py"

say(){ printf '%s\n' "$*"; }
run(){ printf '\n$ %s\n' "$*"; eval "$@"; rc=$?; printf 'rc=%s\n' "$rc"; }

say "=== bash -n (syntax) ==="
run "bash -n \"$REPO/ops/scripts/manage/check-deepseek-mcp-tls.sh\""
run "bash -n \"$REPO/tests/test_deepseek_mcp_tls.sh\""

say "=== hermetic guard regression test ==="
run "bash \"$REPO/tests/test_deepseek_mcp_tls.sh\""

say "=== adversarial-verify A4 gate ==="
run "python3 \"$AV\" --file \"$REPO/ops/scripts/manage/check-deepseek-mcp-tls.sh\" --level A4 --gate"
run "python3 \"$AV\" --file \"$REPO/tests/test_deepseek_mcp_tls.sh\" --level A4 --gate"

say "=== guard vs esther's real mcp.json (no deepseek entry -> rc=1 expected) ==="
run "bash \"$REPO/ops/scripts/manage/check-deepseek-mcp-tls.sh\""

say "=== canonical venv imports the new 8-declared set (--check, changes nothing) ==="
run "python3 \"$REPO/ops/scripts/manage/fix-cortex-venv.py\" --check"

say "=== done ==="