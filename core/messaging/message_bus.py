"""
MessageBus — Transport-agnostic message bus abstraction for A2A and event-driven
communication between agents.  Supports multiple backends via adapter pattern.

Backends:
  - **GitInboxAdapter** wraps the existing Git-backed agent inbox
  - **InMemoryBusAdapter** for testing and single-process use
  - Future: NATS, Redis Streams, Kafka, Local SQLite queue

See: docs/research/enterprise-grade-hermes-cortex.md § "Reliable event bus"
"""

from __future__ import annotations

import abc
import hashlib
import json
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional


# ── Delivery semantics ──────────────────────────────────────────────────────


class DeliverySemantics(str, Enum):
    AT_LEAST_ONCE = "at_least_once"     # Retry until acknowledged
    AT_MOST_ONCE = "at_most_once"       # Fire and forget
    EXACTLY_ONCE = "exactly_once"       # Deduplication via message ID


# ── Message envelope ────────────────────────────────────────────────────────


@dataclass
class BusMessage:
    """Canonical message envelope for the bus."""

    # Identity
    message_id: str = ""                 # Unique, ideally content-addressed
    correlation_id: str = ""             # Links related messages
    causation_id: str = ""               # Links to the message that caused this one

    # Routing
    source: str = ""                     # Agent/service that produced this
    destination: str = ""                # "*" for broadcast, specific agent name
    topic: str = "general"              # Logical channel
    priority: int = 0                    # 0=normal, higher=more urgent

    # Payload
    type: str = "event"                  # "event", "command", "request", "response"
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1"

    # Delivery metadata
    timestamp: str = ""
    ttl_seconds: int = 86400             # Time-to-live (default 24h)
    delivery_count: int = 0              # How many times delivery was attempted
    max_deliveries: int = 3

    def __post_init__(self):
        if not self.message_id:
            raw = f"{self.source}:{self.topic}:{self.timestamp or time.time()}:{uuid.uuid4().hex}"
            self.message_id = hashlib.sha256(raw.encode()).hexdigest()[:24]
        if not self.timestamp:
            self.timestamp = _now()

    def is_expired(self) -> bool:
        """Check if this message has exceeded its TTL."""
        if not self.timestamp:
            return True
        try:
            created = datetime.fromisoformat(self.timestamp)
            age = (datetime.now(timezone.utc) - created).total_seconds()
            return age > self.ttl_seconds
        except (ValueError, TypeError):
            return True


# ── Bus adapter interface ───────────────────────────────────────────────────


class BusError(Exception):
    """Base exception for bus operations."""


class MessageNotAcknowledged(BusError):
    """Raised when a message lease expires without acknowledgement."""


class DeadLetterError(BusError):
    """Raised when a message exceeds max delivery attempts."""


class BusAdapter(abc.ABC):
    """Abstract interface for message bus backends.

    All implementations must handle:
    - Sending messages (with optional TTL and priority)
    - Receiving/consuming messages (polling or subscription)
    - Acknowledging messages (marking as processed)
    - Leasing (preventing duplicate processing across consumers)
    - Dead-letter handling (messages that fail repeatedly or expire)
    """

    @abc.abstractmethod
    def send(self, message: BusMessage) -> str:
        """Publish a message.  Returns the message ID."""
        ...

    @abc.abstractmethod
    def poll(self, topic: str, consumer_id: str, limit: int = 10) -> list[BusMessage]:
        """Poll for new messages on a topic.  Returns up to ``limit`` messages."""
        ...

    @abc.abstractmethod
    def acknowledge(self, message_id: str, consumer_id: str) -> bool:
        """Mark a message as processed.  Returns True if successful."""
        ...

    @abc.abstractmethod
    def lease(self, message_id: str, consumer_id: str, ttl_seconds: int = 30) -> bool:
        """Acquire a lease on a message to prevent duplicate processing.
        Returns True if the lease was acquired."""
        ...

    @abc.abstractmethod
    def release_lease(self, message_id: str, consumer_id: str) -> bool:
        """Release a lease (e.g. after processing or on failure)."""
        ...

    @abc.abstractmethod
    def dead_letter(self, message: BusMessage, reason: str) -> None:
        """Move a message to the dead-letter queue after repeated failures."""
        ...

    @abc.abstractmethod
    def pending_count(self, topic: str) -> int:
        """Count of unacknowledged messages on a topic."""
        ...


# ── InMemoryBusAdapter (for testing and single-process) ─────────────────────


@dataclass
class LeaseRecord:
    consumer_id: str
    acquired_at: str
    ttl_seconds: int

    def is_expired(self) -> bool:
        try:
            acquired = datetime.fromisoformat(self.acquired_at)
            age = (datetime.now(timezone.utc) - acquired).total_seconds()
            return age > self.ttl_seconds
        except (ValueError, TypeError):
            return True


class InMemoryBusAdapter(BusAdapter):
    """Thread-unsafe in-memory bus for testing and single-process use.

    Messages are stored in dicts keyed by topic.  Leases are stored in-memory.
    """

    def __init__(self):
        self._queues: dict[str, list[BusMessage]] = {}         # topic → messages
        self._dead_letter: dict[str, list[tuple[BusMessage, str]]] = {}  # topic → (message, reason)
        self._acks: set[str] = set()                            # message_ids that were acked
        self._leases: dict[str, LeaseRecord] = {}               # message_id → lease

    # ── Topic helpers ──────────────────────────────────────────────────────

    def _queue(self, topic: str) -> list[BusMessage]:
        if topic not in self._queues:
            self._queues[topic] = []
        return self._queues[topic]

    def _dead(self, topic: str) -> list[tuple[BusMessage, str]]:
        if topic not in self._dead_letter:
            self._dead_letter[topic] = []
        return self._dead_letter[topic]

    # ── BusAdapter interface ───────────────────────────────────────────────

    def send(self, message: BusMessage) -> str:
        self._queue(message.topic).append(message)
        return message.message_id

    def poll(self, topic: str, consumer_id: str, limit: int = 10) -> list[BusMessage]:
        queue = self._queue(topic)
        result: list[BusMessage] = []
        # Mark messages in result as "in flight" (don't remove from queue)
        for msg in queue:
            if len(result) >= limit:
                break
            if msg.message_id in self._acks:
                continue
            if msg.is_expired():
                self.dead_letter(msg, "expired")
                continue
            result.append(msg)

        for msg in result:
            msg.delivery_count += 1
            if msg.delivery_count >= msg.max_deliveries:
                self.dead_letter(msg, "max_deliveries_exceeded")

        # Rebuild queue excluding dead-lettered messages
        dead_ids = {m[0].message_id for m in self._dead_letter.get(topic, [])}
        self._queues[topic] = [m for m in queue if m.message_id not in dead_ids]

        return result

    def acknowledge(self, message_id: str, consumer_id: str) -> bool:
        self._acks.add(message_id)
        self._leases.pop(message_id, None)
        return True

    def lease(self, message_id: str, consumer_id: str, ttl_seconds: int = 30) -> bool:
        existing = self._leases.get(message_id)
        if existing and not existing.is_expired() and existing.consumer_id != consumer_id:
            return False  # Another consumer holds the lease
        self._leases[message_id] = LeaseRecord(
            consumer_id=consumer_id,
            acquired_at=_now(),
            ttl_seconds=ttl_seconds,
        )
        return True

    def release_lease(self, message_id: str, consumer_id: str) -> bool:
        existing = self._leases.get(message_id)
        if existing and existing.consumer_id == consumer_id:
            self._leases.pop(message_id, None)
            return True
        return False

    def dead_letter(self, message: BusMessage, reason: str) -> None:
        self._dead(message.topic).append((message, reason))
        # Remove from active queue
        queue = self._queue(message.topic)
        self._queues[message.topic] = [m for m in queue if m.message_id != message.message_id]

    def pending_count(self, topic: str) -> int:
        return len([m for m in self._queue(topic) if m.message_id not in self._acks])


# ── GitInboxAdapter ─────────────────────────────────────────────────────────


class GitInboxAdapter(BusAdapter):
    """Adapts the existing Git-backed agent inbox to the BusAdapter interface.

    Messages are written as Markdown files in a Git repository.
    Each message file is named ``<timestamp>-<source>-<topic>.md``.

    This adapter provides:
    - Offline-first operation (Git works without network)
    - Built-in versioning and history
    - Human-readable message format
    - Simple locking via ``.lock`` files for lease semantics
    """

    def __init__(self, inbox_dir: str | Path):
        self.inbox_dir = Path(inbox_dir)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self._lock_dir = self.inbox_dir / ".locks"
        self._dead_dir = self.inbox_dir / ".dead-letter"
        self._lock_dir.mkdir(exist_ok=True)
        self._dead_dir.mkdir(exist_ok=True)

    def _message_path(self, message: BusMessage) -> Path:
        ts = message.timestamp.replace(":", "-").replace("T", "_")[:19]
        safe_source = message.source.replace(" ", "_")
        short_id = message.message_id[:8]
        return self.inbox_dir / f"{ts}-{short_id}-{safe_source}-{message.topic}.md"

    @staticmethod
    def _message_to_md(message: BusMessage) -> str:
        frontmatter = {
            "message_id": message.message_id,
            "correlation_id": message.correlation_id,
            "causation_id": message.causation_id,
            "source": message.source,
            "destination": message.destination,
            "topic": message.topic,
            "priority": message.priority,
            "type": message.type,
            "timestamp": message.timestamp,
            "ttl_seconds": message.ttl_seconds,
            "delivery_count": message.delivery_count,
            "schema_version": message.schema_version,
        }
        lines = ["---"]
        for k, v in frontmatter.items():
            lines.append(f"{k}: {v}")
        lines.append("---")
        lines.append("")
        lines.append(json.dumps(message.payload, indent=2))
        return "\n".join(lines)

    def send(self, message: BusMessage) -> str:
        path = self._message_path(message)
        path.write_text(self._message_to_md(message))
        return message.message_id

    def poll(self, topic: str, consumer_id: str, limit: int = 10) -> list[BusMessage]:
        result: list[BusMessage] = []
        for f in sorted(self.inbox_dir.iterdir()):
            if not f.name.endswith(".md"):
                continue
            if f.suffix == ".md" and topic in f.name:
                if self._acquire_lock(f, consumer_id):
                    msg = self._parse_message(f)
                    if msg:
                        result.append(msg)
                        if len(result) >= limit:
                            break
        return result

    def acknowledge(self, message_id: str, consumer_id: str) -> bool:
        short = message_id[:8]
        for f in self.inbox_dir.glob("*.md"):
            if short in f.stem:
                f.rename(self.inbox_dir / f".processed-{f.name}")
                return True
        return False

    def lease(self, message_id: str, consumer_id: str, ttl_seconds: int = 30) -> bool:
        short = message_id[:8]
        for f in self.inbox_dir.glob("*.md"):
            if short in f.stem:
                return self._acquire_lock(f, consumer_id)
        return False

    def release_lease(self, message_id: str, consumer_id: str) -> bool:
        short = message_id[:8]
        lock_file = self._lock_dir / f"{short}.lock"
        if lock_file.exists():
            lock_file.unlink()
            return True
        for f in self._lock_dir.iterdir():
            if short in f.stem:
                f.unlink()
                return True
        return False

    def dead_letter(self, message: BusMessage, reason: str) -> None:
        dl_path = self._dead_dir / f"{message.message_id}.dead"
        dl_path.write_text(json.dumps({
            "message_id": message.message_id,
            "reason": reason,
            "moved_at": _now(),
        }, indent=2))

    def pending_count(self, topic: str) -> int:
        count = 0
        for f in self.inbox_dir.iterdir():
            if f.name.endswith(".md") and not f.name.startswith(".processed"):
                count += 1
        return count

    def _acquire_lock(self, file_path: Path, consumer_id: str) -> bool:
        lock_path = self._lock_dir / f"{file_path.stem}.lock"
        if lock_path.exists():
            return False  # Already locked by another consumer
        lock_path.write_text(consumer_id)
        return True

    def _parse_message(self, path: Path) -> Optional[BusMessage]:
        try:
            text = path.read_text()
            parts = text.split("---")
            if len(parts) < 3:
                return None
            frontmatter = {}
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    frontmatter[k.strip()] = v.strip()
            payload_text = parts[2].strip()
            payload = json.loads(payload_text) if payload_text else {}
            return BusMessage(
                message_id=frontmatter.get("message_id", ""),
                source=frontmatter.get("source", ""),
                destination=frontmatter.get("destination", ""),
                topic=frontmatter.get("topic", "general"),
                payload=payload,
                timestamp=frontmatter.get("timestamp", ""),
                ttl_seconds=int(frontmatter.get("ttl_seconds", 86400)),
                type=frontmatter.get("type", "event"),
                schema_version=frontmatter.get("schema_version", "1"),
            )
        except (OSError, json.JSONDecodeError, ValueError):
            return None


# ── Internal ────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
