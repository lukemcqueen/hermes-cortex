#!/usr/bin/env python3
"""Hermetic suite for agent-remediate-apply (dedup fix, 2026-08-31).

Proves the seen-file dedup is stable against the sensor's per-run timestamp:

  1. make_issue_id: same type+detail, different timestamps -> EQUAL ids
  2. make_issue_id: different detail -> different ids
  3. main(): persistent service_down issue (fresh timestamp each call)
     -> first call reports the failure once, second call is silent
     (empty stdout, exit 0) and the handler is NOT invoked again.

Run:  python3 tests/test_agent_remediate_apply.py
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "scripts" / "agent" / "agent-remediate-apply.py"

# ── Helpers ─────────────────────────────────────────────────────


def _load_module(home: str):
    """Import the script as a module with HOME pointed at an isolated dir."""
    os.environ["HOME"] = home
    sys.path.insert(0, str(REPO / "ops" / "scripts"))  # hermes_tz resolution
    spec = importlib.util.spec_from_file_location("agent_remediate_apply", SCRIPT)
    assert spec is not None and spec.loader is not None, "import spec failed"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_sensor_output(home: str, job_id: str, issues: list[dict]):
    """Create a fake sensor cron-output dir + jobs.json under the isolated HOME."""
    root = Path(home) / ".hermes" / "cron" / "output" / job_id
    root.mkdir(parents=True, exist_ok=True)
    (root / "latest.md").write_text(json.dumps(issues), encoding="utf-8")
    jobs = Path(home) / ".hermes" / "cron" / "jobs.json"
    jobs.parent.mkdir(parents=True, exist_ok=True)
    jobs.write_text(
        json.dumps({"jobs": [{"name": "agent-remediation-sensor", "id": job_id}]}),
        encoding="utf-8",
    )


def _capture(mod, fn) -> tuple[int, str]:
    """Run fn with stdout captured; returns (returncode, stdout)."""
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = fn()
    finally:
        sys.stdout = old
    return rc, buf.getvalue()


# ── Tests ───────────────────────────────────────────────────────


def main() -> int:
    failures = []

    with tempfile.TemporaryDirectory(prefix="remediate-apply-test-") as home:
        mod = _load_module(home)

        # 1. Timestamp-insensitive: same type+detail, different timestamps -> EQUAL
        a = {
            "type": "service_down",
            "detail": "Remote Agent Bus unreachable",
            "timestamp": "2026-08-31T00:20:20Z",
        }
        b = {
            "type": "service_down",
            "detail": "Remote Agent Bus unreachable",
            "timestamp": "2026-08-31T00:30:20Z",
        }
        id_a, id_b = mod.make_issue_id(a), mod.make_issue_id(b)
        if id_a != id_b:
            failures.append(
                f"1 timestamp-insensitive: ids differ {id_a!r} != {id_b!r}"
            )

        # 2. Detail-sensitive: different detail -> different ids
        c = {"type": "service_down", "detail": "Disk full", "timestamp": "2026-08-31T00:20:20Z"}
        id_c = mod.make_issue_id(c)
        if id_a == id_c:
            failures.append(f"2 detail-sensitive: ids equal {id_a!r} == {id_c!r}")

        # 3. main(): persistent issue with fresh timestamp each call ->
        #    first call reports once; second call silent + handler NOT re-invoked
        job_id = "testjob0001"
        calls: list[str] = []
        mod.run_cmd = lambda cmd, timeout=30: (calls.append(cmd), ("", "", 1))[1]

        def issue(ts: str) -> dict:
            return {
                "type": "service_down",
                "detail": "Remote Agent Bus unreachable",
                "timestamp": ts,
                "context": {"service": "cortex-bus"},
            }

        _make_sensor_output(home, job_id, [issue("2026-08-31T00:20:20Z")])
        rc1, out1 = _capture(mod, mod.main)
        _make_sensor_output(home, job_id, [issue("2026-08-31T00:30:20Z")])
        rc2, out2 = _capture(mod, mod.main)

        if rc1 != 0 or "could not be fixed" not in out1:
            failures.append(f"3a first run reports once: rc={rc1} out={out1!r}")
        if rc2 != 0 or out2 != "":
            failures.append(f"3b second run silent: rc={rc2} out={out2!r}")
        if len(calls) != 1:
            failures.append(
                f"3c handler invoked {len(calls)}x (expected exactly 1): {calls!r}"
            )

    if failures:
        print(f"FAIL ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(
        "PASS — agent-remediate-apply: 3/3 (timestamp-insensitive id, "
        "detail-sensitive id, main() reports once then silent)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
