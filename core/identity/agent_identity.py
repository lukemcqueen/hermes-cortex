"""
Agent Identity — Cryptographic workload identity, signed messages, credential model.

Provides the data structures and verification logic for agent identity in a
multi-agent fleet.  Every agent has a persistent identity rooted in an Ed25519
key pair, issues short-lived credentials, and signs A2A messages for
non-repudiation.

Currently agents are identified by their role descriptions in config and git
author fields.  This module provides the schema and verification primitives to
move to verifiable workload identity.

See: docs/research/enterprise-grade-hermes-cortex.md § "Agent identity"
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional


# ── Role definitions ────────────────────────────────────────────────────────


class AgentRole(str, Enum):
    """Canonical agent roles in the Cortex fleet."""

    ORCHESTRATOR = "orchestrator"           # Fleet-wide coordination (Moses)
    BACKUP_ORCHESTRATOR = "backup_orchestrator"  # Cover orchestrator (Esther)
    DEVOPS = "devops"                       # Service health, recovery (Titus)
    SECURITY = "security"                   # Threat detection (Kustos)
    COMMUNICATIONS = "communications"       # Message routing (Gisu)
    OPERATOR = "operator"                   # Human operator session
    GUEST = "guest"                         # Unauthenticated / limited


# ── Permission model ────────────────────────────────────────────────────────


class Permission(str, Enum):
    """Granular permissions that can be granted to agents."""

    # Tool-level
    TOOL_WRITE_FILE = "tool:write_file"
    TOOL_PATCH = "tool:patch"
    TOOL_TERMINAL_WRITE = "tool:terminal:write"
    TOOL_TERMINAL_READ = "tool:terminal:read"
    TOOL_CRONJOB_MANAGE = "tool:cronjob:manage"
    TOOL_CRONJOB_READ = "tool:cronjob:read"
    TOOL_SKILL_MANAGE = "tool:skill:manage"
    TOOL_SKILL_READ = "tool:skill:read"
    TOOL_DELEGATE = "tool:delegate"

    # System-level
    SYSTEM_GOVERNANCE = "system:governance"     # begin/end governance sessions
    SYSTEM_CONFIG = "system:config"             # Modify system configuration
    SYSTEM_CREDENTIALS = "system:credentials"   # Issue/revoke credentials
    SYSTEM_AUDIT = "system:audit"               # Read audit logs

    # Workflow-level
    WORKFLOW_START = "workflow:start"
    WORKFLOW_APPROVE = "workflow:approve"
    WORKFLOW_CANCEL = "workflow:cancel"
    WORKFLOW_ROLLBACK = "workflow:rollback"


# ── Agent Identity (long-lived) ─────────────────────────────────────────────


@dataclass
class AgentIdentity:
    """Persistent identity of an agent in the fleet.

    Each agent has exactly one identity rooted in a Ed25519 key pair.
    The public key is registered in the ``IdentityRegistry``; the private
    key is held by the agent and never transmitted.
    """

    agent_id: str = ""                 # Unique: "moses", "titus", "esther"
    role: AgentRole = AgentRole.GUEST
    display_name: str = ""             # Human-readable: "Moses"
    public_key: str = ""               # Ed25519 public key (hex-encoded, 32 bytes → 64 hex chars)
    permissions: list[Permission] = field(default_factory=list)

    # Metadata
    version: str = "1"
    issued_at: str = ""                # ISO-8601
    expires_at: Optional[str] = None   # ISO-8601; None = no expiry
    revoked: bool = False
    tags: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not self.issued_at:
            self.issued_at = _now()

    def is_expired(self) -> bool:
        """Check if this identity has passed its expiry."""
        if not self.expires_at:
            return False
        try:
            expiry = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > expiry
        except (ValueError, TypeError):
            return True

    def has_permission(self, perm: Permission) -> bool:
        """Check if this identity has a specific permission."""
        return perm in self.permissions


# ── Agent Credential (short-lived) ──────────────────────────────────────────


@dataclass
class AgentCredential:
    """A time-bound credential issued to an agent for a session.

    Created by signing the agent's identity + timestamp with the issuing
    authority's key.  Short-lived (default 1 hour) to limit blast radius.
    """

    credential_id: str = ""            # Unique credential identifier
    agent_id: str = ""                 # Which agent this is for
    role: AgentRole = AgentRole.GUEST
    permissions: list[Permission] = field(default_factory=list)

    # Validity window
    issued_at: str = ""
    expires_at: str = ""               # ISO-8601; required for credentials

    # Signature from the issuing authority
    issuer_id: str = ""                # Which authority issued this (e.g. "root-ca")
    signature: str = ""                # hex-encoded Ed25519 signature

    def __post_init__(self):
        if not self.issued_at:
            self.issued_at = _now()
        if not self.credential_id:
            raw = f"{self.agent_id}:{self.issued_at}:{self.expires_at}"
            self.credential_id = hashlib.sha256(raw.encode()).hexdigest()[:16]

    def is_valid(self) -> bool:
        """Check if this credential is within its validity window."""
        now = datetime.now(timezone.utc)
        try:
            issued = datetime.fromisoformat(self.issued_at)
            expiry = datetime.fromisoformat(self.expires_at)
            return issued <= now <= expiry
        except (ValueError, TypeError):
            return False


# ── Signed Message (non-repudiation) ────────────────────────────────────────


@dataclass
class SignedMessage:
    """An A2A message envelope with cryptographic signature.

    The ``payload`` is the message content (JSON-serializable dict).
    The ``signature`` covers the payload + timestamp + sender, preventing
    replay and tampering.
    """

    message_id: str = ""
    sender_id: str = ""                # Agent ID of the sender
    recipient_id: str = ""             # Agent ID of the intended recipient, or "*" for broadcast
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    signature: str = ""                # hex-encoded Ed25519 signature

    # Routing
    topic: str = "general"
    priority: str = "normal"           # "normal", "urgent", "critical"

    def __post_init__(self):
        if not self.message_id:
            raw = f"{self.sender_id}:{self.recipient_id}:{self.timestamp}"
            self.message_id = hashlib.sha256(raw.encode()).hexdigest()[:16]
        if not self.timestamp:
            self.timestamp = _now()

    def to_signing_payload(self) -> str:
        """Return the canonical string that should be signed/verified."""
        canonical = {
            "message_id": self.message_id,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }
        return json.dumps(canonical, sort_keys=True, separators=(",", ":"))


# ── Identity Registry ───────────────────────────────────────────────────────


@dataclass
class IdentityRecord:
    """A registered identity in the registry."""

    identity: AgentIdentity = field(default_factory=AgentIdentity)
    registered_at: str = ""
    last_seen_at: Optional[str] = None
    revoked_at: Optional[str] = None
    revocation_reason: str = ""


class IdentityRegistry:
    """Central registry of agent identities with verification capabilities.

    In-memory by default.  Can be backed by a database for persistence.

    The registry stores:
    - Active identities (key → AgentIdentity mapping)
    - Revoked identities (for audit)
    - Credentials (active and expired)
    """

    def __init__(self):
        self._identities: dict[str, AgentIdentity] = {}       # agent_id → identity
        self._by_public_key: dict[str, str] = {}              # public_key → agent_id
        self._revoked: dict[str, IdentityRecord] = {}         # agent_id → revocation record
        self._credentials: dict[str, AgentCredential] = {}    # credential_id → credential

    # ── Identity management ────────────────────────────────────────────────

    def register(self, identity: AgentIdentity) -> None:
        """Register a new agent identity."""
        if identity.agent_id in self._identities:
            raise ValueError(f"Agent '{identity.agent_id}' already registered")
        if identity.public_key in self._by_public_key:
            raise ValueError(f"Public key already registered for agent '{self._by_public_key[identity.public_key]}'")
        self._identities[identity.agent_id] = identity
        self._by_public_key[identity.public_key] = identity.agent_id

    def get(self, agent_id: str) -> Optional[AgentIdentity]:
        """Get an identity by agent ID.  Returns None if revoked or expired."""
        identity = self._identities.get(agent_id)
        if not identity:
            return None
        if identity.revoked or identity.is_expired():
            return None
        return identity

    def get_by_public_key(self, public_key: str) -> Optional[AgentIdentity]:
        """Look up an identity by its public key."""
        agent_id = self._by_public_key.get(public_key)
        if not agent_id:
            return None
        return self.get(agent_id)

    def revoke(self, agent_id: str, reason: str = "") -> None:
        """Revoke an agent's identity.  Future verifications will fail."""
        identity = self._identities.get(agent_id)
        if not identity:
            raise ValueError(f"Agent '{agent_id}' not found")
        identity.revoked = True
        self._revoked[agent_id] = IdentityRecord(
            identity=identity,
            revoked_at=_now(),
            revocation_reason=reason,
        )

    def list_active(self) -> list[AgentIdentity]:
        """List all non-revoked, non-expired identities."""
        return [
            identity for identity in self._identities.values()
            if not identity.revoked and not identity.is_expired()
        ]

    # ── Credential management ──────────────────────────────────────────────

    def issue_credential(self, credential: AgentCredential) -> None:
        """Register a credential for verification lookups."""
        self._credentials[credential.credential_id] = credential

    def verify_credential(self, credential_id: str) -> Optional[AgentCredential]:
        """Look up and verify a credential.  Returns None if invalid/expired."""
        credential = self._credentials.get(credential_id)
        if not credential:
            return None
        if not credential.is_valid():
            return None
        # Check if the agent's identity is still valid
        identity = self.get(credential.agent_id)
        if not identity or identity.revoked:
            return None
        return credential

    def revoke_credential(self, credential_id: str) -> bool:
        """Revoke a credential by removing it from the active store."""
        return self._credentials.pop(credential_id, None) is not None

    # ── Verification ───────────────────────────────────────────────────────

    def verify_signature(self, signed: SignedMessage, public_key: str) -> bool:
        """Verify a signed message against a public key.

        In production this calls the Ed25519 verification primitive.
        For now we store the signature and can validate format.
        """
        if not public_key or not signed.signature:
            return False
        # Validate hex format (minimal check — real verification needs crypto lib)
        if not re.match(r"^[0-9a-f]{128}$", signed.signature):
            return False
        if not re.match(r"^[0-9a-f]{64}$", public_key):
            return False
        # Check sender exists and is not revoked
        identity = self.get(signed.sender_id)
        if not identity or identity.revoked:
            return False
        return True

    def verify_message_authenticity(self, signed: SignedMessage) -> bool:
        """Full-chain verification: sender identity, public key match, signature format."""
        identity = self.get(signed.sender_id)
        if not identity:
            return False
        return self.verify_signature(signed, identity.public_key)


# ── Permission presets ──────────────────────────────────────────────────────


DEV_OPS_PERMISSIONS: list[Permission] = [
    Permission.TOOL_WRITE_FILE, Permission.TOOL_PATCH,
    Permission.TOOL_TERMINAL_WRITE, Permission.TOOL_TERMINAL_READ,
    Permission.TOOL_CRONJOB_MANAGE, Permission.TOOL_CRONJOB_READ,
    Permission.TOOL_SKILL_READ,
    Permission.SYSTEM_GOVERNANCE,
    Permission.WORKFLOW_START, Permission.WORKFLOW_APPROVE,
]

ORCHESTRATOR_PERMISSIONS: list[Permission] = [
    *DEV_OPS_PERMISSIONS,
    Permission.TOOL_SKILL_MANAGE, Permission.TOOL_DELEGATE,
    Permission.SYSTEM_CONFIG, Permission.SYSTEM_CREDENTIALS,
    Permission.SYSTEM_AUDIT,
    Permission.WORKFLOW_CANCEL, Permission.WORKFLOW_ROLLBACK,
]

GUEST_PERMISSIONS: list[Permission] = [
    Permission.TOOL_TERMINAL_READ,
    Permission.TOOL_CRONJOB_READ,
    Permission.TOOL_SKILL_READ,
]


# ── Helper factories ────────────────────────────────────────────────────────


def create_credential(
    identity: AgentIdentity,
    issuer_id: str = "root-ca",
    ttl_minutes: int = 60,
) -> AgentCredential:
    """Issue a short-lived credential for an agent identity."""
    now = datetime.now(timezone.utc)
    return AgentCredential(
        agent_id=identity.agent_id,
        role=identity.role,
        permissions=list(identity.permissions),
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=ttl_minutes)).isoformat(),
        issuer_id=issuer_id,
    )


def create_signed_message(
    sender_id: str,
    recipient_id: str,
    payload: dict[str, Any],
    signature: str = "",
    topic: str = "general",
    priority: str = "normal",
) -> SignedMessage:
    """Create a SignedMessage with auto-generated fields."""
    return SignedMessage(
        sender_id=sender_id,
        recipient_id=recipient_id,
        payload=payload,
        signature=signature,
        topic=topic,
        priority=priority,
    )


# ── Internal helpers ────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
