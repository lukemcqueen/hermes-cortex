# Work Registration with Ownership Validation

**When to use:** Registering platform-native works (not synced from external systems) with creator ownership splits that must sum to 100%.

## Core Pattern

1. **Normalize title** (NFC + Hanja→Hangul) before storage
2. **Validate ownership** using existing domain invariants (`validate_ownership_basis_points`)
3. **Generate unique work code** (platform-native prefix + timestamp + random)
4. **Create work record** with `is_platform_native=True`
5. **Create ownership splits** proportional to share percentages

## Service Implementation

```python
from services.korean_normalization import normalize_korean
from domain.invariants import validate_ownership_basis_points
from db.models import Work, OwnershipSplit


@dataclass
class CreatorInput:
    """Creator input for work registration."""
    name: str
    role: str  # composer, lyricist, arranger, publisher
    share_percentage: int  # basis points
    ipi: str | None = None


def register_work(
    db: Session,
    title: str,
    creators: list[CreatorInput],
    iswc: str | None = None,
    created_by: int | None = None,
) -> WorkRegistrationResult:
    """
    Register a new platform-native work.

    1. Normalizes title (NFC + Hanja→Hangul)
    2. Generates unique work code
    3. Validates ownership sums to 100%
    4. Creates work record
    5. Creates ownership splits

    Returns WorkRegistrationResult with status.
    """
    # Normalize title
    title_normalized = normalize_korean(title).normalized

    # Validate ownership before creating
    shares = [{"percentage": c.share_percentage} for c in creators]
    ownership_validation = validate_ownership_basis_points(shares)

    if not ownership_validation.valid:
        return WorkRegistrationResult(
            work_id=0,
            work_code="",
            title=title,
            title_normalized=title_normalized,
            status="rejected",
            ownership_valid=False,
            message=f"Ownership validation failed: {ownership_validation.status}",
        )

    # Generate unique work code
    work_code = generate_work_code()  # e.g., "PN-20260604-1234"

    # Create work record
    work = Work(
        work_code=work_code,
        title=title,
        title_normalized=title_normalized,
        iswc=iswc,
        status="registered",
        is_platform_native=True,
        created_by=created_by,
    )
    db.add(work)
    db.flush()  # Get the work ID

    # Create ownership splits
    for creator in creators:
        split = OwnershipSplit(
            work_id=work.id,
            territory_code="KR",
            split_type="performance",
            rights_holder_id=creator.share_percentage,  # Placeholder until user linking
            rights_holder_name=creator.name,
            share_percentage=creator.share_percentage,
            is_deleted=False,
        )
        db.add(split)

    db.commit()
    return WorkRegistrationResult(...)
```

## API Endpoint

```python
class RegisterWorkRequest(BaseModel):
    title: str
    iswc: str | None = None
    creators: list[dict]  # [{name, role, share_percentage, ipi?}, ...]


class RegisterWorkResponse(BaseModel):
    work_id: int
    work_code: str
    title: str
    title_normalized: str | None
    status: str
    ownership_valid: bool
    message: str


@router.post("/works", response_model=RegisterWorkResponse)
def register_work_endpoint(req: RegisterWorkRequest, db: Session):
    creators = [
        CreatorInput(
            name=c["name"],
            role=c.get("role", "composer"),
            share_percentage=c["share_percentage"],
            ipi=c.get("ipi"),
        )
        for c in req.creators
    ]

    result = register_work(db, title=req.title, creators=creators, iswc=req.iswc)

    if result.status == "rejected":
        raise HTTPException(status_code=400, detail=result.message)

    return result
```

## Test Cases

```python
class TestRegisterWorkEndpoint:
    def test_register_work_valid_ownership(self):
        """POST /api/v1/ingestion/works with valid ownership (100%)."""
        payload = {
            "title": "Test Song",
            "creators": [
                {"name": "Alice", "role": "composer", "share_percentage": 6000},
                {"name": "Bob", "role": "lyricist", "share_percentage": 4000},
            ],
        }
        response = client.post("/api/v1/ingestion/works", json=payload)
        assert response.status_code == 200
        assert response.json()["ownership_valid"] is True

    def test_register_work_with_hanja_title(self):
        """Hanja title should normalize to Hangul."""
        payload = {
            "title": "金敏秀的歌",  # Hanja + Chinese
            "creators": [{"name": "김민수", "role": "composer", "share_percentage": 10000}],
        }
        response = client.post("/api/v1/ingestion/works", json=payload)
        assert response.json()["title_normalized"] is not None
        assert "김" in response.json()["title_normalized"]

    def test_register_work_invalid_ownership(self):
        """Ownership >100% should fail."""
        payload = {
            "title": "Test Song",
            "creators": [
                {"name": "Alice", "share_percentage": 6000},
                {"name": "Bob", "share_percentage": 6000},  # Total 120%
            ],
        }
        response = client.post("/api/v1/ingestion/works", json=payload)
        assert response.status_code == 400
        assert "Ownership validation failed" in response.json()["detail"]

    def test_register_work_komca_fractions(self):
        """KOMCA standard: composer 12/20 (60%), lyricist 6/20 (30%), arranger 2/20 (10%)."""
        payload = {
            "title": "KOMCA Standard Split",
            "creators": [
                {"name": "작곡가", "role": "composer", "share_percentage": 6000},
                {"name": "작사가", "role": "lyricist", "share_percentage": 3000},
                {"name": "편곡가", "role": "arranger", "share_percentage": 1000},
            ],
        }
        response = client.post("/api/v1/ingestion/works", json=payload)
        assert response.status_code == 200
        assert response.json()["ownership_valid"] is True
```

## Database Schema

```python
class Work(Base):
    __tablename__ = "works"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    title_normalized: Mapped[str | None] = mapped_column(String(500), nullable=True)
    iswc: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    is_platform_native: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
```

## Migration

```python
def upgrade() -> None:
    op.create_table(
        "works",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("work_code", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("title_normalized", sa.String(length=500), nullable=True),
        sa.Column("iswc", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("is_platform_native", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_works_work_code", "works", ["work_code"], unique=True)
    op.create_index("ix_works_iswc", "works", ["iswc"])
```

## Pitfalls

- **Ownership validation must happen BEFORE DB writes** — reject early, don't create partial records
- **Title normalization is non-reversible** — store both original and normalized for audit
- **Work code generation must be unique** — use distributed ID generator in production (not just timestamp)
- **KOMCA fractions are standard** — composer 12/20, lyricist 6/20, arranger 2/20 (60%/30%/10%)
- **Basis points, not percentages** — 10000 = 100%, 6000 = 60%, etc.

## Related Patterns

- `references/korean-text-normalization.md` — NFC, Hanja→Hangul, jamo decomposition
- `references/backend-api-domain-patterns.md` — Domain invariants and validation
- `references/stub-parser-pattern.md` — File ingestion pipeline
