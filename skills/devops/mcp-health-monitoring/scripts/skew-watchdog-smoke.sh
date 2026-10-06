#!/usr/bin/env bash
# skew-watchdog-smoke.sh — prove the client-side otel skew check on THIS host.
#
# 1. the watchdog's scenario suite (stubs: threshold, alert, recovery, UNVERIFIED,
#    watched path)
# 2. the live probe under every agent-runtime interpreter the watchdog resolves,
#    plus which commit carries the probe
# 3. that the watchdog stays SILENT when those interpreters agree — unexpected output
#    on a healthy host is a false positive and fails this script
#
# Exit 0 = the check works here. Non-zero = suite failed, an interpreter is skewed,
# the probe is missing, or the watchdog spoke when it should not have.
# Usage: bash skills/devops/mcp-health-monitoring/scripts/skew-watchdog-smoke.sh
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
PY="${PYTHON:-python3}"
PROBE_REL="skills/devops/mcp-health-monitoring/scripts/otel-version-skew-probe.py"
cd "$REPO" || exit 2

echo "== 1. scenario suite (stubs) =="
PYTHONPATH=ops/scripts "$PY" tests/test_mcp_health_watchdog.py
suite=$?
echo "suite_exit=$suite"

echo
echo "== 2. live probe, every resolved runtime interpreter =="
echo "probe committed at: $(git log -1 --format='%h %ad %s' --date=short -- "$PROBE_REL")"
PYTHONPATH=ops/scripts "$PY" - <<'PY'
import contextlib, importlib.util, io, pathlib, tempfile

spec = importlib.util.spec_from_file_location(
    "wd", "ops/scripts/health/agent-mcp-health-watchdog.py"
)
wd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wd)

probe = wd.find_skew_probe()
print(f"probe: {probe}")
if probe is None:
    print("FAIL: no probe on this host — the check cannot run (expected the repo copy)")
    raise SystemExit(2)

skewed = []
for python in wd.runtime_pythons():
    ok, detail = wd.probe_otel_skew(python, probe)
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
print(f"interpreters_skewed={len(skewed)}")

if skewed:
    print("FAIL: an interpreter IS skewed on this host — the watchdog should be alerting")
    raise SystemExit(1)
if out:
    # Healthy interpreters must produce NO output. Anything here is a false positive
    # (or an unrelated warning this smoke test should not paper over).
    print(f"FAIL: watchdog spoke on a healthy host (false positive): {out}")
    raise SystemExit(1)
print("watchdog output after 2 runs: (silent) — no false positive")
raise SystemExit(0)
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
