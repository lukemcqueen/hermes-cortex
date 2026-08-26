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
