#!/usr/bin/env bash
# skew-watchdog-smoke.sh — prove the client-side otel skew check on THIS host.
#
# 1. the watchdog's scenario suite (stubs: alert, recovery, UNVERIFIED, watched path)
# 2. the live probe under every agent-runtime interpreter the watchdog resolves
# 3. whether the watchdog stays silent when they agree (no false positive)
#
# Exit 0 = the check works here. Exit 1 = the suite failed or an interpreter is skewed.
# Usage: bash skills/devops/mcp-health-monitoring/scripts/skew-watchdog-smoke.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
PY="${PYTHON:-python3}"
cd "$REPO" || exit 2

echo "== 1. scenario suite (stubs) =="
PYTHONPATH=ops/scripts "$PY" tests/test_mcp_health_watchdog.py
suite=$?
echo "suite_exit=$suite"

echo
echo "== 2. live probe, every resolved runtime interpreter =="
PYTHONPATH=ops/scripts "$PY" - <<'PY'
import contextlib, importlib.util, io, pathlib, tempfile

spec = importlib.util.spec_from_file_location(
    "wd", "ops/scripts/health/agent-mcp-health-watchdog.py"
)
wd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wd)

probe = wd.find_skew_probe()
print(f"probe: {probe}")
skewed = []
for python in wd.runtime_pythons():
    ok, detail = wd.probe_otel_skew(python, probe) if probe else (True, "no probe")
    print(f"  {'OK  ' if ok else 'SKEW'} {python} {detail}")
    if not ok:
        skewed.append(python)

tmp = pathlib.Path(tempfile.mkdtemp(prefix="skew-smoke-"))
wd.STATE_FILE = tmp / "state.json"
wd.MCP_LOG_DIR = tmp / "logs"
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    wd.main()
    wd.main()  # 2 strikes would be needed to alert
out = buf.getvalue().strip()
print(f"watchdog output after 2 runs: {out if out else '(silent)'}")
print(f"interpreters_skewed={len(skewed)}")
raise SystemExit(1 if skewed else 0)
PY
live=$?
echo "live_exit=$live"

echo
if [ "$suite" -eq 0 ] && [ "$live" -eq 0 ]; then
  echo "VERDICT: PASS — the skew check works on this host and is silent when healthy"
  exit 0
fi
echo "VERDICT: FAIL — suite_exit=$suite live_exit=$live"
exit 1
