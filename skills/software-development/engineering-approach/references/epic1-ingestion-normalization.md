# Epic 1: Encoding Detection + Korean Normalization

Ingestion preprocessing services for robust file handling with Korean text support.

## Story 1.2: Encoding Detection

**Service:** `services/encoding_detection.py`

**Purpose:** Auto-detect file encoding before parsing CRD/CSV files. Critical for Korean files that may be EUC-KR or CP949 encoded.

### Key Functions

```python
from services.encoding_detection import auto_detect_encoding, decode_with_preview

# Auto-detect with confidence scores
result = auto_detect_encoding(file_bytes)
# Returns: EncodingDetectionResult(
#   detected_encoding="euc-kr",
#   confidence=0.98,
#   is_confident=True,  # >= 0.95
#   candidates=[{"encoding": "euc-kr", "confidence": 0.98}, ...],
#   sample_decoded="안녕하세요..."
# )

# Decode with preview (first N rows)
preview = decode_with_preview(file_bytes, "euc-kr", rows=10)
# Returns: {"encoding": "euc-kr", "rows": [...], "total_chars": N, "error": None}
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/ingestion/encode/detect` | POST | Upload file → encoding detection result |
| `/api/v1/ingestion/encode/decode` | POST | Upload file + encoding → first 10 rows preview |

### Testing Pattern

```python
# tests/test_encoding_detection.py

class TestAutoDetectEncoding:
    def test_detect_utf8(self):
        content = b"Hello, World! \xec\x95\x88\xeb\x85\x95"  # UTF-8 Korean
        result = auto_detect_encoding(content)
        assert result.detected_encoding == "utf-8"
        assert result.is_confident is True

    def test_detect_euc_kr(self):
        content = "안녕하세요".encode("euc-kr")
        result = auto_detect_encoding(content)
        assert any(c["encoding"] in ("euc-kr", "cp949") for c in result.candidates)
```

### Dependency

Add to `pyproject.toml`:
```toml
dependencies = [
    "chardet>=5.2.0",
    # ...
]
```

Install: `pip install chardet`

---

## Story 1.3: Korean Normalization

**Service:** `services/korean_normalization.py`

**Purpose:** Normalize Korean text for storage and matching: NFC, Hanja→Hangul conversion, jamo decomposition.

### Key Functions

```python
from services.korean_normalization import (
    normalize_korean,
    decompose_to_jamo,
    extract_initial_jamo,
    normalize_for_search,
    fuzzy_match_korean,
)

# Full normalization with all forms
result = normalize_korean("金敏秀")
# Returns: NormalizedText(
#   original="金敏秀",
#   normalized="김민수",
#   has_hanja=True,
#   hanja_mappings={"金": "김", "敏": "민", "秀": "수"},
#   jamo_decomposed="김민ᄉᆔ"  # Unicode jamo (U+1100–U+11FF)
# )

# Jamo decomposition only
jamo = decompose_to_jamo("한국")  # "한ᄀᆮ"

# Initial jamo only (abbreviation matching)
initials = extract_initial_jamo("가나다라")  # "ᄀᄂᄃᄅ"

# Search normalization (no jamo)
search_term = normalize_for_search("金敏秀")  # "김민수"

# Fuzzy matching
matches = fuzzy_match_korean("金敏秀", "김민수", threshold=0.8)  # True
```

### Hanja Mapping

Built-in dictionary of ~50 common Hanja characters:

```python
HANJA_TO_HANGUL = {
    # Family names
    "金": "김", "李": "이", "朴": "박", "崔": "최", "鄭": "정",
    "姜": "강", "趙": "조", "尹": "윤", "張": "장", "林": "임",
    # Given name characters
    "敏": "민", "秀": "수", "智": "지", "恩": "은", "俊": "준",
    # Common title/work characters
    "愛": "애", "國": "국", "山": "산", "水": "수", "月": "월",
    # ... extend as needed
}
```

**Note:** Production would use a full Hanja database. This v1 lookup covers the most common characters in Korean names and titles.

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/ingestion/normalize` | POST | Normalize text → all forms (original, normalized, jamo) |
| `/api/v1/ingestion/normalize/search` | POST | Normalize for search (NFC + Hanja, no jamo) |
| `/api/v1/ingestion/normalize/fuzzy-match` | POST | Fuzzy match two Korean strings via jamo |

### Testing Pattern

```python
# tests/test_korean_normalization.py

class TestNormalizeKorean:
    def test_hanja_conversion(self):
        result = normalize_korean("金敏秀")
        assert result.normalized == "김민수"
        assert result.has_hanja is True
        assert "金" in result.hanja_mappings

    def test_jamo_decomposition(self):
        result = normalize_korean("한국")
        assert len(result.jamo_decomposed) == 6  # 2 syllables × 3 jamo

class TestFuzzyMatch:
    def test_hanja_match(self):
        assert fuzzy_match_korean("金敏秀", "김민수") is True

    def test_no_match(self):
        assert fuzzy_match_korean("김민수", "이철수") is False
```

### Jamo Unicode Ranges

Jamo characters live in Unicode Hangul Jamo block (U+1100–U+11FF):
- Initial consonants (choseong): U+1100–U+115F
- Medial vowels (jungseong): U+1160–U+11A7
- Final consonants (jongseong): U+11A8–U+11FF

**Pitfall:** Jamo display as combining characters in terminals/logs. Tests should check `len(jamo)` rather than asserting specific character values.

---

## Integration Workflow

Typical ingestion pipeline:

```
1. Upload file → detect encoding (Story 1.2)
2. Decode with detected encoding
3. Parse CRD/CSV rows
4. For each Korean text field (names, titles):
   - normalize_korean() before storage
   - Store both original and normalized forms
5. For search queries:
   - normalize_for_search() on query
   - Match against normalized columns
6. For fuzzy matching:
   - decompose_to_jamo() on both sides
   - fuzzy_match_korean() with threshold
```

---

## When to Use This Pattern

- **Encoding detection:** Any file upload endpoint that accepts CRD/CSV from external sources (especially Korean broadcasters/societies)
- **Korean normalization:** Any feature storing or matching Korean names/titles (creator names, work titles, society names)
- **Fuzzy matching:** Search features, duplicate detection, matching pipelines (Epic 10)

---

## Related References

- `references/korean-text-normalization.md` — Korean normalization for Epic 10 name matching (pg_texample integration, variant-based similarity)
- `references/pro-metadata-systems-research-methodology.md` — Broader Korean matching challenges (romanization variance, Konglish, ISRC collisions)
