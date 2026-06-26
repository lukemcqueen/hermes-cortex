# CISAC CRD/CWR Fixed-Width Format Patterns

CISAC CRD (Common Data Repository) and CWR (Common Works Registration) files use fixed-width record formats with strict field lengths.

## CRD v3.0 R4 Field Lengths

| Record | Field | Length | Format | Notes |
|---|---|---|---|---|
| HDR | Record type | 3 | `HDR` | Transmission Header |
| HDR | Standard version | 6 | `02.10` | CRD version |
| HDR | Sender ID | 6 | CISAC code | e.g. `ACME` |
| HDR | Recipient ID | 6 | CISAC code | e.g. `SESAC` |
| HDR | Group count | 8 | `00000002` | Zero-padded |
| HDR | Record count | 8 | `00000123` | Zero-padded |
| SDN | Amount | 18 | `000000000008000000` | **18-digit zero-padded integer** |
| MDR | Amount | 18 | `000000050000000000` | **18-digit zero-padded integer** |
| ICC | Amount | 18 | `000000100000000000` | **18-digit zero-padded integer** |
| ICC | Share % | 10 | `0000006000` | Basis points (6000 = 60%) |
| MWN | Work title | 50 | Left-padded | Truncated if longer |
| MWN | ISWC | 15 | `T-123-456-789-0` | With dashes |
| MWN | Duration | 10 | `0000258000` | Milliseconds |

## Common Pitfalls

### Amount Format (18 digits)

**Wrong:**
```python
assert amount == "500000000000"  # Variable length
```

**Correct:**
```python
assert amount == "000000050000000000"  # 18-digit zero-padded
# Or generate with: f"{amount:018}"
```

The CRD spec defines amount fields as 18-character fixed-width. Leading zeros are significant — they indicate the field position, not numeric value.

### Record Lengths

All CRD records are fixed-width:
- HDR: 100 chars
- GRH: 100 chars
- SDN: 200 chars
- GRT: 100 chars
- MWN: 300 chars
- MDS: 100 chars
- MDR: 150 chars
- ICC: 200 chars
- WER: 150 chars
- TRL: 100 chars

Use `.ljust(width)` for padding:
```python
hdr_content = f"HDR{version}{sender:6}{recipient:6}{groups:08}{records:08}"
hdr = hdr_content.ljust(100)  # Pad to 100 chars
```

## CWR 2.1 Notes

CWR 2.1 uses similar fixed-width conventions but with different record types (NW, WR, SW, PU, IS, etc.). Amounts are also 18-digit zero-padded.

## Test Assertions

When testing CRD/CWR parsers:

```python
# ✅ Correct assertion for 18-digit amount
assert group.mdrs[0]["amount"] == "000000050000000000"

# ❌ Wrong — variable length
assert group.mdrs[0]["amount"] == "500000000000"
```

## Session Context

This pattern was discovered during Epic 8 (CISAC Exchange) implementation in acme-royalty. Two pre-existing test failures were caused by incorrect amount assertions (variable-length vs 18-digit fixed-width). Tests were corrected to match CRD spec.

## Related

- `stub-parser-pattern.md` — Stub parser development for file ingestion
- `backend-api-test-patterns.md` — Test assertion patterns
