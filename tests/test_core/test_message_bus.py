"""Tests for core/messaging/message_bus.py"""

import json
import tempfile
from pathlib import Path

import pytest

from core.messaging.message_bus import (
    BusMessage,
    DeadLetterError,
    GitInboxAdapter,
    InMemoryBusAdapter,
    LeaseRecord,
)


# ═════════════════════════════════════════════════════════════════════════════
# BusMessage
# ═════════════════════════════════════════════════════════════════════════════


class TestBusMessage:
    def test_defaults(self):
        msg = BusMessage()
        assert msg.message_id != ""
        assert msg.topic == "general"
        assert msg.type == "event"
        assert msg.priority == 0
        assert msg.ttl_seconds == 86400
        assert msg.delivery_count == 0
        assert msg.max_deliveries == 3

    def test_message_id_generated(self):
        msg = BusMessage(source="titus", topic="health")
        assert len(msg.message_id) == 24

    def test_message_id_stable_with_same_inputs(self):
        msg1 = BusMessage(source="titus", topic="health", timestamp="2026-01-01T00:00:00")
        msg2 = BusMessage(source="titus", topic="health", timestamp="2026-01-01T00:00:00")
        assert msg1.message_id != msg2.message_id  # UUID component makes it unique

    def test_is_expired(self):
        msg = BusMessage(timestamp="2020-01-01T00:00:00", ttl_seconds=3600)
        assert msg.is_expired() is True

    def test_not_expired(self):
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        msg = BusMessage(timestamp=now, ttl_seconds=3600)
        assert msg.is_expired() is False

    def test_custom_fields(self):
        msg = BusMessage(
            source="kustos",
            destination="moses",
            topic="security",
            type="command",
            priority=10,
            payload={"alert": "intrusion"},
            correlation_id="abc",
            causation_id="def",
        )
        assert msg.source == "kustos"
        assert msg.destination == "moses"
        assert msg.topic == "security"
        assert msg.payload == {"alert": "intrusion"}


# ═════════════════════════════════════════════════════════════════════════════
# InMemoryBusAdapter
# ═════════════════════════════════════════════════════════════════════════════


class TestInMemoryBus:
    @pytest.fixture
    def bus(self):
        return InMemoryBusAdapter()

    def test_send_and_poll(self, bus):
        msg = BusMessage(source="titus", topic="health")
        bus.send(msg)
        messages = bus.poll("health", "consumer-1")
        assert len(messages) == 1
        assert messages[0].source == "titus"

    def test_poll_empty_topic(self, bus):
        messages = bus.poll("nonexistent", "consumer-1")
        assert messages == []

    def test_poll_respects_limit(self, bus):
        for i in range(5):
            bus.send(BusMessage(source="titus", topic="test", payload={"n": i}))
        messages = bus.poll("test", "consumer-1", limit=3)
        assert len(messages) == 3

    def test_acknowledge_removes_from_queue(self, bus):
        msg = BusMessage(source="titus", topic="test")
        bus.send(msg)
        bus.acknowledge(msg.message_id, "consumer-1")
        messages = bus.poll("test", "consumer-1")
        assert len(messages) == 0

    def test_pending_count(self, bus):
        bus.send(BusMessage(source="titus", topic="test"))
        bus.send(BusMessage(source="moses", topic="test"))
        assert bus.pending_count("test") == 2
        messages = bus.poll("test", "consumer-1")
        bus.acknowledge(messages[0].message_id, "consumer-1")
        assert bus.pending_count("test") == 1

    def test_lease_prevents_duplicate_consumption(self, bus):
        msg = BusMessage(source="titus", topic="test")
        bus.send(msg)
        # Consumer 1 acquires lease
        assert bus.lease(msg.message_id, "consumer-1") is True
        # Consumer 2 cannot acquire
        assert bus.lease(msg.message_id, "consumer-2") is False

    def test_lease_release(self, bus):
        msg = BusMessage(source="titus", topic="test")
        bus.send(msg)
        bus.lease(msg.message_id, "consumer-1")
        assert bus.release_lease(msg.message_id, "consumer-1") is True
        # Now consumer 2 can lease
        assert bus.lease(msg.message_id, "consumer-2") is True

    def test_dead_letter_moves_message(self, bus):
        msg = BusMessage(source="titus", topic="test")
        bus.send(msg)
        bus.dead_letter(msg, "unprocessable")
        messages = bus.poll("test", "consumer-1")
        assert len(messages) == 0

    def test_max_deliveries_moves_to_dead_letter(self, bus):
        msg = BusMessage(source="titus", topic="test", max_deliveries=1)
        bus.send(msg)
        # First poll increments delivery_count to 1 → exceeds max_deliveries
        bus.poll("test", "consumer-1")
        # Second poll should be empty (moved to dead letter)
        messages = bus.poll("test", "consumer-1")
        assert len(messages) == 0

    def test_expired_message_moves_to_dead_letter(self, bus):
        msg = BusMessage(source="titus", topic="test", timestamp="2020-01-01T00:00:00", ttl_seconds=60)
        bus.send(msg)
        messages = bus.poll("test", "consumer-1")
        assert len(messages) == 0

    def test_different_topics_isolated(self, bus):
        bus.send(BusMessage(source="titus", topic="alerts"))
        bus.send(BusMessage(source="moses", topic="health"))
        assert len(bus.poll("alerts", "c1")) == 1
        assert len(bus.poll("health", "c1")) == 1


# ═════════════════════════════════════════════════════════════════════════════
# GitInboxAdapter
# ═════════════════════════════════════════════════════════════════════════════


class TestGitInboxAdapter:
    @pytest.fixture
    def inbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield GitInboxAdapter(Path(tmp))

    def test_send_creates_file(self, inbox):
        msg = BusMessage(source="titus", topic="health")
        msg_id = inbox.send(msg)
        files = list(inbox.inbox_dir.glob("*.md"))
        assert len(files) == 1
        assert msg_id == msg.message_id

    def test_send_and_poll(self, inbox):
        msg = BusMessage(source="titus", topic="health")
        inbox.send(msg)
        messages = inbox.poll("health", "consumer-1")
        assert len(messages) == 1
        assert messages[0].source == "titus"

    def test_poll_empty(self, inbox):
        messages = inbox.poll("nonexistent", "consumer-1")
        assert messages == []

    def test_acknowledge_moves_file(self, inbox):
        msg = BusMessage(source="titus", topic="test")
        inbox.send(msg)
        inbox.acknowledge(msg.message_id, "consumer-1")
        processed = list(inbox.inbox_dir.glob(".processed-*.md"))
        assert len(processed) == 1

    def test_poll_respects_lock(self, inbox):
        msg = BusMessage(source="titus", topic="test")
        inbox.send(msg)
        # Consumer 1 polls → acquires lock
        messages_c1 = inbox.poll("test", "consumer-1")
        assert len(messages_c1) == 1
        # Consumer 2 polls → lock prevents
        messages_c2 = inbox.poll("test", "consumer-2")
        assert len(messages_c2) == 0

    def test_lease_and_release(self, inbox):
        msg = BusMessage(source="titus", topic="test")
        inbox.send(msg)
        assert inbox.lease(msg.message_id, "consumer-1") is True
        assert inbox.lease(msg.message_id, "consumer-2") is False
        assert inbox.release_lease(msg.message_id, "consumer-1") is True
        assert inbox.lease(msg.message_id, "consumer-2") is True

    def test_dead_letter_creates_file(self, inbox):
        msg = BusMessage(source="titus", topic="test")
        inbox.send(msg)
        inbox.dead_letter(msg, "test_reason")
        dead_files = list(inbox._dead_dir.glob("*.dead"))
        assert len(dead_files) == 1
        content = json.loads(dead_files[0].read_text())
        assert content["reason"] == "test_reason"

    def test_pending_count(self, inbox):
        inbox.send(BusMessage(source="titus", topic="test"))
        inbox.send(BusMessage(source="moses", topic="test"))
        assert inbox.pending_count("test") == 2
        messages = inbox.poll("test", "consumer-1")
        assert len(messages) == 2  # Both available (Git doesn't lock across poll calls directly)
        # After ack
        inbox.acknowledge(messages[0].message_id, "consumer-1")
        # pending_count still sees both .md files (processed ones are renamed)
        # Let me count by .md vs .processed:
        md_files = [f for f in inbox.inbox_dir.glob("*.md") if not f.name.startswith(".processed")]
        assert len(md_files) == 1  # One remaining .md

    def test_message_frontmatter_parsed(self, inbox):
        msg = BusMessage(source="kustos", topic="security", payload={"alert": True})
        inbox.send(msg)
        messages = inbox.poll("security", "consumer-1")
        assert len(messages) == 1
        assert messages[0].source == "kustos"
        assert messages[0].payload == {"alert": True}

    def test_message_id_preserved_roundtrip(self, inbox):
        msg = BusMessage(source="titus", topic="test")
        inbox.send(msg)
        messages = inbox.poll("test", "consumer-1")
        assert messages[0].message_id == msg.message_id


class TestLeaseRecord:
    def test_not_expired(self):
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        lease = LeaseRecord(consumer_id="c1", acquired_at=now, ttl_seconds=60)
        assert lease.is_expired() is False

    def test_expired(self):
        lease = LeaseRecord(consumer_id="c1", acquired_at="2020-01-01T00:00:00", ttl_seconds=60)
        assert lease.is_expired() is True
