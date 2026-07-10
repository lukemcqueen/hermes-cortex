"""Tests for core/schemas/knowledge_record.py"""

from core.schemas.knowledge_record import (
    AccessPolicy,
    Classification,
    Confidence,
    KnowledgeMetadata,
    KnowledgeRecord,
    backfill_minimal,
    compute_expiry,
    now_iso,
    validate_metadata,
)


class TestEnums:
    def test_classification_values(self):
        assert Classification.PUBLIC == "public"
        assert Classification.INTERNAL == "internal"
        assert Classification.CONFIDENTIAL == "confidential"
        assert Classification.RESTRICTED == "restricted"
        assert Classification.CUSTOMER_DATA == "customer_data"
        assert Classification.PII == "pii"

    def test_confidence_values(self):
        assert Confidence.VERIFIED == "verified"
        assert Confidence.HIGH == "high"
        assert Confidence.MEDIUM == "medium"
        assert Confidence.LOW == "low"
        assert Confidence.UNKNOWN == "unknown"
        assert Confidence.STALE == "stale"

    def test_access_policy_values(self):
        assert AccessPolicy.PUBLIC_READ == "public_read"
        assert AccessPolicy.INTERNAL_READ == "internal_read"
        assert AccessPolicy.OWNER_ONLY == "owner_only"
        assert AccessPolicy.RESTRICTED == "restricted"


class TestKnowledgeMetadata:
    def test_defaults(self):
        meta = KnowledgeMetadata()
        assert meta.owner == ""
        assert meta.classification == Classification.INTERNAL
        assert meta.confidence == Confidence.UNKNOWN
        assert meta.access_policy == AccessPolicy.INTERNAL_READ
        assert meta.deletion_status == "active"
        assert meta.retention_days == 0
        assert meta.allowed_agents == []
        assert meta.audit_trail == []

    def test_all_fields_set(self):
        meta = KnowledgeMetadata(
            owner="titus",
            source="agent:lesson",
            tenant="org-acme",
            classification=Classification.CONFIDENTIAL,
            retention_days=90,
            expires_at="2026-10-07T12:00:00Z",
            confidence=Confidence.HIGH,
            provenance="human:luke",
            access_policy=AccessPolicy.RESTRICTED,
            allowed_agents=["titus", "moses"],
            created_at="2026-07-10T10:00:00Z",
            updated_at="2026-07-10T10:30:00Z",
            deletion_status="active",
        )
        assert meta.owner == "titus"
        assert meta.tenant == "org-acme"
        assert meta.classification == Classification.CONFIDENTIAL
        assert meta.retention_days == 90
        assert meta.confidence == Confidence.HIGH
        assert meta.access_policy == AccessPolicy.RESTRICTED
        assert meta.allowed_agents == ["titus", "moses"]


class TestKnowledgeRecord:
    def test_defaults(self):
        rec = KnowledgeRecord()
        assert rec.id == ""
        assert rec.kind == "note"
        assert rec.title == ""
        assert rec.content == ""
        assert rec.tags == []
        assert isinstance(rec.metadata, KnowledgeMetadata)

    def test_minimal_record(self):
        meta = KnowledgeMetadata(owner="test", source="manual", created_at="2026-07-10T00:00:00Z")
        rec = KnowledgeRecord(
            id="abc123",
            kind="lesson",
            title="Test lesson",
            content="Some content here",
            tags=["python", "debugging"],
            metadata=meta,
        )
        assert rec.id == "abc123"
        assert rec.kind == "lesson"
        assert rec.title == "Test lesson"
        assert rec.content == "Some content here"
        assert "python" in rec.tags
        assert rec.metadata.owner == "test"


class TestValidateMetadata:
    def test_empty_owner(self):
        meta = KnowledgeMetadata(source="test", created_at="2026-07-10T00:00:00Z")
        warnings = validate_metadata(meta)
        assert "owner is required" in warnings

    def test_empty_source(self):
        meta = KnowledgeMetadata(owner="test", created_at="2026-07-10T00:00:00Z")
        warnings = validate_metadata(meta)
        assert "source is required" in warnings

    def test_empty_created_at(self):
        meta = KnowledgeMetadata(owner="test", source="manual")
        warnings = validate_metadata(meta)
        assert "created_at is required" in warnings

    def test_invalid_iso_timestamp(self):
        meta = KnowledgeMetadata(
            owner="test", source="manual",
            created_at="not-a-date",
        )
        warnings = validate_metadata(meta)
        assert any("created_at" in w for w in warnings)

    def test_invalid_expires_at(self):
        meta = KnowledgeMetadata(
            owner="test", source="manual",
            created_at="2026-07-10T00:00:00Z",
            expires_at="bad-date",
        )
        warnings = validate_metadata(meta)
        assert any("expires_at" in w for w in warnings)

    def test_negative_retention(self):
        meta = KnowledgeMetadata(
            owner="test", source="manual",
            created_at="2026-07-10T00:00:00Z",
            retention_days=-1,
        )
        warnings = validate_metadata(meta)
        assert "retention_days cannot be negative" in warnings

    def test_restricted_no_agents(self):
        meta = KnowledgeMetadata(
            owner="test", source="manual",
            created_at="2026-07-10T00:00:00Z",
            access_policy=AccessPolicy.RESTRICTED,
        )
        warnings = validate_metadata(meta)
        assert any("allowed_agents is empty" in w for w in warnings)

    def test_invalid_deletion_status(self):
        meta = KnowledgeMetadata(
            owner="test", source="manual",
            created_at="2026-07-10T00:00:00Z",
            deletion_status="unknown_status",
        )
        warnings = validate_metadata(meta)
        assert any("deletion_status" in w for w in warnings)

    def test_valid_metadata_no_warnings(self):
        meta = KnowledgeMetadata(
            owner="titus",
            source="agent:lesson",
            created_at="2026-07-10T12:00:00Z",
            updated_at="2026-07-10T12:00:00Z",
        )
        assert validate_metadata(meta) == []


class TestBackfillMinimal:
    def test_creates_record_with_defaults(self):
        rec = backfill_minimal("hello world", kind="note", title="Greeting")
        assert rec.id != ""
        assert rec.kind == "note"
        assert rec.title == "Greeting"
        assert rec.content == "hello world"
        assert rec.metadata.owner == "system"
        assert rec.metadata.source == "import:legacy"
        assert rec.metadata.classification == Classification.INTERNAL
        assert rec.metadata.created_at != ""
        assert rec.metadata.deletion_status == "active"

    def test_content_hash_is_stable(self):
        rec1 = backfill_minimal("same content")
        rec2 = backfill_minimal("same content")
        assert rec1.id == rec2.id

    def test_different_content_different_hash(self):
        rec1 = backfill_minimal("content a")
        rec2 = backfill_minimal("content b")
        assert rec1.id != rec2.id

    def test_custom_owner_source(self):
        rec = backfill_minimal("test", owner="moses", source="agent:orchestrator")
        assert rec.metadata.owner == "moses"
        assert rec.metadata.source == "agent:orchestrator"


class TestHelpers:
    def test_now_iso_format(self):
        ts = now_iso()
        assert "T" in ts
        assert ts.endswith("Z") or "+" in ts or "-" in ts[10:]

    def test_compute_expiry_positive(self):
        expiry = compute_expiry(90)
        assert expiry is not None
        assert "T" in expiry

    def test_compute_expiry_zero(self):
        assert compute_expiry(0) is None

    def test_compute_expiry_negative(self):
        assert compute_expiry(-1) is None
