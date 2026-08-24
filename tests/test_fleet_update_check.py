#!/usr/bin/env python3
"""Tests for fleet-update-check.py — the fleet update progress checker.

Run: python3 -m pytest tests/test_fleet_update_check.py -q
"""
import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "fleet_update_check", _REPO / "ops" / "scripts" / "manage" / "fleet-update-check.py")
MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["fleet_update_check"] = MOD
_SPEC.loader.exec_module(MOD)


class FakeDB:
    """In-memory stand-in for the psql() query seam."""

    def __init__(self, pending=None, archived=None, replied=None, outbound=""):
        self.pending = pending or {}
        self.archived = archived or {}
        self.replied = replied or {}
        self.outbound = outbound
        self.queries = []

    def psql(self, sql):
        self.queries.append(sql)
        if "queue_name='inbox_esther'" in sql:
            # replies-to-esther query: find which agent it's about
            for agent in MOD.TASKS:
                if f"LIKE '%{agent}%'" in sql:
                    return str(self.replied.get(agent, 0))
            return "0"
        if "messages_archive" in sql:
            for agent, tid in MOD.TASKS.items():
                if f"inbox_{agent}" in sql and tid in sql:
                    return str(self.archived.get(agent, 0))
            return "0"
        if "LIKE 'out_%'" in sql:
            return self.outbound
        for agent, tid in MOD.TASKS.items():
            if f"inbox_{agent}" in sql and tid in sql:
                return str(self.pending.get(agent, 0))
        return "0"


def _run(db):
    """Run main() with the psql seam replaced; capture stdout."""
    import io
    import contextlib
    real_psql = MOD.psql
    MOD.psql = db.psql
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            MOD.main()
    finally:
        MOD.psql = real_psql
    return buf.getvalue()


def test_all_pending_reported():
    """All agents still pending → report shows PENDING for each."""
    db = FakeDB(pending={"titus": 1, "joseph": 1, "kustos": 1, "gisu": 1})
    out = _run(db)
    assert "titus" in out and "PENDING" in out
    assert "PENDING" in out and out.count("PENDING") >= 4


def test_done_agents_archived():
    """Agents that archived their task → DONE, not PENDING."""
    db = FakeDB(pending={"titus": 0}, archived={"titus": 1})
    out = _run(db)
    assert "titus" in out and "DONE" in out


def test_replies_to_esther_reported():
    db = FakeDB(pending={"titus": 0}, archived={"titus": 1},
                replied={"titus": 2})
    out = _run(db)
    assert "replies-to-esther: 2" in out


def test_outbound_queues_listed():
    db = FakeDB(pending={"titus": 0}, archived={"titus": 1},
                outbound="out_titus|1\nout_joseph|2")
    out = _run(db)
    assert "outbound queues" in out
