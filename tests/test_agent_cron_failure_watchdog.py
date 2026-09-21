"""agent-cron-failure-watchdog state tests.

The fleet had NO consecutive-failure detection: agent-push-metrics failed
1053 times in a row (2026-08-30..09-14) with no counter, no auto-pause, no
re-alert — the sensor dedups to silence and nothing pauses failing crons.
This watchdog counts consecutive `last_status: error` per job and after
N consecutive failures (default 3): alerts (stdout = delivery) and pauses
the cron via `hermes cron pause`, stopping the retry loop and escalating
to the operator instead of failing 1000+ times silently.
"""
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "ops" / "scripts" / "health" / "agent-cron-failure-watchdog.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "agent_cron_failure_watchdog", SRC
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def wd(tmp_path):
    mod = _load()
    # Re-point state dir at tmp so tests never touch the real state file.
    mod.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    mod.STATE_FILE = tmp_path / "state.json"
    return mod


def _job(jid, status, name="test-job", enabled=True, paused=False):
    return {
        "id": jid,
        "name": name,
        "last_status": status,
        "enabled": enabled,
        "paused_at": "yes" if paused else None,
    }


class TestConsecutiveCounting:
    def test_first_failure_counts_one_no_alert(self, wd):
        # One error tick is transient tolerance — count, but no alert/pause.
        jobs = [_job("a1", "error")]
        alerts, to_pause = wd._evaluate(jobs)
        assert to_pause == []
        assert alerts == []  # below threshold
        st = wd._load_state()
        assert st["a1"]["consecutive"] == 1

    def test_three_consecutive_failures_alert_and_pause(self, wd):
        # First tick counts; second counts; third crosses threshold.
        j = _job("a1", "error")
        wd._evaluate([j])
        wd._evaluate([j])
        alerts, to_pause = wd._evaluate([j])
        assert to_pause == ["a1"]
        assert len(alerts) == 1
        assert "3 consecutive" in alerts[0]

    def test_success_resets_counter(self, wd):
        j = _job("a1", "error")
        wd._evaluate([j])
        wd._evaluate([j])
        ok = _job("a1", "ok")
        alerts, to_pause = wd._evaluate([ok])
        assert to_pause == []
        assert alerts == []
        assert wd._load_state()["a1"]["consecutive"] == 0

    def test_paused_job_not_counted(self, wd):
        # A job already paused (by scheduler or watchog) stays out of the loop.
        j = _job("a1", "error", paused=True)
        alerts, to_pause = wd._evaluate([j])
        assert to_pause == []
        assert alerts == []
        assert "a1" not in wd._load_state()

    def test_disabled_job_not_counted(self, wd):
        j = _job("a1", "error", enabled=False)
        alerts, to_pause = wd._evaluate([j])
        assert to_pause == []
        assert "a1" not in wd._load_state()


class TestRecoveryIsSilent:
    def test_recovery_does_not_emit_alert_or_exit(self, wd):
        # A cron that was alerted (paused) then returns to ok RECOVERED. That is a
        # SUCCESS, not a failure: the watchdog must be silent (no alert, no exit 1).
        # Regression: the recovery line was appended to `alerts`, so run_once() exited
        # 1, marking the watchdog's OWN last_status=error and cascading into self-pause.
        j = _job("a1", "error")
        wd._evaluate([j]); wd._evaluate([j]); wd._evaluate([j])  # cross threshold, alerted
        recovered = _job("a1", "ok")
        alerts, to_pause = wd._evaluate([recovered])
        assert alerts == []        # recovery is silent, not an alert
        assert to_pause == []      # nothing to pause on recovery
        st = wd._load_state()
        assert st["a1"]["alerted"] is False  # state reset so a future failure re-alerts
        assert st["a1"]["consecutive"] == 0

    def test_recovery_subsequent_failure_realerts(self, wd):
        # After a silent recovery resets the state, a NEW failure streak must alert
        # again (recovery must not permanently mute the cron).
        j = _job("a1", "error")
        [wd._evaluate([j]) for _ in range(3)]  # alerted
        wd._evaluate([_job("a1", "ok")])        # silent recovery, state reset
        alerts, to_pause = wd._evaluate([j]); wd._evaluate([j])
        alerts, to_pause = wd._evaluate([j])    # new streak crosses threshold
        assert len(alerts) == 1
        assert "3 consecutive" in alerts[0]
        assert to_pause == ["a1"]


class TestSelfExclusion:
    def test_watchdog_never_counts_its_own_errors(self, wd):
        # The watchdog must not evaluate its own job. When it pauses a BROKEN cron it
        # exits 1 (delivery), so its own last_status turns error; if it counted itself
        # it would accumulate 3 self-errors and pause ITSELF — the fleet-wide self-pause.
        me = _job("self-id", "error", name="agent-cron-failure-watchdog")
        alerts, to_pause = wd._evaluate([me])
        alerts2, to_pause2 = wd._evaluate([me])
        alerts3, to_pause3 = wd._evaluate([me])
        assert to_pause == [] and to_pause2 == [] and to_pause3 == []
        assert alerts == [] and alerts2 == [] and alerts3 == []
        assert "self-id" not in wd._load_state()  # never even tracked

    def test_other_watchdogs_still_monitored(self, wd):
        # Self-exclusion must be scoped to THIS script's name only — sibling watchdogs
        # (and every other cron) are still counted and paused normally.
        sibling = _job("sib", "error", name="agent-other-watchdog")
        wd._evaluate([sibling]); wd._evaluate([sibling])
        alerts, to_pause = wd._evaluate([sibling])
        assert to_pause == ["sib"]
        assert any("other-watchdog" in a for a in alerts)


class TestPauseAndAlertNoisyProps:
    def test_unique_job_names_in_alert(self, wd):
        # 1053-failure scenario: the alert must carry the job name so the
        # operator knows WHAT to fix, not just "a cron failed".
        j = _job("x", "error", name="agent-push-metrics")
        wd._evaluate([j])
        wd._evaluate([j])
        alerts, to_pause = wd._evaluate([j])
        assert "agent-push-metrics" in alerts[0]
        assert to_pause == ["x"]

    def test_no_repeat_alert_until_reset(self, wd):
        # After pausing, remaining ticks must not re-alert (would spam).
        j = _job("a1", "error")
        wd._evaluate([j]); wd._evaluate([j]); wd._evaluate([j])
        alerts, to_pause = wd._evaluate([j])  # 4th tick — still error, still counted
        assert alerts == []  # already alerted at threshold; not re-alerted
        assert to_pause == []  # already paused

    def test_state_roundtrip(self, wd):
        j = _job("a1", "error")
        wd._evaluate([j])
        raw = json.loads(wd.STATE_FILE.read_text())
        assert raw["a1"]["consecutive"] == 1


class TestMainDispatch:
    def test_main_ok_when_jobs_healthy(self, wd, tmp_path, monkeypatch):
        jobs_path = tmp_path / "jobs.json"
        jobs_path.write_text(json.dumps({
            "jobs": [
                _job("a", "ok", "healthy-one"),
                _job("b", "ok", "healthy-two"),
            ]
        }))
        monkeypatch.setattr(wd, "CRON_JOBS_FILE", jobs_path)
        assert wd.run_once() == 0