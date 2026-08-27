#!/usr/bin/env python3
"""Tests for bus_outbox — enterprise bus retry (2026-08-27).

Run: python3 -m pytest tests/test_bus_outbox.py -v

Covers: atomic enqueue, deterministic dedup filenames, backoff timing,
resend-success deletion, dedup-on-resend, poison-pill quarantine
(corrupt + max attempts), flock concurrency, bus_send fallback wiring.
"""
import importlib.util
import json
import os
import sqlite3  # noqa: F401 — kept for parity with sibling suites
import sys
import tempfile
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parent.parent / "ops" / "scripts" / "lib"
sys.path.insert(0, str(_LIB))  # bus_outbox does `from cortex_bus import ...` at top


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def outbox(tmp_path, monkeypatch):
    """Load bus_outbox against a temp retry dir."""
    monkeypatch.setenv("CORTEX_BUS_RETRY_DIR", str(tmp_path / "bus-retry"))
    mod = _load("bus_outbox", _LIB / "bus_outbox.py")
    return mod


@pytest.fixture()
def cortex_bus(outbox, monkeypatch, tmp_path):
    """Load cortex_bus with the outbox retry dir pointing at temp."""
    monkeypatch.setenv("CORTEX_BUS_RETRY_DIR", str(tmp_path / "bus-retry"))
    mod = _load("cortex_bus", _LIB / "cortex_bus.py")
    return mod


# ────────────────────────────────────────────────────────────────
# enqueue
# ────────────────────────────────────────────────────────────────
def test_enqueue_writes_atomic_file(outbox, tmp_path):
    r = outbox.enqueue("inbox_test", {"subject": "PING", "correlation_id": "c-1"})
    assert r["queued"] is True
    path = Path(r["outbox_file"])
    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["queue"] == "inbox_test"
    assert payload["message_body"]["subject"] == "PING"
    assert payload["attempts"] == 0
    assert payload["version"] == 1
    assert payload["created_at"]
    # no stray tmp files
    assert list(tmp_path.rglob("*.tmp")) == []


def test_enqueue_same_message_overwrites(outbox):
    r1 = outbox.enqueue("inbox_test", {"subject": "PING", "correlation_id": "c-1"})
    r2 = outbox.enqueue("inbox_test", {"subject": "PING", "correlation_id": "c-1"})
    assert Path(r1["outbox_file"]).name == Path(r2["outbox_file"]).name
    assert len(list(outbox.RETRY_DIR.glob("*.json"))) == 1


def test_enqueue_different_correlation_distinct(outbox):
    r1 = outbox.enqueue("inbox_test", {"subject": "PING", "correlation_id": "c-1"})
    r2 = outbox.enqueue("inbox_test", {"subject": "PING", "correlation_id": "c-2"})
    assert Path(r1["outbox_file"]).name != Path(r2["outbox_file"]).name
    assert len(list(outbox.RETRY_DIR.glob("*.json"))) == 2


# ────────────────────────────────────────────────────────────────
# backoff
# ────────────────────────────────────────────────────────────────
def test_backoff_grows_exponentially(outbox):
    b0 = outbox._backoff_minutes(0)
    b1 = outbox._backoff_minutes(1)
    b2 = outbox._backoff_minutes(2)
    assert b0 < b1 < b2
    # base values with jitter: 1, 2, 4 minutes
    assert 0.8 <= b0 <= 1.2
    assert 1.6 <= b1 <= 2.4
    assert 3.2 <= b2 <= 4.8


def test_backoff_caps(outbox):
    assert outbox._backoff_minutes(15) <= outbox.BACKOFF_CAP_MINUTES * 1.2


def test_sweep_skips_young_file(outbox, monkeypatch):
    outbox.enqueue("inbox_test", {"subject": "PING"})
    # file is 0 minutes old; backoff for attempts=0 is ~1 min -> skip
    sent = []
    monkeypatch.setattr(outbox, "bus_send", lambda q, b: sent.append(q) or {"ok": True})
    monkeypatch.setattr(outbox, "bus_peek", lambda q, limit=50: [])
    r = outbox.sweep(now=time.time())
    assert r["backoff"] == 1
    assert r["sent"] == 0
    assert sent == []


def test_sweep_old_enough_resends_and_deletes(outbox, monkeypatch, tmp_path):
    r = outbox.enqueue("inbox_test", {"subject": "PING", "correlation_id": "c-9"})
    path = Path(r["outbox_file"])
    # age the file past the 1-min backoff
    old = time.time() - 120
    os.utime(path, (old, old))
    sent = []
    monkeypatch.setattr(outbox, "bus_send", lambda q, b: sent.append(q) or {"ok": True})
    monkeypatch.setattr(outbox, "bus_peek", lambda q, limit=50: [])
    res = outbox.sweep(now=time.time())
    assert res["sent"] == 1
    assert sent == ["inbox_test"]
    assert not path.exists()


# ────────────────────────────────────────────────────────────────
# dedup on resend
# ────────────────────────────────────────────────────────────────
def test_sweep_dedupes_against_pending(outbox, monkeypatch):
    outbox.enqueue("inbox_test", {"subject": "PING", "correlation_id": "c-7"})
    # an identical message is already pending in the queue
    pending = [{"body": {"subject": "PING", "correlation_id": "c-7"}}]
    sent = []
    monkeypatch.setattr(outbox, "bus_send", lambda q, b: sent.append(q) or {"ok": True})
    monkeypatch.setattr(outbox, "bus_peek", lambda q, limit=50: pending)
    r = outbox.sweep(now=time.time() + 120)  # past backoff
    assert r["deduped"] == 1
    assert r["sent"] == 0
    assert sent == []
    assert len(list(outbox.RETRY_DIR.glob("*.json"))) == 0


def test_dedup_requires_same_correlation(outbox):
    # the sweep's dedup uses the canonical bus_find_duplicate (shared with hc.py)
    from cortex_bus import bus_find_duplicate
    pending = [{"body": {"subject": "PING", "correlation_id": "c-1"}}]
    assert bus_find_duplicate(pending, "PING", "x", "c-1") is not None
    assert bus_find_duplicate(pending, "PING", "x", "c-2") is None


# ────────────────────────────────────────────────────────────────
# quarantine (poison pill)
# ────────────────────────────────────────────────────────────────
def test_sweep_quarantines_corrupt_file(outbox, monkeypatch, tmp_path):
    (tmp_path / "bus-retry").mkdir(parents=True)
    bad = tmp_path / "bus-retry" / "corrupt.json"
    bad.write_text("{not json")
    monkeypatch.setattr(outbox, "bus_send", lambda q, b: {"ok": True})
    monkeypatch.setattr(outbox, "bus_peek", lambda q, limit=50: [])
    r = outbox.sweep(now=time.time() + 120)
    assert r["quarantined"] == 1
    assert (tmp_path / "bus-retry" / "quarantine" / "corrupt.json").exists()
    assert not bad.exists()


def test_sweep_quarantines_max_attempts(outbox, monkeypatch, tmp_path):
    r = outbox.enqueue("inbox_test", {"subject": "PING"})
    path = Path(r["outbox_file"])
    payload = json.loads(path.read_text())
    payload["attempts"] = outbox.MAX_ATTEMPTS - 1
    path.write_text(json.dumps(payload))
    old = time.time() - 99999  # far past any backoff
    os.utime(path, (old, old))
    monkeypatch.setattr(outbox, "bus_send", lambda q, b: None)  # bus down
    monkeypatch.setattr(outbox, "bus_peek", lambda q, limit=50: [])
    res = outbox.sweep(now=time.time())
    assert res["quarantined"] == 1
    assert (tmp_path / "bus-retry" / "quarantine").exists()


# ────────────────────────────────────────────────────────────────
# flock concurrency
# ────────────────────────────────────────────────────────────────
def test_sweep_respects_held_lock(outbox, monkeypatch):
    outbox.RETRY_DIR.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(str(outbox.LOCK_FILE), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        import fcntl
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sent = []
        monkeypatch.setattr(outbox, "bus_send", lambda q, b: sent.append(q) or {"ok": True})
        monkeypatch.setattr(outbox, "bus_peek", lambda q, limit=50: [])
        r = outbox.sweep(now=time.time() + 120)
        assert r["scanned"] == 0
        assert "lock" in " ".join(r["errors"]).lower()
    finally:
        os.close(lock_fd)


# ────────────────────────────────────────────────────────────────
# bus_send integration
# ────────────────────────────────────────────────────────────────
def test_bus_send_failure_queues_to_outbox(cortex_bus, monkeypatch, tmp_path):
    def _dead_post(endpoint, payload, fallback=False):
        raise ConnectionError("bus down")
    monkeypatch.setattr(cortex_bus, "_bus_post", _dead_post)
    r = cortex_bus.bus_send("inbox_test", {"subject": "PING", "correlation_id": "c-3"})
    assert r is not None
    assert r["queued"] is True
    files = list(Path(tmp_path / "bus-retry").glob("*.json"))
    assert len(files) == 1


def test_bus_send_success_no_outbox(cortex_bus, monkeypatch, tmp_path):
    monkeypatch.setattr(cortex_bus, "_bus_post", lambda e, p, fallback=False: {"ok": True})
    r = cortex_bus.bus_send("inbox_test", {"subject": "PING"})
    assert r == {"ok": True}
    assert list(Path(tmp_path / "bus-retry").glob("*.json")) == []


def test_bus_send_no_outbox_env_fails_hard(cortex_bus, monkeypatch, tmp_path):
    monkeypatch.setenv("CORTEX_BUS_NO_OUTBOX", "1")
    monkeypatch.setattr(cortex_bus, "_bus_post",
                        lambda e, p, fallback=False: (_ for _ in ()).throw(ConnectionError("down")))
    r = cortex_bus.bus_send("inbox_test", {"subject": "PING"})
    assert r is None
    assert list(Path(tmp_path / "bus-retry").glob("*.json")) == []


# ────────────────────────────────────────────────────────────────
# CLI (watchdog pattern)
# ────────────────────────────────────────────────────────────────
def test_cli_silent_when_clean(outbox, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(outbox, "bus_send", lambda q, b: {"ok": True})
    monkeypatch.setattr(outbox, "bus_peek", lambda q, limit=50: [])
    rc = outbox.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip() == ""  # silent when nothing to report


def test_cli_reports_quarantine(outbox, monkeypatch, capsys, tmp_path):
    (tmp_path / "bus-retry").mkdir(parents=True)
    bad = tmp_path / "bus-retry" / "corrupt.json"
    bad.write_text("{nope")
    monkeypatch.setattr(outbox, "bus_send", lambda q, b: {"ok": True})
    monkeypatch.setattr(outbox, "bus_peek", lambda q, limit=50: [])
    rc = outbox.main()
    captured = capsys.readouterr()
    assert rc == 1
    assert "QUARANTINED" in captured.out


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
