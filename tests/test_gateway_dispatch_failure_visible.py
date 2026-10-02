#!/usr/bin/env python3
"""A failed dispatch must be VISIBLE (cutover rehearsal finding, 2026-10-02).

During the live rehearsal on the second bot (@Esther0001Bot), /status worked — it is
answered inside the gateway and never touches the bus — while a normal message went
nowhere: the rehearsal config routed to the example's placeholder agent "hermes", and
`inbox_hermes` does not exist. HermesBackend.dispatch swallowed the failed enqueue
(`_ = ok`) and returned None, which the daemon treats exactly like a successful async
dispatch, so the message vanished with no log, no error and an offset that still advanced.

This test pins the visibility fix, and pins the honest bound of it: the WARNING fires, and
dispatch still returns None — the offset behaviour is deliberately NOT changed here,
because that is a seam-contract change that must be made deliberately, not during a
pre-cutover push.

Run: python3 -m pytest tests/test_gateway_dispatch_failure_visible.py -q -s
"""
import logging
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

from cortex_gateway import hermes_backend as hb          # noqa: E402
import gateway_envelope as _env                          # noqa: E402

# A REAL envelope: HermesBackend.dispatch validates before it enqueues, so a hand-made
# dict with a fake msg_id silently takes the malformed-inbound DLQ path and never calls
# the bus at all (found the hard way — the first version of this test asserted on a
# dispatch that never happened).
_ENVELOPE = {"msg_id": _env.new_msg_id(), "ts": 1, "from_agent": "", "to_agent": "esther",
             "channel": "telegram", "channel_user_id": 100001, "thread_id": None,
             "body": "hello", "media": [], "reply_to_msg_id": None, "ack_required": False}


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _backend(agent="esther"):
    return hb.HermesBackend(agent=agent, bus_url="https://bus.example.com",
                            bus_headers={}, secret="s" * 32)


def _with_bus_result(monkeypatch, result):
    def _fake(bus_url, headers, queue, signed):
        _fake.queue = queue
        return result
    monkeypatch.setattr(hb._bus, "bus_send", _fake)
    return _fake


def test_failed_enqueue_warns_and_names_the_queue(monkeypatch):
    """The defect: silence. The fix: a WARNING that names the agent and the queue."""
    fake = _with_bus_result(monkeypatch, None)          # None == the bus refused/failed
    handler = _Capture()
    hb.log.addHandler(handler)
    hb.log.setLevel(logging.DEBUG)
    try:
        out = _backend("hermes").dispatch(dict(_ENVELOPE))
    finally:
        hb.log.removeHandler(handler)
    assert fake.queue == "inbox_hermes"
    assert out is None, "the async contract still returns None"
    warnings = [r for r in handler.records if r.levelno >= logging.WARNING]
    assert warnings, "a failed dispatch MUST log — silence is what lost the message"
    msg = warnings[0].getMessage()
    assert "inbox_hermes" in msg and "NOT delivered" in msg, msg
    print(f"  failed dispatch warns: {msg[:96]}…")


def test_successful_enqueue_is_quiet(monkeypatch):
    """Control: the warning must not fire on the normal path."""
    fake = _with_bus_result(monkeypatch, {"msg_id": "x"})
    handler = _Capture()
    hb.log.addHandler(handler)
    hb.log.setLevel(logging.DEBUG)
    try:
        _backend().dispatch(dict(_ENVELOPE))
    finally:
        hb.log.removeHandler(handler)
    assert fake.queue == "inbox_esther", "the queue must follow the agent name"
    warnings = [r for r in handler.records if r.levelno >= logging.WARNING]
    assert not warnings, f"a successful dispatch must stay quiet, got {warnings}"
    print("  successful dispatch is quiet, queue=inbox_esther ✓")


def test_malformed_inbound_stays_a_silent_dlq(monkeypatch):
    """Control: the pre-existing DLQ path must NOT start warning (it is not a failure)."""
    _with_bus_result(monkeypatch, {"msg_id": "x"})
    handler = _Capture()
    hb.log.addHandler(handler)
    hb.log.setLevel(logging.DEBUG)
    try:
        assert _backend().dispatch(None) is None
        assert _backend().dispatch({"nonsense": True}) is None
    finally:
        hb.log.removeHandler(handler)
    warnings = [r for r in handler.records if r.levelno >= logging.WARNING]
    assert not warnings, f"malformed inbound is a DLQ, not a dispatch failure: {warnings}"
    print("  malformed inbound stays a silent DLQ ✓")


def test_the_offset_still_advances_and_that_is_recorded_as_a_limit():
    """The residual risk, asserted rather than implied: a failed dispatch still acks.

    If someone later makes the daemon NOT advance on a failed dispatch, this test should
    be updated deliberately — the assertion exists so the limit is visible, not so it is
    frozen forever.
    """
    src = (_REPO / "ops" / "scripts" / "cortex_gateway" / "daemon.py").read_text()
    assert "self.offset = max(self.offset, uid + 1)" in src, \
        "the daemon's enqueue-then-ack behaviour is the known limit; update this test if it changes"
    print("  residual limit recorded: a failed dispatch still advances the offset ✓")
