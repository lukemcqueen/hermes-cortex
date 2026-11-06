#!/usr/bin/env python3
"""Hermetic tests for ops/scripts/bus/fleet-bus-processor.py.

The processor is a 10-minute no_agent watchdog that peeks at the Agent Bus
(non-consuming bus_list_queues/bus_read, then archives) and prints one JSON
line. The close review (ADV-14307) required a committed test: its behavior —
output JSON shape, seen-file dedup, broadcast classification, and the
audible-fallback on unreadable registry/malformed body — is pinned here with
a stubbed lib.fleet_bus instead of a live bus.

The module imports `lib.fleet_bus` from the DEPLOYED scripts dir at import
time; the stub is spliced into sys.modules first so nothing touches the real
bus or a real HOME.
"""
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PROCESSOR = REPO / "ops" / "scripts" / "bus" / "fleet-bus-processor.py"


class _StubBus:
    def __init__(self):
        self.queues = []
        self.reads = []
        self.archived = []
        self.list_calls = 0

    def bus_list_queues(self):
        self.list_calls += 1
        return self.queues

    def bus_read(self, queue, vt=30):
        if self.reads:
            return self.reads.pop(0)
        return None

    def bus_archive(self, queue, msg_id):
        self.archived.append(msg_id)


@pytest.fixture
def env(monkeypatch, tmp_path):
    """A controlled HOME + AGENT_NAME + stubbed bus, with the module imported."""
    monkeypatch.setenv("AGENT_NAME", "tester")
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".hermes" / "state").mkdir(parents=True)
    stub = _StubBus()
    mod = types.ModuleType("lib.fleet_bus")
    mod.bus_list_queues = stub.bus_list_queues
    mod.bus_read = stub.bus_read
    mod.bus_archive = stub.bus_archive
    monkeypatch.setitem(sys.modules, "lib.fleet_bus", mod)
    spec = importlib.util.spec_from_file_location("fleet_bus_processor_ut", PROCESSOR)
    proc = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "fleet_bus_processor_ut", proc)
    spec.loader.exec_module(proc)
    return proc, stub, tmp_path


def test_output_json_shape_when_queue_absent(env, capsys):
    proc, stub, _ = env
    stub.queues = [{"name": "inbox_moses", "depth": 0}]
    assert proc.main() == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["has_work"] is False
    assert out["unread_count"] == 0 and out["urgent_count"] == 0
    assert out["new_broadcasts"] == 0
    assert "last_check" in out


def test_broadcast_classification_and_archive(env, capsys):
    proc, stub, _ = env
    stub.queues = [{"name": "inbox_tester", "depth": 2}]
    stub.reads = [
        {"msg_id": "m1", "correlation_id": "c1",
         "body": json.dumps({"topic": "all", "priority": "urgent"})},
        {"msg_id": "m2", "correlation_id": "c2",
         "body": {"topic": "general", "priority": "normal"}},
    ]
    assert proc.main() == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["has_work"] is True
    assert out["unread_count"] == 2
    assert out["urgent_count"] == 1
    assert out["new_broadcasts"] == 2
    assert sorted(stub.archived) == ["m1", "m2"]


def test_seen_file_dedups_next_run(env, capsys):
    proc, stub, tmp_path = env
    stub.queues = [{"name": "inbox_tester", "depth": 1}]
    stub.reads = [{"msg_id": "m1", "correlation_id": "c1",
                   "body": {"topic": "all", "priority": "normal"}}]
    proc.main()
    capsys.readouterr()
    assert (tmp_path / ".hermes" / "state" / "bus-broadcast-seen").exists()
    # second run: same message -> 0 new
    stub.queues = [{"name": "inbox_tester", "depth": 1}]
    stub.reads = [{"msg_id": "m1", "correlation_id": "c1",
                   "body": {"topic": "all", "priority": "normal"}}]
    proc.main()
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["new_broadcasts"] == 0
    assert out["unread_count"] == 1


def test_malformed_body_is_audible_not_swallowed(env, capsys):
    proc, stub, _ = env
    stub.queues = [{"name": "inbox_tester", "depth": 1}]
    stub.reads = [{"msg_id": "m1", "correlation_id": "c1", "body": "not-json{{"}]
    assert proc.main() == 0
    captured = capsys.readouterr()
    out = json.loads(captured.out.strip().splitlines()[-1])
    # an unparsed body is classified general/normal and still counts as a
    # NEW message (its correlation id was unseen) — the point is audibility
    assert out["has_work"] is True
    assert out["new_broadcasts"] == 1
    assert "unparsed message body" in captured.err


def test_default_topics_on_corrupt_registry(env, capsys, tmp_path):
    proc, stub, _ = env
    reg = tmp_path / ".hermes" / "state" / "agent-registry.json"
    reg.write_text("{corrupt!!")
    stub.queues = [{"name": "inbox_tester", "depth": 0}]
    assert proc.main() == 0
    captured = capsys.readouterr()
    assert "broadcast registry unreadable" in captured.err
    assert proc.get_broadcast_topics() == ["luke", "all", "general", "moses"]
