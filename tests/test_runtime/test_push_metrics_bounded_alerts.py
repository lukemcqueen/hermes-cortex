"""agent-push-metrics.sh — bounded alerting on a dead sink (2026-09-23).

Why this exists: the cron runs every 5m on every host (288 runs/day). When the
sink is dead for a reason no agent can fix (the xx005 reverse proxy was never
deployed — a root action), the old behaviour was exit 1 on every tick: 1053
consecutive failures, an escalation loop, and a watchdog that kept pausing the
job. The rule now:

  first failure of a streak   → exit 1 (self-diagnosing alert)
  same streak, inside cooldown → exit 0 (suppressed; signal already delivered)
  cooldown elapsed            → exit 1 again
  recovery                    → exit 0 + state cleared
  state file unwritable       → exit 1 every run (fail-closed: we cannot prove
                                a prior alert happened, so we never suppress)

These tests run the REAL script with a stub curl on PUSH_METRICS_CURL.
"""
import os
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "ops" / "scripts" / "manage" / "agent-push-metrics.sh"

SINK_URL = "http://127.0.0.1:19999/api/v1/import/prometheus"


def _stub_curl(tmp: Path, code: str) -> Path:
    """A curl that consumes stdin and always reports `code` (000 = refused)."""
    p = tmp / "stub-curl"
    p.write_text(
        "#!/usr/bin/env bash\n"
        "cat >/dev/null 2>&1 || true\n"
        f"printf '%s' '{code}'\n"
    )
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return p


def _run(tmp: Path, code: str, *, cooldown=None, state=None, env_extra=None):
    home = tmp / "home"
    (home / ".hermes-cortex").mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "AGENT_NAME": "test-agent",
        "VICTORIA_METRICS_URL": SINK_URL,
        "PUSH_METRICS_CURL": str(_stub_curl(tmp, code)),
        "PUSH_METRICS_STATE_FILE": str(state or (tmp / "state" / "push-metrics.state")),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    if cooldown is not None:
        env["PUSH_METRICS_ALERT_COOLDOWN_S"] = str(cooldown)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=180
    )


def test_first_failure_alerts_and_records_the_streak(tmp_path):
    state = tmp_path / "state" / "push-metrics.state"
    r = _run(tmp_path, "000", state=state)
    assert r.returncode == 1, "a new outage must still be loud"
    assert "SINK UNREACHABLE" in r.stderr
    assert "refused" in r.stderr, "the alert must say what a 000 means"
    assert "docs/runbooks/push-metrics-nginx-deploy.md" in r.stderr, "must be actionable"
    assert state.is_file()
    assert "CONSECUTIVE=1" in state.read_text()


def test_same_streak_is_suppressed(tmp_path):
    state = tmp_path / "state" / "push-metrics.state"
    assert _run(tmp_path, "000", state=state).returncode == 1
    r = _run(tmp_path, "000", state=state)
    assert r.returncode == 0, "later ticks of the same outage must not error the cron"
    assert "still down" in r.stderr
    assert "CONSECUTIVE=2" in state.read_text()


def test_cooldown_elapsed_re_alerts(tmp_path):
    state = tmp_path / "state" / "push-metrics.state"
    assert _run(tmp_path, "000", state=state).returncode == 1
    assert _run(tmp_path, "000", state=state).returncode == 0
    r = _run(tmp_path, "000", cooldown=0, state=state)
    assert r.returncode == 1, "an unresolved outage must be re-reported"
    assert "cooldown" in r.stderr


def test_recovery_clears_the_state(tmp_path):
    state = tmp_path / "state" / "push-metrics.state"
    assert _run(tmp_path, "000", state=state).returncode == 1
    assert state.is_file()
    r = _run(tmp_path, "204", state=state)
    assert r.returncode == 0
    assert "reachable again" in r.stderr
    assert not state.exists(), "a recovered sink must alert immediately next time"


def test_unwritable_state_fails_closed(tmp_path):
    """Cannot record the alert → cannot prove it happened → keep alerting."""
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    r = _run(tmp_path, "000", state=blocker / "sub" / "push-metrics.state")
    assert r.returncode == 1
    assert "suppression impossible" in r.stderr


def test_no_sink_configured_is_silent_success(tmp_path):
    """Pushing is optional: an unset URL means the feature is off, not broken."""
    home = tmp_path / "home"
    (home / ".hermes-cortex").mkdir(parents=True, exist_ok=True)
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "AGENT_NAME": "test-agent",
        "PUSH_METRICS_STATE_FILE": str(tmp_path / "state" / "push-metrics.state"),
    }
    r = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=120
    )
    assert r.returncode == 0
    assert "metrics push disabled" in r.stderr
