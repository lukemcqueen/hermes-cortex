"""Tests for core/identity/agent_identity.py"""

import pytest

from core.identity.agent_identity import (
    DEV_OPS_PERMISSIONS,
    GUEST_PERMISSIONS,
    ORCHESTRATOR_PERMISSIONS,
    AgentCredential,
    AgentIdentity,
    AgentRole,
    IdentityRegistry,
    Permission,
    SignedMessage,
    create_credential,
    create_signed_message,
)


class TestAgentIdentity:
    def test_defaults(self):
        identity = AgentIdentity()
        assert identity.agent_id == ""
        assert identity.role == AgentRole.GUEST
        assert identity.permissions == []
        assert identity.revoked is False
        assert identity.issued_at != ""

    def test_role_assignment(self):
        identity = AgentIdentity(agent_id="titus", role=AgentRole.DEVOPS)
        assert identity.agent_id == "titus"
        assert identity.role == AgentRole.DEVOPS

    def test_permission_check(self):
        identity = AgentIdentity(
            agent_id="moses",
            role=AgentRole.ORCHESTRATOR,
            permissions=[Permission.SYSTEM_CONFIG, Permission.SYSTEM_AUDIT],
        )
        assert identity.has_permission(Permission.SYSTEM_CONFIG) is True
        assert identity.has_permission(Permission.TOOL_WRITE_FILE) is False

    def test_expired_identity(self):
        identity = AgentIdentity(
            agent_id="old",
            expires_at="2020-01-01T00:00:00Z",
        )
        assert identity.is_expired() is True

    def test_non_expired_identity(self):
        identity = AgentIdentity(agent_id="current")
        assert identity.is_expired() is False

    def test_no_expiry(self):
        identity = AgentIdentity(agent_id="permanent")
        assert identity.is_expired() is False


class TestAgentCredential:
    def test_defaults(self):
        cred = AgentCredential(agent_id="titus", expires_at="2026-07-10T05:00:00Z")
        assert cred.credential_id != ""
        assert cred.role == AgentRole.GUEST
        assert cred.issued_at != ""

    def test_valid_credential(self):
        import datetime
        future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
        cred = AgentCredential(agent_id="titus", expires_at=future)
        assert cred.is_valid() is True

    def test_expired_credential(self):
        cred = AgentCredential(agent_id="titus", expires_at="2020-01-01T00:00:00Z")
        assert cred.is_valid() is False

    def test_permissions_from_identity(self):
        identity = AgentIdentity(
            agent_id="titus",
            role=AgentRole.DEVOPS,
            permissions=[Permission.TOOL_WRITE_FILE, Permission.TOOL_PATCH],
        )
        cred = create_credential(identity)
        assert cred.agent_id == "titus"
        assert cred.permissions == [Permission.TOOL_WRITE_FILE, Permission.TOOL_PATCH]
        assert cred.issuer_id == "root-ca"

    def test_credential_ttl(self):
        identity = AgentIdentity(agent_id="titus")
        cred = create_credential(identity, ttl_minutes=30)
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        expiry = datetime.datetime.fromisoformat(cred.expires_at)
        diff = (expiry - now).total_seconds()
        assert 25 * 60 < diff < 35 * 60  # Approximately 30 minutes


class TestSignedMessage:
    def test_defaults(self):
        msg = SignedMessage(sender_id="moses", recipient_id="titus")
        assert msg.message_id != ""
        assert msg.timestamp != ""
        assert msg.topic == "general"
        assert msg.priority == "normal"

    def test_signing_payload_includes_fields(self):
        msg = SignedMessage(
            sender_id="moses",
            recipient_id="titus",
            payload={"task": "check_health"},
        )
        payload = msg.to_signing_payload()
        assert "moses" in payload
        assert "titus" in payload
        assert "check_health" in payload
        assert "message_id" in payload

    def test_custom_priority(self):
        msg = create_signed_message(
            sender_id="kustos",
            recipient_id="moses",
            payload={"alert": "intrusion_detected"},
            priority="critical",
        )
        assert msg.priority == "critical"

    def test_signature_is_verifiable_format(self):
        msg = SignedMessage(
            sender_id="moses",
            recipient_id="titus",
            signature="a" * 128,  # Valid hex-encoded Ed25519 signature
        )
        assert len(msg.signature) == 128


class TestIdentityRegistry:
    def test_register_and_get(self):
        registry = IdentityRegistry()
        identity = AgentIdentity(
            agent_id="titus",
            role=AgentRole.DEVOPS,
            public_key="a" * 64,
        )
        registry.register(identity)
        retrieved = registry.get("titus")
        assert retrieved is not None
        assert retrieved.agent_id == "titus"

    def test_register_duplicate_raises(self):
        registry = IdentityRegistry()
        registry.register(AgentIdentity(agent_id="titus", public_key="a" * 64))
        with pytest.raises(ValueError, match="already registered"):
            registry.register(AgentIdentity(agent_id="titus", public_key="b" * 64))

    def test_register_duplicate_key_raises(self):
        registry = IdentityRegistry()
        registry.register(AgentIdentity(agent_id="titus", public_key="a" * 64))
        with pytest.raises(ValueError, match="Public key already registered"):
            registry.register(AgentIdentity(agent_id="moses", public_key="a" * 64))

    def test_get_by_public_key(self):
        registry = IdentityRegistry()
        registry.register(AgentIdentity(agent_id="titus", public_key="a" * 64))
        retrieved = registry.get_by_public_key("a" * 64)
        assert retrieved is not None
        assert retrieved.agent_id == "titus"

    def test_get_unknown_agent(self):
        registry = IdentityRegistry()
        assert registry.get("nonexistent") is None

    def test_revoke(self):
        registry = IdentityRegistry()
        registry.register(AgentIdentity(agent_id="titus", public_key="a" * 64))
        registry.revoke("titus", reason="Key compromised")
        identity = registry.get("titus")
        assert identity is None  # Revoked identities are excluded from active

    def test_list_active(self):
        registry = IdentityRegistry()
        registry.register(AgentIdentity(agent_id="titus", public_key="a" * 64))
        registry.register(AgentIdentity(agent_id="moses", public_key="b" * 64))
        registry.revoke("titus", reason="Compromised")
        active = registry.list_active()
        assert len(active) == 1
        assert active[0].agent_id == "moses"


class TestCredentialLifecycle:
    def test_issue_and_verify_credential(self):
        registry = IdentityRegistry()
        identity = AgentIdentity(
            agent_id="titus",
            role=AgentRole.DEVOPS,
            public_key="a" * 64,
        )
        registry.register(identity)
        cred = create_credential(identity)
        registry.issue_credential(cred)
        verified = registry.verify_credential(cred.credential_id)
        assert verified is not None
        assert verified.agent_id == "titus"

    def test_expired_credential_fails_verification(self):
        registry = IdentityRegistry()
        identity = AgentIdentity(agent_id="titus", public_key="a" * 64)
        registry.register(identity)
        cred = AgentCredential(
            agent_id="titus",
            expires_at="2020-01-01T00:00:00Z",
        )
        registry.issue_credential(cred)
        assert registry.verify_credential(cred.credential_id) is None

    def test_revoked_agent_invalidates_credentials(self):
        registry = IdentityRegistry()
        identity = AgentIdentity(agent_id="titus", public_key="a" * 64)
        registry.register(identity)
        cred = create_credential(identity)
        registry.issue_credential(cred)
        registry.revoke("titus", reason="Compromised")
        assert registry.verify_credential(cred.credential_id) is None

    def test_revoke_credential(self):
        registry = IdentityRegistry()
        identity = AgentIdentity(agent_id="titus", public_key="a" * 64)
        registry.register(identity)
        cred = create_credential(identity)
        registry.issue_credential(cred)
        registry.revoke_credential(cred.credential_id)
        assert registry.verify_credential(cred.credential_id) is None


class TestSignatureVerification:
    def test_verify_valid_format(self):
        registry = IdentityRegistry()
        identity = AgentIdentity(
            agent_id="moses",
            role=AgentRole.ORCHESTRATOR,
            public_key="a" * 64,
        )
        registry.register(identity)
        msg = SignedMessage(
            sender_id="moses",
            recipient_id="titus",
            signature="a" * 128,
        )
        assert registry.verify_message_authenticity(msg) is True

    def test_verify_wrong_signature_length(self):
        registry = IdentityRegistry()
        identity = AgentIdentity(agent_id="moses", public_key="a" * 64)
        registry.register(identity)
        msg = SignedMessage(
            sender_id="moses",
            recipient_id="titus",
            signature="too-short",
        )
        assert registry.verify_message_authenticity(msg) is False

    def test_verify_revoked_sender(self):
        registry = IdentityRegistry()
        identity = AgentIdentity(agent_id="moses", public_key="a" * 64)
        registry.register(identity)
        registry.revoke("moses", reason="Compromised")
        msg = SignedMessage(
            sender_id="moses",
            recipient_id="titus",
            signature="a" * 128,
        )
        assert registry.verify_message_authenticity(msg) is False

    def test_verify_unknown_sender(self):
        registry = IdentityRegistry()
        msg = SignedMessage(
            sender_id="unknown",
            recipient_id="titus",
            signature="a" * 128,
        )
        assert registry.verify_message_authenticity(msg) is False

    def test_verify_empty_signature(self):
        registry = IdentityRegistry()
        identity = AgentIdentity(agent_id="moses", public_key="a" * 64)
        registry.register(identity)
        msg = SignedMessage(sender_id="moses", recipient_id="titus")
        assert registry.verify_message_authenticity(msg) is False


class TestPermissionPresets:
    def test_orchestrator_has_all_devops_permissions(self):
        for perm in DEV_OPS_PERMISSIONS:
            assert perm in ORCHESTRATOR_PERMISSIONS

    def test_guest_limited(self):
        assert Permission.TOOL_WRITE_FILE not in GUEST_PERMISSIONS
        assert Permission.TOOL_TERMINAL_READ in GUEST_PERMISSIONS
