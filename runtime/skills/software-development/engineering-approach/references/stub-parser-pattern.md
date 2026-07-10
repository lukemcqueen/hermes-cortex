# Stub Parser Development Pattern

**When to use:** Building file ingestion pipelines where full parser implementation is complex (CWR 2.1, Excel, proprietary formats) but the upload API endpoint and basic validation infrastructure need to exist first.

**Core principle:** Write parsers that validate structure and count records, not parse every field. Return `(total, processed, failed)` tuples immediately so the upload endpoint works end-to-end. Full field-level parsing comes later.

## Stub Parser Template

```python
"""
CWR 2.1 parser stub (Epic 1, Story 1.1).

Validates basic CISAC CWR 2.1 structure.
Full implementation would parse NW/WR/SW/PU/IS records.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# CWR 2.1 mandatory header records
CWR_MANDATORY_RECORDS = ["HDR", "NW", "WR", "SW", "PU", "IS", "GR"]


def parse_cwr(content: bytes) -> tuple[int, int, int]:
    """
    Parse CWR 2.1 file.

    This is a stub implementation that:
    1. Validates file starts with HDR record
    2. Counts total lines
    3. Returns (total, processed, failed)

    Full implementation would parse:
    - HDR: Header record
    - NW: New work record
    - WR: Writer record
    - SW: Switch record
    - PU: Publisher record
    - IS: Interested party record
    - GR: Group record
    - EOT: End of transmission

    Args:
        content: Raw CWR file bytes

    Returns:
        (total_rows, processed_rows, failed_rows)
    """
    try:
        # Try to decode as UTF-8 first, then fallback to latin-1 (CWR standard)
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")

        lines = text.splitlines()
        total = len(lines)

        if total == 0:
            return (0, 0, 0)

        # Validate header record
        first_line = lines[0].strip() if lines else ""
        if not first_line.startswith("HDR"):
            raise ValueError(
                f"Invalid CWR file: expected HDR record at start, got '{first_line[:10]}...'"
            )

        # Validate mandatory record types are present
        record_types = {line[:2] for line in lines if len(line) >= 2}

        missing = []
        for rec in ["NW", "WR"]:  # Minimum required for a valid work submission
            if rec not in record_types:
                missing.append(rec)

        if missing:
            logger.warning("CWR file missing record types: %s", missing)
            # Don't fail - just log the warning

        # Count valid records
        processed = 0
        failed = 0

        for line in lines:
            if len(line) < 2:
                failed += 1
                continue

            record_type = line[:2]
            if record_type in CWR_MANDATORY_RECORDS or record_type in ("EOT", "EOF"):
                processed += 1
            else:
                logger.debug("Unknown CWR record type: %s", record_type)
                processed += 1  # Count as processed even if unknown

        logger.info("Parsed CWR file: %d total, %d processed, %d failed", total, processed, failed)
        return (total, processed, failed)

    except Exception as e:
        logger.error("CWR parse error: %s", e)
        raise ValueError(f"CWR parse failed: {e}")
```

## Key Patterns

### 1. Graceful Degradation

Stub parsers should work even when optional dependencies are missing:

```python
def parse_excel(content: bytes) -> tuple[int, int, int]:
    """Parse Excel (.xlsx) file with fallback when openpyxl unavailable."""
    try:
        # XLSX files are ZIP archives - validate the magic bytes
        if not content.startswith(b"PK"):
            raise ValueError("Invalid XLSX file: missing PK signature")

        # Try to open with openpyxl if available
        try:
            import openpyxl
            # Full parsing with openpyxl...
        except ImportError:
            # Fallback to basic ZIP validation
            logger.warning("openpyxl not installed - using basic XLSX validation")
            import zipfile
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                worksheets = [n for n in zf.namelist() if "worksheets/sheet" in n]
                if not worksheets:
                    raise ValueError("No worksheets found in XLSX file")
                # Count <row> elements from XML...
    except Exception as e:
        logger.error("Excel parse error: %s", e)
        raise ValueError(f"Excel parse failed: {e}")
```

### 2. Router Integration

Upload endpoints route to parsers based on file extension:

```python
try:
    # Route to appropriate parser based on file extension
    if name_lower.endswith(".cwr"):
        # CWR 2.1 parsing
        logger.info("Parsing CWR 2.1 file")
        total, processed, failed = parse_cwr(raw_content)
    elif name_lower.endswith((".xlsx", ".xls")):
        # Excel parsing
        logger.info("Parsing Excel file")
        total, processed, failed = parse_excel(raw_content)
    else:
        # CRD/CSV parsing (existing)
        version = detect_crd_version(raw_content)
        # ...
        total, processed, failed = process_crd_file(db, raw_content, processor, job_uuid)
except Exception as e:
    job.status = "failed"
    job.error_detail = str(e)
    db.commit()
    raise HTTPException(status_code=500, detail=f"Import failed: {e}")
```

### 3. Test Strategy

Test stubs for structure validation, not field-level correctness:

```python
class TestCwrParser:
    def test_parse_valid_cwr(self):
        """Parse valid CWR file with HDR and NW records."""
        cwr_content = b"""HDR0100000001CWR21000000000000000000000000000000000000
NW0100000012345678901234567890123456789012345678901234567890
WR0100000012345678901234567890123456789012345678901234567890
EOT000000000000000000000000000000000000000000000000000000000000"""

        total, processed, failed = parse_cwr(cwr_content)

        assert total == 4
        assert processed == 4
        assert failed == 0

    def test_parse_cwr_missing_header(self):
        """CWR file without HDR should fail."""
        cwr_content = b"""NW0100000012345678901234567890123456789012345678901234567890"""

        with pytest.raises(ValueError, match="Invalid CWR file"):
            parse_cwr(cwr_content)
```

## When to Evolve Beyond Stub

A stub parser is complete when:
- ✅ Upload endpoint accepts the file type
- ✅ Basic structure validation works (header records, file format)
- ✅ Returns accurate row counts
- ✅ Logs warnings for missing mandatory elements
- ✅ Tests cover valid/invalid/edge cases

Evolve to full parser when:
- Field-level validation is required (ISWC format, IPI validation)
- Cross-record relationships must be validated (writer shares sum to 100%)
- Business rules need enforcement (territory restrictions, society codes)
- Data extraction is needed (parse NW records into Work objects)

## Related Patterns

- `references/fullstack-feature-workflow.md` — End-to-end feature delivery
- `references/backend-api-feature-workflow.md` — Backend API development flow
- `references/korean-text-normalization.md` — Text normalization for ingestion
