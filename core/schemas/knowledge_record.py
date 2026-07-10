"""
KnowledgeRecord — Canonical metadata envelope for all knowledge artifacts.

Every memory, lesson, brain entry, and cached knowledge item carries this
envelope.  The schema is runtime-independent — no Hermes Agent imports.

See: docs/research/enterprise-grade-hermes-cortex.md § "Formalize data governance"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

__all__ = [
    "Classification",
    "Confidence",
    "AccessPolicy",
    "KnowledgeMetadata",
    "KnowledgeRecord",
    "validate_metadata",
    "backfill_minimal",
]


# ── Enums ──────────────────────────────────────────────────────────────────


class Classification(str, Enum):
    """Data classification levels."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    CUSTOMER_DATA = "customer_data"
    PII = "pii"


class Confidence(str, Enum):
    """Confidence in the knowledge artifact's accuracy."""

    VERIFIED = "verified"          # Confirmed by human or authoritative source
    HIGH = "high"                  # Strong evidence, cross-validated
    MEDIUM = "medium"              # Reasonable, single source
    LOW = "low"                    # Speculative, heuristic, unconfirmed
    UNKNOWN = "unknown"            # Not yet evaluated
    STALE = "stale"                # Once verified, now possibly outdated


class AccessPolicy(str, Enum):
    """Who can read / query this knowledge item."""

    PUBLIC_READ = "public_read"            # Anyone
    INTERNAL_READ = "internal_read"        # Same-tenant agents
    OWNER_ONLY = "owner_only"              # Only the creating agent/user
    RESTRICTED = "restricted"              # Explicit ACL required


# ── Metadata envelope ──────────────────────────────────────────────────────


@dataclass
class KnowledgeMetadata:
    """Enterprise metadata envelope attached to every knowledge artifact.

    All fields are optional at creation time — the system backfills defaults
    via :func:`backfill_minimal`.  Once set, a governance policy can require
    certain fields (e.g. classification != UNKNOWN) before a record is
    considered "published".
    """

    # Identity & ownership
    owner: str = ""                        # Agent or user that owns this item
    source: str = ""                       # Origin system: "agent:lesson", "agent:memory", "gbrain", "web_cache", "manual"
    tenant: str = ""                       # Multi-tenant namespace: "" for personal, "org-<name>" for enterprise

    # Governance & compliance
    classification: Classification = Classification.INTERNAL
    retention_days: int = 0               # 0 = no expiry, >0 = auto-delete after N days
    expires_at: Optional[str] = None       # ISO-8601 timestamp; computed from retention_days if set

    # Quality & provenance
    confidence: Confidence = Confidence.UNKNOWN
    provenance: str = ""                   # How this was created: "llm:gpt-4", "human:luke", "crawl:web", "import:legacy"
    confidence_reason: str = ""            # Why this confidence level was assigned

    # Access control
    access_policy: AccessPolicy = AccessPolicy.INTERNAL_READ
    allowed_agents: list[str] = field(default_factory=list)  # Explicit allowlist when access_policy == RESTRICTED

    # Lifecycle
    created_at: str = ""                   # ISO-8601
    updated_at: str = ""                   # ISO-8601
    deleted_at: Optional[str] = None       # Soft-delete timestamp
    deletion_status: str = "active"        # "active" | "pending_deletion" | "deleted"

    # Audit trail
    audit_trail: list[dict] = field(default_factory=list)  # {"action": "create|update|delete", "by": "agent-name", "at": "ISO-8601"}


# ── Record container ───────────────────────────────────────────────────────


@dataclass
class KnowledgeRecord:
    """A knowledge artifact with enterprise metadata.

    ``id`` is a stable content-addressed identifier (SHA-256 of ``content``).
    ``kind`` differentiates knowledge types for routing and UI display.
    ``content`` is the raw artifact body (markdown, JSON, code snippet…).
    ``tags`` are free-form labels for search and filtering.
    ``metadata`` is the :class:`KnowledgeMetadata` envelope.
    """

    id: str = ""
    kind: str = "note"                     # "lesson", "memory", "brain_entry", "code_snippet", "note", "reference"
    title: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: KnowledgeMetadata = field(default_factory=KnowledgeMetadata)


# ── Validation ─────────────────────────────────────────────────────────────


def validate_metadata(meta: KnowledgeMetadata) -> list[str]:
    """Validate a metadata envelope.  Returns a list of warning strings (empty = valid)."""
    warnings: list[str] = []

    if not meta.owner:
        warnings.append("owner is required")
    if not meta.source:
        warnings.append("source is required")
    if not meta.created_at:
        warnings.append("created_at is required")

    # Validate ISO-8601 timestamps
    for field_name, value in [("created_at", meta.created_at),
                              ("updated_at", meta.updated_at)]:
        if value and not _is_iso8601(value):
            warnings.append(f"{field_name} is not valid ISO-8601: {value!r}")

    if meta.expires_at and not _is_iso8601(meta.expires_at):
        warnings.append(f"expires_at is not valid ISO-8601: {meta.expires_at!r}")

    if meta.retention_days < 0:
        warnings.append("retention_days cannot be negative")

    if meta.access_policy == AccessPolicy.RESTRICTED and not meta.allowed_agents:
        warnings.append("access_policy=RESTRICTED but allowed_agents is empty")

    if meta.deletion_status not in ("active", "pending_deletion", "deleted"):
        warnings.append(f"invalid deletion_status: {meta.deletion_status!r}")

    return warnings


# ── Helpers ─────────────────────────────────────────────────────────────────


def _is_iso8601(s: str) -> bool:
    """Rough check for ISO-8601: '2026-07-10T12:00:00' or '2026-07-10T12:00:00+09:00'."""
    return bool(re.match(
        r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?$",
        s,
    ))


def _content_hash(content: str) -> str:
    """Stable content-addressed identifier (SHA-256)."""
    import hashlib
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:24]


def backfill_minimal(
    content: str,
    *,
    kind: str = "note",
    title: str = "",
    tags: list[str] | None = None,
    owner: str = "system",
    source: str = "import:legacy",
) -> KnowledgeRecord:
    """Create a :class:`KnowledgeRecord` with auto-filled metadata.

    Intended for migrating existing content (lessons, memory entries) that
    don't have enterprise metadata yet.  Defaults are conservative — the
    enforcer can later require explicit classification.
    """
    now = datetime.now(timezone.utc).isoformat()
    meta = KnowledgeMetadata(
        owner=owner,
        source=source,
        classification=Classification.INTERNAL,
        confidence=Confidence.UNKNOWN,
        access_policy=AccessPolicy.INTERNAL_READ,
        created_at=now,
        updated_at=now,
        deletion_status="active",
    )
    return KnowledgeRecord(
        id=_content_hash(content),
        kind=kind,
        title=title,
        content=content,
        tags=tags or [],
        metadata=meta,
    )


# ── Convenience ─────────────────────────────────────────────────────────────


def now_iso() -> str:
    """Current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def compute_expiry(retention_days: int) -> Optional[str]:
    """Compute ISO-8601 expiry timestamp from retention days."""
    if retention_days <= 0:
        return None
    return (datetime.now(timezone.utc) + timedelta(days=retention_days)).isoformat()
