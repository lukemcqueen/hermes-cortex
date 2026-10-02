"""Shared pytest fixtures for the hermes-cortex test suite.

Hermeticity contract (slice 74f2ac46 — precommit test-DB isolation):
the global git `core.hookspath` (~/.hermes-cortex/hooks) fires the
pre-commit-score hook on EVERY `git commit` — including commits made inside
pytest temp repos (test_bus_task_context.py, test_executor_context_builder.py,
...). Without isolation those commits wrote `precommit-<testrepo>-HEAD/*`
rows into the PROD loop-governance DB, polluting the review queue (5,628
fixture rows cleared by the orchestrator batch on 2026-08-26).

This autouse session fixture points the scorer at a SCRATCH sqlite DB so test
commits stay hermetic — same pattern as task-db/review-sweep hermetic tests.
"""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _hermetic_precommit_db(tmp_path_factory):
    """Point pre-commit-score at a scratch DB for every test in the suite.

    pre-commit-score reads PRE_COMMIT_SCORE_DB (default: the PROD
    ~/.hermes-cortex/data/loop-governance.db). Subprocesses spawned by tests
    (git commit) inherit os.environ, so the hook writes to the scratch DB and
    the prod review queue never sees test-fixture cycles.
    """
    scratch = tmp_path_factory.mktemp("precommit-scratch")
    os.environ["PRE_COMMIT_SCORE_DB"] = str(scratch / "loop-governance.db")
    yield


@pytest.fixture(scope="session", autouse=True)
def _no_real_notifications(tmp_path_factory):
    """A test run must NEVER be able to message the human.

    `lib/telegram_notify` resolves its token from TELEGRAM_NOTIFY_ENV_FILE and
    sends to TELEGRAM_HOME_CHANNEL, and nothing in the suite pointed either away
    from production — so any test driving a notify path sent a REAL message.
    Observed (Luke, 2026-10-02): tests/test_task_db_unit.py's
    `test_shell_payload_stored_as_literal` calls cmd_add("learn $(whoami) —
    literal", …), which post-commits a task-event, so a full-suite run delivered
    "[esther] task-event / learn $(whoami) — literal: ⏳ pending (<uuid>)" to
    Telegram ~every time. The case only intends to prove the string is stored as
    a LITERAL, never that it notifies.

    Fail-safe: point the env file at a path that does not exist (no token →
    notify() logs a skip and returns False) and clear the home channel. A test
    that genuinely exercises the send path sets its own TELEGRAM_NOTIFY_ENV_FILE
    via monkeypatch — test_telegram_notify_unit.py already does.
    """
    scratch = tmp_path_factory.mktemp("notify-off")
    os.environ["TELEGRAM_NOTIFY_ENV_FILE"] = str(scratch / "absent.env")
    os.environ["TELEGRAM_NOTIFY_STATE_DIR"] = str(scratch / "state")
    os.environ.pop("TELEGRAM_HOME_CHANNEL", None)
    yield
