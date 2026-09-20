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

    # 4. Paused-cron auto-resume: resumes a paused job, records cooldown,
    #    and respects the cooldown (no re-resume within RESUME_COOLDOWN_HOURS).
    with tempfile.TemporaryDirectory(prefix="remediate-resume-test-") as home:
        mod = _load_module(home)
        jobs_file = Path(home) / ".hermes" / "cron" / "jobs.json"
        jobs_file.parent.mkdir(parents=True, exist_ok=True)
        paused_job = {
            "id": "abcd1234",
            "name": "agent-fake-sync",
            "state": "paused",
            "enabled": False,
            "paused_at": "2026-09-20T01:00:00.000000+09:00",
        }
        active_job = {
            "id": "efgh5678",
            "name": "agent-normal",
            "state": "scheduled",
            "enabled": True,
        }
        jobs_file.write_text(
            json.dumps({"jobs": [paused_job, active_job]}), encoding="utf-8"
        )
        # Seed the watchdog state so the paused job is a legitimate candidate.
        wd_state = Path(home) / ".hermes-cortex" / "state" / "cron-failure-watchdog.json"
        wd_state.parent.mkdir(parents=True, exist_ok=True)
        wd_state.write_text(json.dumps({"abcd1234": {"alerted": True, "consecutive": 3}}))
        mod.subprocess = _FakeSubprocess()

        # First call resumes exactly the paused job, not the active one.
        res = mod.maybe_resume_paused_crons()
        resumed = [m for _, m in res if m.startswith("✅")]
        cmd = mod.subprocess.calls
        if len(resumed) != 1 or "agent-fake-sync" not in resumed[0]:
            failures.append(f"4a resume result wrong: {res}")
        if cmd != [["hermes", "cron", "resume", "abcd1234"]]:
            failures.append(f"4b resume command wrong: {cmd}")

        # Cooldown recorded → second call (immediately) is a no-op.
        res2 = mod.maybe_resume_paused_crons()
        if any(m.startswith("✅") for _, m in res2):
            failures.append(f"4c cooldown not honored: {res2}")
        if len(mod.subprocess.calls) != 1:
            failures.append(
                f"4d resume attempted again during cooldown: {mod.subprocess.calls}"
            )

        # 5. Gates: a paused job NOT flagged by the watchdog (deliberate hold)
        #    and one on the NEVER_RESUME denylist are both left untouched.
        denylisted = {"id": "195fa856001d", "name": "agent-hermes-update",
                      "state": "paused", "enabled": False,
                      "paused_at": "2026-09-20T01:00:00.000000+09:00"}
        held = {"id": "held0001", "name": "agent-on-hold", "state": "paused",
                "enabled": False, "paused_at": "2026-09-20T01:00:00.000000+09:00"}
        jobs_file.write_text(json.dumps({"jobs": [denylisted, held]}), encoding="utf-8")
        # denylisted IS watchdog-flagged (tests NEVER_RESUME); held is NOT
        # flagged at all (tests the watchdog-identity gate).
        wd_state.write_text(json.dumps({
            "195fa856001d": {"alerted": True, "consecutive": 3},
        }))
        res3 = mod.maybe_resume_paused_crons()
        if any(m.startswith("✅") for _, m in res3):
            failures.append(f"5a gated job resumed incorrectly: {res3}")

    if failures:
        print(f"FAIL ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(
        "PASS — agent-remediate-apply: 5/5 (timestamp-insensitive id, "
        "detail-sensitive id, main() reports once then silent, "
        "paused-cron auto-resume + watchdog gate + never-resume)"
    )
    return 0


class _FakeSubprocess:
    """Stub subprocess with .run() returning rc=0 and recording calls."""

    def __init__(self):
        self.calls = []

    def run(self, cmd, capture_output=False, text=False, timeout=30):
        self.calls.append(list(cmd))
        import subprocess as _real
        return _real.CompletedProcess(cmd, 0, stdout="resumed", stderr="")


if __name__ == "__main__":
    sys.exit(main())
