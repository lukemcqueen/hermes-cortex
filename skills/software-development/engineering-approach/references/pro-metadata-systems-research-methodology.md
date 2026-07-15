# PRO Metadata Systems Research Methodology

How to research copyright society metadata/catalog systems and Korean cross-lingual matching challenges for PRD creation. Bridges the gap between `references/prd-creation-methodology.md` (which covers the PRD creation process generically) and `references/korean-text-normalization.md` (which covers text normalization techniques narrowly).

## When to Use

- Creating a PRD for a PRO metadata store, catalog system, or matching engine
- Evaluating PRO catalog architectures for benchmarking
- Researching Korean↔English matching failure modes
- Feeding research into hc-elicit (PRD) and hc-party (review) phases

## PRO Catalog System Research Dimensions

When benchmarking PRO catalog/matching systems, capture these dimensions:

| Dimension | What to Look For | Why It Matters |
|---|---|---|
| **Architecture pattern** | Event-sourced microservices (PRS Chronos), centralized work master (GEMA), graph DB (SOCAN Neo4j), shared-nothing sharded (ASCAP ACE), traditional centralized (JASRAC, KOMCA) | Determines scalability, audit capability, migration complexity |
| **Match engine strategy** | ISRC-only, multi-key composite, probabilistic, audio fingerprint, host-side vs PRO-side | Error rate varies dramatically — PRS saw 40% ISRC-only match error |
| **DSP coverage** | Direct DDEX/API (PRS, GEMA, APRA), YouTube Content ID partnership, limited (ASCAP) | Revenue coverage gap |
| **Audit trail** | Full event-sourced (PRS), versioned records (GEMA), basic, none | Regulatory compliance, dispute resolution |
| **Korean / CJK support** | None, Hanji/Hiragana (JASRAC), Korean-native (ACME target) | Directly affects match accuracy for Korean catalog |
| **Title variant limit** | ASCAP (99), PRS (50), GEMA (30), SOCAN (unlimited) | K-pop romanization variance can exceed 50 variants; ASCAP's 99 is a hard cap |
| **API availability** | Public (ASCAP ACE, SOCAN Repertoire), partner (APRA, BMI), internal (PRS, GEMA), none (JASRAC) | Integration cost and data access patterns |
| **Identifiers** | ISWC, ISRC, IPI/CAE, local work codes (GEMA Werknummer, JASRAC Work Code, KOMCA work ID) | Cross-PRO deduplication and CWR exchange |
| **Ownership model** | Per-work splits, per-territory splits, CWR 2.1 vs 2.2 multi-territorial | Distribution complexity |

### Research Sources

1. **PRO public repertoires** — ASCAP ACE (ascap.com/ace), SOCAN Repertoire (socan.com/repertoire), PRS for Music Repertoire (prsformusic.com/repertoire), GEMA Online Catalog (online.gema.de)
2. **CISAC annual reports** — global CMO statistics, technology adoption trends
3. **DDEX member directory** — which PROs subscribe to DDEX standards
4. **ICMP/BIEM publications** — mechanical rights society benchmarking
5. **Academic papers** — cross-lingual music matching, Korean NLP for song metadata

### Cautionary Tales (Reference for Risk Register)

- **PRS 40% ISRC-only error**: PRS for Music initially used ISRC-only matching for YouTube Content ID and found ~40% error rate. Switched to multi-key composite (ISRC + title + artist + duration). Motivates FR-MPL-01 through FR-MPL-06 and the evidence-based approach.
- **ASCAP 99-title variant limit**: ACE Repertoire caps title variants at 99 per work. For K-pop with extensive romanization variants, this is a hard limit. ASCAP has no romanization normalization — "Gangnam Style" had 4 romanization variants in ACE. Motivates variant dictionary (FR-RCAT-13).
- **GEMA 2022 migration corruption**: GEMA's catalog migration in 2022 corrupted work registrations, causing a 2-month distribution delay. Motivates snapshot-first approach (§10.4) and phased migration (§12).
- **SOCAN graph complexity**: SOCAN's Neo4j graph DB enables complex writer/publisher relationship queries but requires specialized skills. Alternative to relational; ACME stays relational for acme-royalty compatibility.

## Korean Cross-Lingual Matching Research

### Romanization Variance Types

Korean romanization appears in DSP metadata in at least 4 forms:

1. **Revised Romanization** (RR, official since 2000) — eotteoke, jeonjaeng
2. **McCune-Reischauer** (MR, older system) — eottŏk'e, chŏnjaeng
3. **Idiosyncratic commercial** — DSP/platform-specific (deuraibeu, jungkook, jk)
4. **Mixed** — partial RR, partial English, partial phonetic (e.g. "Daechwita" from Agust D)

Common variance patterns (example: "How You Like That" by BLACKPINK):
- RR: Eotteoke Geureonde
- MR: Eottŏk'e Kŭrŏnde
- Commercial: How You Like That (English title), Eotteoke Geureonde (RR)
- Half-romanized: Eotteo-ke Geu-reon-de (dash separators)

Research approach: **Catalog scan + variant dictionary** — don't rely on algorithmic inversion alone. A pre-built dictionary of 50K top works covers ~85% of variance. Build from existing match evidence + manual curation.

### Konglish (Korean-English Loanwords)

English loanwords in Korean are frequently back-transliterated inconsistently across DSPs. Example: "Love&드라이브":
- Love & Drive (English-only interpretation)
- Love & Deuraibeu (partial romanization)
- Love and Drive (expanded English)
- Love & 드라이브 (mixed Hangul + English)

**Dictionary approach**: Build a 500-1,000 term Konglish dictionary mapping Hangul→English. Prioritize terms from catalog scan. Common categories: technology (컴퓨터→computer), transportation (드라이브→drive), fashion/culture (쇼핑몰→shopping mall), food (커피→coffee).

Research method: Scan existing work titles for known Konglish patterns (syllables matching dictionary entries), cross-reference against known Konglish term lists online.

### Encoding Issues in Legacy Data

Korean PRO data commonly arrives in these encodings:

| Encoding | Korean Support | Typical Source |
|---|---|---|
| UTF-8 | Full (modern) | Current MWI, DSP APIs |
| EUC-KR | Korean (extended Unix code) | Legacy databases, older CWR files |
| CP949 | Korean (Windows) | Excel exports, older PC systems |
| CP932/Shift-JIS | Japanese | JASRAC cross-references |
| Broken UTF-8 | Corrupted | Bad imports, copy-paste from legacy systems |

Research: **Audit encoding distribution before building normalization pipeline**. Pull 10K sample works, check encoding via charset-detection (chardet/cchardet), report distribution. If >1% legacy encoding, build detection + conversion + reject path into pipeline Stage 1.

### DDEX Standards Research Dimensions

When researching DDEX standards alignment for a CMO metadata store, capture:

| Standard | What to Research | Decision Point |
|---|---|---|
| **CWR 2.1/2.2** | CWR record types (NW, SW, WR, PW, SP, TR, TX, VER), transaction codes (A/C/D), fixed-width vs XML format, version history | Schema field mapping for rights catalog tables |
| **DDEX ERN 3.8/4.x** | ERN entities (Release, SoundRecording, Resource, Deal, Party), element tree structure, required vs optional fields, version differences | Schema field mapping for DSP metadata tables |
| **NDDEX 1.0** | LyricText, LyricType, TimeCode, Language elements | Lyrics table design (future) |
| **DDEX RDR 3.x** | UsageLine, Revenue record structures | Matching engine input (acme-matching) |

Research method:
1. Download DDEX standard docs (ddex.net → standards → download PDF)
2. For each entity, extract: name, cardinality, field type, allowed values
3. Map to canonical schema: which fields are mandatory, which can be stored in JSONB
4. Check DDEX ACR (Available Codes Report) for allowed code values (genres, territories, etc.)

**Key decision: Store canonical, not raw. Raw files retained for audit only.**

### Korean DSP Non-Compliance Research

Korean DSPs (Melon, Genie, Bugs!, FLO, VIBE) typically do NOT use DDEX. Research approach:

1. Collect one sample export from each Korean DSP
2. Document: column headers (Korean), data types, identifier coverage (ISRC/UPC presence)
3. Identify missing fields: ISRC, UPC, genre in English, standardized territory codes
4. Design per-source YAML field mapper for each DSP

Sample field mapping document per DSP (research artifact):

```yaml
source: "Melon"
format: "CSV"
encoding: "CP949"
columns:
  - native: "곡명"
    canonical: "sound_recordings.track_title"
    type: TEXT
    notes: "May contain both Hangul and English in same field"
  - native: "아티스트"
    canonical: "sound_recordings.display_artist"
    type: TEXT
  - native: "장르"
    canonical: "sound_recordings.genre"
    type: ENUM
    mapping:
      발라드: Ballad
      댄스: Dance
      힙합: Hip-Hop
      알앤비: R&B
      인디: Indie
missing_identifiers:
  - isrc: "~30% of rows have no ISRC. Resolve via fuzzy matching."
  - upc: "Never provided"
```

### Artist Disambiguation for Korean Names

Same ISRC mapped to different works. Common causes:
- Re-recording by different artist (cover version inheriting ISRC)
- Multi-volume compilation (same ISRC on different volumes)
- Label error (ISRC accidentally duplicated)
- Wrong ISRC in metadata submission

Research: Internal 2023 ACME audit found ~3,200 collisions. Validate current count in Phase 0. Implement composite key matching (ISRC + registrant code + duration window) to handle collisions.

### Artist Disambiguation for Korean Names

Korean artists present unique disambiguation challenges:

1. **Name order variance**: Kim Namjoon vs Namjoon Kim (family name first in Korean, given name first in Western order)
2. **Stage name evolution**: Rap Monster → RM (BTS member)
3. **Sub-units**: Girls' Generation → GG-TTS, GG-Oh!GG; EXO → EXO-K, EXO-M
4. **Same name, different person**: "Soyeon" could be (G)I-DLE's Soyeon or former T-ARA's Soyeon
5. **Cross-cultural mixups**: BTS's V vs EXO's Xiumin (confusion in Western DSP metadata because both use single-letter stage names and similar face)

Research approach: Build IPI/CAE-verified artist registry (FR-RCAT-04) with sub-unit membership table (FR-RCAT-12). Use multiple signals: IPI, role (writer vs performer), sub-unit linking, group membership dates.

## Research-to-PRD Pipeline

When research is complete, feed findings into the PRD and architecture review:

```
Research Complete
  ↓
Save research doc → docs/research/<topic>-research.md
  ↓
Patch PRD:
  ├── §Competitive Benchmarking — add architecture details, cautionary tales
  ├── §Feature Requirements — add new FRs from research insights
  ├── §Technical Architecture — add patterns discovered (distribution snapshot, ISRC collision, point-in-time queries)
  ├── §Schema Design — add valid_from/valid_until to match_map, ISRC collision table, distribution_snapshots table
  ├── §Open Questions — add new unresolved questions
  └── §References — add research doc link, update industry standards/comparison tables
  ↓
Patch hc-party Review:
  ├── Add new critical risks (R6, R7, ...)
  ├── Add new medium issues (I6, I7, ...)  
  ├── Add new observations (O5, O6, ...)
  ├── Add new ADRs to trade-offs table
  ├── Update "What's Solid" section
  └── Update Recommended Actions
  ↓
Draft new ADRs for architecture decisions discovered in research
  ↓
**Output: 3-Store Architecture Pattern** — see `3-store-architecture-pattern` skill for implementation

## Related References

- `references/prd-creation-methodology.md` — generic PRD creation process (this file adds the research dimension)
- `references/architecture-review-methodology.md` — hc-party review (this file feeds into it)
- `references/korean-text-normalization.md` — Korean text normalization techniques (narrower scope, this file provides the broader context)
- `references/copyright-society-benchmarking.md` — 12-society website feature matrix (frontend features, not catalog/matching systems)
- `3-store-architecture-pattern` — the concrete architecture pattern derived from this research (Rights Catalog ↔ DSP Metadata ↔ Match Map). Read after research is complete and before building.
