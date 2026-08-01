---
name: cwr-file-processing
version: 1.0.0
description: >
  CISAC CWR (Common Works Registration) file processing for music copyright
  societies. Covers export generation (Rails + Python), ACK response handling,
  validation (structural + custom rules + field-level), share calculations,
  pub_share conversion, and ACK file analysis. Dual-stack: client-mwi
  (Rails/PostgreSQL) and client-works (Python/FastAPI/Next.js).
trigger: >
  When the task involves CWR export, CWR import, ACK file analysis,
  share validation, pub_share conversion, or CWR format validation.
  Load this skill before editing any CWR-related code in either
  client-mwi (Rails) or client-works (Python) projects.
domain: music copyright, CISAC CWR 2.1, collective rights management
---

# CWR File Processing

## Key Architecture

### Legacy Export (14K-line helper, still available)
- **Export**: `app/helpers/cwr_helper.rb` — `export_cwr()` generates CWR files with batch/file/upload logic
- **Validation**: `verify_cwr_file()` in t... (see below)

### Dual Stack
| Stack | Language | Role |
|-------|----------|------|
| `client-mwi` | Rails/PostgreSQL | Legacy export + validation, share calculations |
| `client-works` | Python/FastAPI/Next.js | Modern export/import pipeline, ACK analysis |

## CWR Format Basics (v2.1)

CWR (Common Works Registration) is a fixed-width or delimited text format
for registering musical works with collective rights management societies.
Key record types:

| Record | Purpose |
|--------|---------|
| `HDR` | Header — file control, sender/receiver |
| `GRH` | Group header — one per work |
| `NWR` | New Work registration — the work itself |
| `SWR` | Society Work Registration — society/publisher shares |
| `SPU` | Share Participant — writer/publisher shares |
| `ACK` | Acknowledgment — response to submitted records |
| `TRA` | Transmittal — batch-level acknowledgment |
| `TER` | Trailer — file totals and checksums |

**CWR 2.1 uses fixed-width fields.** Column positions are defined by the
spec — a one-character offset shift breaks the entire file. Field-level
validation must know exact start/end positions per record type.

## Export Generation

### Rails (client-mwi) — legacy path

```ruby
# app/helpers/cwr_helper.rb
def export_cwr(works:, sender:)
  lines = []
  lines << build_hdr(sender: sender)
  works.each do |work|
    lines << build_grh(work)
    lines << build_nwr(work)
    work.shares.each { |s| lines << build_spu(s) }
    lines << build_swr(work)
  end
  lines << build_ter
  lines.join("\n") + "\n"
end
```

Rules:
- **Fixed-width padding** — pad/truncate every field to its spec length
- **Character set** — CWR uses ISO-8859-1 with specific escape conventions
  for accented characters; UTF-8 input must be transcoded
- **Line length** — every line must be exactly the record's defined length;
  the TER checksum is computed over all preceding lines

### Python (client-works) — modern path

```python
# services/cwr_exporter.py
def build_export(works: list[Work], sender: str) -> str:
    records = [build_hdr(sender)]
    for w in works:
        records += [build_grh(w), build_nwr(w)]
        records += [build_spu(s) for s in w.shares]
        records.append(build_swr(w))
    records.append(build_ter(records))
    return "\n".join(records) + "\n"
```

## ACK Response Handling

When a society receives CWR files, it responds with an `ACK` file. The ACK
maps submitted records (via the original line/reference) to status codes:

| ACK status | Meaning | Action |
|------------|---------|--------|
| `AC` | Accepted | None |
| `RE` | Rejected | Fix the record and resubmit |
| `ER` | Error in record | Investigate the specific field error |

Parse ACK files to find rejected records and their error reasons:

```python
# services/ack_parser.py
def parse_ack(content: str) -> list[AckRecord]:
    """Return list of (original_line_no, record_type, status, error_text)."""
```

## Validation

### Structural validation

```python
def validate_structure(content: str) -> list[str]:
    errors = []
    lines = content.splitlines()
    if not lines[0].startswith("HDR"):
        errors.append("File must start with HDR record")
    if not lines[-1].startswith("TER"):
        errors.append("File must end with TER record")
    # GRH must be preceded by HDR, NWR must follow GRH, etc.
    return errors
```

### Custom rules (domain-specific)

- Each `NWR` must be followed by its `SPU` records before the next `GRH`
- Total shares per work must sum to 100
- `pub_share` must convert correctly between societies' share formats

### Field-level validation

```python
FIELD_SPECS = {
    "NWR": {"work_title": (1, 90), "language": (91, 93), ...},
}

def validate_field(record_type: str, line: str) -> list[str]:
    errors = []
    for field, (start, end) in FIELD_SPECS[record_type].items():
        value = line[start-1:end].strip()
        if field == "language" and value and len(value) != 2:
            errors.append(f"Invalid language code '{value}' at {start}-{end}")
    return errors
```

## Share Calculations

Shares per work must total 100%:

```ruby
def validate_shares(work)
  total = work.shares.sum(&:percentage)
  return if total == 100
  raise ShareError, "Work #{work.id} shares total #{total}% (expected 100%)"
end
```

Common share math:
- **Split between writer and publisher** — typically 50/50 writer-publisher,
  then subdivided per participant
- **Original publisher share** — the publisher's portion of the work
- **Controlled vs uncontrolled** — controlled compositions are 100% owned

## pub_share Conversion

`pub_share` (publisher share) must convert between societies' conventions:

- **US practice**: publisher gets 50% of the writer share (the "writer's
  share" split)
- **International**: publisher share is defined per the society agreement

Conversion is a source of silent corruption — validate the result equals the
expected total before writing.

## ACK File Analysis

```python
def analyze_ack(content: str) -> dict:
    records = parse_ack(content)
    return {
        "total": len(records),
        "accepted": sum(r.status == "AC" for r in records),
        "rejected": sum(r.status == "RE" for r in records),
        "errors": [r for r in records if r.status != "AC"],
    }
```

Report the analysis as: total, accepted, rejected, top error reasons.

## Pitfalls

- ❌ **Off-by-one in fixed-width fields** — a 1-char shift corrupts every field after it; verify with a known-good sample
- ❌ **Transcoding** — UTF-8 vs ISO-8859-1 accented characters break validation downstream
- ❌ **Shares not summing to 100** — reject before writing, not after
- ❌ **pub_share conversion errors** — verify converted totals match expected
- ❌ **Modifying the 14K-line legacy helper blindly** — use the modern Python path for new work; patch the helper only for compatibility bugs
- ❌ **Client PII in public artifacts** — CWR files contain copyrighted work metadata; never commit sample files with real client data

## Verification

```bash
# Structural validation
python -m services.cwr_validate < export.cwr && echo "structure OK"

# Field-level
python -m services.cwr_validate --fields < export.cwr

# Share totals
python -m services.cwr_validate --shares < export.cwr

# ACK analysis
python -m services.ack_parser < ack.cwr
```

## Related
- `rails-data-pipeline-debugging` — heuristics corrupting titles (same domain)
- `batch-job-optimization` — making CWR exports fast
- `postgres-schema-design` — the DB behind client-mwi/client-works
- `pii-scrubbing` — never leak client work metadata to public repos
