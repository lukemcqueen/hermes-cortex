#!/usr/bin/env python3
"""Tests for bot_locks.py — per-bot advisory locks (ADR-0005, SRE finding).

The SRE's key mechanism: `pg_try_advisory_lock(bot_id_hash)` held for the
poller's lifetime solves 409-avoidance, migration exclusivity, AND
multi-server active-passive in ONE mechanism. A second gateway that cannot
acquire the lock must NOT poll the bot (it stays unowned/standby) — the
409 class dies at the database, before the Telegram API.

Run: python3 -m pytest tests/test_bot_locks.py -q
"""
import importlib.util
import threading
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "bot_locks", _REPO / "ops" / "scripts" / "bot_locks.py")
LOCKS = importlib.util.module_from_spec(_SPEC)
import sys
sys.modules["bot_locks"] = LOCKS
_SPEC.loader.exec_module(LOCKS)


class FakeConn:
    """Minimal psycopg-like cursor wrapper for the advisory lock calls."""

    def __init__(self, held: dict):
        self.held = held          # key -> owner count
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        key = params[0]
        if "pg_try_advisory_lock" in sql:
            if self.conn.held.get(key, 0) > 0:
                self.result = False
            else:
                self.conn.held[key] = 1
                self.result = True
        elif "pg_advisory_unlock" in sql:
            self.conn.held.pop(key, None)
            self.result = True
        elif "pg_try_advisory_xact_lock" in sql:
            self.result = self.conn.held.get(key, 0) == 0
        return self

    def fetchone(self):
        return (self.result,)


@pytest.fixture
def held():
    return {}


def test_acquire_succeeds_first(held):
    conn = FakeConn(held)
    assert LOCKS._try_lock(conn, 42) is True
    assert 42 in held


def test_second_owner_denied(held):
    """Second gateway trying the same bot → lock DENIED (stands down)."""
    conn = FakeConn(held)
    assert LOCKS._try_lock(conn, 42) is True
    conn2 = FakeConn(held)
    assert LOCKS._try_lock(conn2, 42) is False  # already held


def test_release_frees(held):
    conn = FakeConn(held)
    LOCKS._try_lock(conn, 42)
    LOCKS._unlock(conn, 42)
    assert 42 not in held
    assert LOCKS._try_lock(FakeConn(held), 42) is True


def test_different_bots_independent(held):
    """Bot A held doesn't block bot B (per-bot, not global)."""
    assert LOCKS._try_lock(FakeConn(held), 1) is True
    assert LOCKS._try_lock(FakeConn(held), 2) is True  # different bot


def test_lock_holder_context_manager(held):
    with LOCKS.BotLock(lambda: FakeConn(held), 7) as ok:
        assert ok is True
    assert 7 not in held  # released on exit
