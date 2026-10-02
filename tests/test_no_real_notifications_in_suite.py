#!/usr/bin/env python3
"""The test suite must not be able to reach Telegram.

Regression (Luke, 2026-10-02): a full-suite run delivered a REAL Telegram
"task-event" to the home channel — "[esther] task-event / learn $(whoami) —
literal: ⏳ pending (<uuid>)" — because tests/test_task_db_unit.py drives
task-db's cmd_add(), which post-commits a notification, and nothing in the suite
redirected lib/telegram_notify away from production. It looked like recurring
fleet noise and could never resolve, because each run minted a fresh UUID.

The suite-level guard is tests/conftest.py::_no_real_notifications (autouse).
This pins it so a future conftest edit cannot silently re-open the channel.

Run: python3 -m pytest tests/test_no_real_notifications_in_suite.py -q -s
"""
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

from lib import telegram_notify as tn  # noqa: E402


def test_the_suite_env_points_notify_away_from_production():
    env_file = Path(os.environ.get("TELEGRAM_NOTIFY_ENV_FILE", ""))
    assert env_file, "TELEGRAM_NOTIFY_ENV_FILE is unset — conftest's notify guard is gone"
    assert not env_file.exists(), (
        f"the suite's notify env file exists ({env_file}) — a test could send a real message")
    assert not os.environ.get("TELEGRAM_HOME_CHANNEL"), (
        "TELEGRAM_HOME_CHANNEL is set during the suite — notify could reach the human")


def test_notify_actually_refuses_under_the_suite(tmp_path, monkeypatch, capsys):
    """The guard is only real if the send path refuses, not just if env looks odd."""
    monkeypatch.setenv("TELEGRAM_NOTIFY_STATE_DIR", str(tmp_path / "state"))
    ok = tn.notify("suite probe — this message must never reach Telegram",
                   subject="[test] notify guard")
    assert ok is False, "notify() returned True during the test suite — it sent a real message"
    assert tn._load_env()[0] == "", "notify resolved a token during the suite"


def test_the_gate_is_the_env_file_and_notify_still_works_with_one(tmp_path, monkeypatch):
    """Control: prove the skip above is the GUARD working, not notify being broken.

    Points TELEGRAM_NOTIFY_ENV_FILE at a file that exists, and asserts the token
    resolves. `_load_env()` is read-only — nothing is sent.
    """
    env = tmp_path / "env"
    env.write_text("TELEGRAM_BOT_TOKEN=dummy-token\nTELEGRAM_HOME_CHANNEL=123\n")
    monkeypatch.setenv("TELEGRAM_NOTIFY_ENV_FILE", str(env))
    token, chat_id, _perms = tn._load_env()
    assert token == "dummy-token" and chat_id == "123", (
        "with a real env file notify does NOT resolve a token — the guard is not the "
        "thing doing the work, so the previous test proves nothing")
