# Korean Text Normalization for Name Matching

Technique for handling Korean name variance in similarity matching (EPIC 10).

**Broader context:** This file covers text normalization techniques. For the full landscape of Korean matching challenges — including romanization variance types, Konglish handling, encoding detection, ISRC collision patterns, and artist disambiguation — see `references/pro-metadata-systems-research-methodology.md`.

## Problem

Korean names appear in multiple forms that break naive string comparison:

| Variant | Example |
|---|---|
| Hangul (standard) | 김민수 |
| Hanja (CJK) | 金敏秀 |
| Romanized | Kim Min-su / Kim Minsoo |
| Half-width jamo | ｱｲｳ (legacy systems) |
| Spacing variant | 김 민수 / 김민수 |
| NFD (jamo) | ㄱㅣㅁ ㅁㅣㄴ ㅅㅜ |

## Solution: Variant-Based Similarity

Generate multiple normalized forms for each text, then compute similarity as the **max over all variant pairs**.

### Core Functions

```python
# In services/matching.py

def normalize_variants(text: str) -> list[str]:
    """Returns [NFC_base, NFD_jamo] for Korean text, [NFC_base] otherwise."""
    base = normalize(text)
    result = [base]
    if _has_korean(text):
        kr = korean_normalize(text)
        kr_norm = normalize(kr)
        nfd = unicodedata.normalize("NFD", kr_norm)
        if nfd != kr_norm:
            result.append(nfd)
    return result

def trigram_similarity(a: str, b: str) -> float:
    """Jaccard trigram similarity over all variant pairs."""
    va = normalize_variants(a)
    vb = normalize_variants(b)
    max_sim = 0.0
    for na in va:
        for nb in vb:
            sim = _jaccard(_trigrams(na), _trigrams(nb))
            if sim > max_sim:
                max_sim = sim
    return max_sim
```

### Hanja→Hangul Lookup

Maintain a dict of common Korean Hanja (surnames + frequent given-name chars):

```python
_HANJA_TO_HANGUL = {
    "\u91d1": "\uae40",  # 金 → 김
    "\u674e": "\uc774",  # 李 → 이
    "\u6734": "\ubc15",  # 朴 → 박
    "\u5d14": "\ucd5c",  # 崔 → 최
    # ... 50 total entries in production
}

def _convert_hanja(text: str) -> str:
    return "".join(_HANJA_TO_HANGUL.get(c, c) for c in text)

def _is_hanja(c: str) -> bool:
    return 0x4E00 <= ord(c) <= 0x9FFF  # CJK Unified Ideographs
```

The lookup is integrated into `normalize()` so it runs on every text (zero-cost on non-Hanja).

### Half-Width Jamo Fix

Half-width jamo (U+FFA1-U+FFDC from legacy encodings) are normalized by NFC:

```python
def _fix_halfwidth(text: str) -> str:
    return unicodedata.normalize("NFC", text)
```

Unicode NFC composition converts half-width jamo → full-width Hangul syllables automatically.

## Integration Pattern

### In the normalize() function:

```python
def normalize(text: str) -> str:
    t = unicodedata.normalize("NFC", text)
    t = _convert_hanja(t)        # Hanja → Hangul
    t = t.lower().strip()
    t = _NON_ALNUM_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()
```

### In PostgreSQL pg_texample path:

The `title_norm` column stores the NFC-normalized form (with Hanja→Hangul applied). The pg_texample index handles trigram matching natively at DB level. NFD variants are only used in the Python fallback path.

### In fuzzy matching (find_candidates):

```python
# Python fallback — uses variant-based similarity:
for work in db.query(Work).filter(Work.title.isnot(None)).all():
    sim = trigram_similarity(usage.title, work.title or "")
    if sim >= threshold:
        scores.append((work, sim, ...))

# PostgreSQL path — uses pg_texample on title_norm column:
rows = db.execute(text("""
    SELECT id, similarity(:title, title_norm) AS sim
    FROM works
    WHERE title_norm IS NOT NULL
      AND similarity(:title, title_norm) > :threshold
    ORDER BY sim DESC
    LIMIT :limit
"""), {"title": usage_norm, ...})
```

## Korean Detection

```python
def _has_korean(text: str) -> bool:
    return any(0xAC00 <= ord(c) <= 0xD7AF or _is_hanja(c) for c in text)
```

Only generates NFD variants when Korean text is detected — zero overhead for English.

## What This Covers

| Variance | Match? | Mechanism |
|---|---|---|
| 김민수 vs 김민수 | 1.0 | exact match |
| 김민수 vs 金敏秀 | ~0.5+ | Hanja→Hangul conversion |
| 김민수 vs 김 민수 | ~0.2+ | whitespace collapsed, partial trigram overlap |
| 김민수 vs 김민수 (NFD) | 1.0 | NFD vs NFD variant |
| 김민수 vs Hello World | <0.1 | low trigram overlap (no false positive) |
| Half-width ｳ vs full-width 수 | 1.0 | NFC normalization |

## When to Use This Pattern

- Any feature that needs to match Korean names against an existing catalog
- User-generated input in Korean that may have spacing, encoding, or Hanja variation
- EPIC 10 matching pipeline (Stories 10.1–10.4)
