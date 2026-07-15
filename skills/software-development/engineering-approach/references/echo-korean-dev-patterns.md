---
title: Echo Korean — Development Patterns
---

## TTS (browser SpeechSynthesis)

The app uses the browser's built-in `SpeechSynthesisUtterance` API for Korean TTS — no backend required. Two integration points:

1. **PlayButton component** at `components/ui/play-button.tsx` — reusable button that speaks Korean text via `speechSynthesis`. Props: `text`, `lang` (default `ko-KR`), `size` (`sm`/`md`). Plays at 0.85 rate with pulsing animation. Safety timeout prevents stuck "playing" state.

2. **Reading view** (`app/read/[content_id]/page.tsx`):
   - "Read Aloud" button in ContentHeader — speaks entire article text (joins all segments)
   - Per-segment play button appears on hover (absolute positioned `-left-10`, `opacity-0 group-hover:opacity-100`)

3. **Review cards** (`components/review/review-card.tsx`) — already had `useSpeak` hook and `onPlayAudio` prop wired to card type renderers. No changes needed.

## User Settings page

Located at `/settings` (protected by middleware). Uses `PATCH /auth/me` endpoint which supports partial updates:

- `display_name`, `native_language`, `target_language`, `level`
- Schema: `UpdateProfileRequest` with `extra="forbid"`
- Service method: `UserService.update_profile(user_id, **fields)`
- Returns updated `UserResponse` with `is_admin`

The settings form includes selects for language (en/ko/ja) and level (beginner/intermediate/advanced) with save/success/error states.

## Admin login

Admin users are created via the normal signup flow, then promoted via direct SQL:

```sql
UPDATE users SET is_admin = true WHERE email = 'admin@...';
```

The `is_admin` field is now correctly returned in `_user_to_response()` and the auth `UserResponse` schema (both backend + frontend). Previously it was silently omitted from the auth response.

## Lexicon System

### Backend — TL-P1-1 through TL-P1-3

All three backend tasks are fully built:

- **TL-P1-1 (Model + Migration):** `models/lexicon.py` — LexiconItem (UUID PK, surface_form, normalized_form, dictionary_form, meaning_en, PartOfSpeech enum, level, frequency) + LexiconExample (FK to item, korean_text, english_translation, source). PartOfSpeech enum covers universal tags (NOUN, VERB, ADJ, ADV, PART, AUX, PRON, DET, NUM, CONJ, INTJ, X) + Korean-specific (EOMI, JOSA, PRE, SUF). Unique constraint on (surface_form, part_of_speech). Migration: `3b3174c356bd`.

- **TL-P1-2 (Search API):** `GET /lexicon/search` with multi-strategy matching — 1) exact prefix on normalized_form, 2) exact prefix on surface_form, 3) ILIKE on meaning_en. POS filter, level_min/level_max filters. Pagination with relevance ordering (surface_form exact first → normalized prefix → surface prefix → meaning). Full CRUD: `POST /lexicon/`, `PUT /lexicon/{id}`, `DELETE /lexicon/{id}`, `GET /lexicon/{id}`. Router registered in `main.py` as `lexicon.router` under `/lexicon` prefix.

- **TL-P1-3 (Kiwi Pipeline):** `KiwiService` (lazy singleton via `get_kiwi()`, ~500ms init). Full POS mapping from Kiwi tags (NNG, NNP, VV, VA, JKS, etc.) to universal PartOfSpeech enum via `POS_MAP` dict (49 entries). `ContentIngestionPipeline` in `services/content_ingestion.py`: tokenize → deduplicate → upsert lexicon_items → create token Spans with FK to lexicon_item. Idempotent on re-ingestion (removes existing token spans first).

### Frontend — TL-P1-4

`/admin/lexicon` page at `apps/web/src/app/admin/lexicon/page.tsx`:

- Search form with debounced input + POS dropdown filter
- Create/Edit modal form (LexiconFormModal) — surface_form, normalized_form, dictionary_form, meaning_en, POS select, level, frequency
- Delete with ConfirmDialog (danger variant)
- Pagination with adjacent-page ellipsis
- Loading skeleton (TableSkeleton), EmptyState, error banner with retry
- Admin-only route guard (redirects non-admin to `/`)
- i18n keys under `lexicon.admin.*` in both `en.json` and `ko.json`

### Tests — written June 2026

**`test_lexicon.py`** (18 tests):
- CRUD: create, create with examples, get by ID, get not-found, update, update not-found, delete, delete not-found
- Search: exact Korean, exact English, normalized prefix, POS filter, level_range filter, pagination (page boundary verification + disjoint page IDs), empty results, empty-query-returns-all
- Constraints: unique (surface_form, part_of_speech) rejected, same surface + different POS allowed

**`test_kiwi.py`** (15 tests):
- Normalize: NFKC, trim+lower, Korean preserved, empty string
- Analyze: basic sentence returns structured tokens (all 6 keys), normalized is lowercase, pure English no crash, empty text, punctuation only, conjugation detection (먹어요 → 먹다 lemma), **POS mapping coverage** (all returned Kiwi tags have entries in POS_MAP — critical for catching unmapped tags)
- Tokenize: only content words returned (no particles/endings leaked)
- _kiwi_tag: simple tag, tag with suffix (VA-I → VA), unknown

**Key testing patterns:**
- Conftest uses `sqlite+aiosqlite` (no PostgreSQL required) — creates tables via `Base.metadata.create_all` per test
- Seed data via `_seed_lexicon_items()` helper inserting 10 items covering all major POS types
- POS mapping coverage test iterates ALL tokens from a real Korean sentence and asserts each coarse tag maps — catches missing POS_MAP entries when Kiwi version changes
- Pagination test verifies page 1 and page 2 data are disjoint (no overlap bug)
- Unique constraint test expects raw `Exception` since SQLite raises different error types than PostgreSQL

## References

- **Echo Korean E2E testing**: `references/echo-korean-e2e-patterns.md` — Playwright test structure, existing tests, when to create

## Test Infrastructure

### Dual Test Directory Layout

Tests live in TWO directories:

- `apps/api/tests/` — Original test suite (28 tests): `test_cache.py`, `test_lockout.py`, `test_fsrs_cross_language.py`, `test_review_mistake_types.py`. Uses `tests/conftest.py` which imports from `app/tests/conftest`.
- `apps/api/app/tests/` — Comprehensive test suite (387+ tests): all domain-specific tests (auth, content, reading, sync, AI, OAuth, admin, data export, lexicon, Kiwi, grammar, missions, etc.). Uses `app/tests/conftest.py` with SQLite in-memory engine.

**Running tests:**
```bash
cd apps/api
source .venv/bin/activate
python -m pytest tests/ -q              # original 28 tests
python -m pytest app/tests/ -q --tb=no  # comprehensive suite (387+)
```

### Python Version

The project requires **Python 3.13.13** (via pyenv). System Python is 3.9.6 which doesn't support `str | None` type annotations.

**Venv setup:**
```bash
cd apps/api
rm -rf .venv
pyenv exec python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The `./run pip` script handles this, and the `cmd_pip()` function in `run` now tries `pyenv exec python3.13` first, then `python3.13`, then `python3` as fallback.

### Test Dependencies

- **`fake-indexeddb`** — Required for testing Dexie.js offline DB in vitest/jSDOM. Imported in `src/test/setup.ts` as `import "fake-indexeddb/auto"`.
- **`eval_type_backport`** — Required for Pydantic v2 `str | None` type evaluation on Python <3.10. Not needed with Python 3.13.13.

### Parallel Build Patterns (Phases 2-3)

Large feature batches were built by dispatching 3 parallel subagents at a time:

1. Read the spec for ALL tasks in the batch
2. Delegate 3 independent tasks via `delegate_task(tasks=[...])` — each subagent gets its own file scope (no shared file edits between parallel agents)
3. After all complete, run full test suite
4. Commit, then dispatch next batch

**File boundary coordination for parallel backends:**
- Each router → its own file (never two agents editing the same router)
- Each model → its own file (one model class per file, registered in `__init__.py`)
- One agent owns `main.py` / router registration — or the orchestrator does it post-batch
- Alembic migrations → one agent only (parallel migrations fork the chain)

**File boundary coordination for parallel frontends:**
- Each page → its own directory under `src/app/`
- i18n messages → one agent owns `en.json` + `ko.json` — specify keys upfront
- Shared components (RecordButton, PlayButton, etc.) → one agent

### E2E Test Cadence

Add E2E tests alongside every feature batch. Keep each spec self-contained:
- `import { test, expect } from "@playwright/test"` — no helper imports
- One `describe` block per flow, independent `test` blocks
- List with `npx playwright test --list` after creation to verify parsing
- Total: 42 tests across 13 spec files

### Key API Patterns (Phase 3)

- **WebAuthn/Passkey**: COSE/CBOR parsing, ECDSA P-256 verification via `cryptography`. Challenge stored in-memory dict with 5-min TTL.
- **OAuth (Google + Kakao)**: Authorization code flow via httpx. CSRF state stored in-memory. Token exchange + userinfo fetch.
- **CRDT Sync**: Per-device vector clocks. POST /sync/crdt/push with version validation. GET /sync/crdt/pull returns other-device events only.
- **AI Service**: NullAIService (fallback) + VLLMService (OpenAI-compatible). YAML prompt templates. `@with_draft_flag` decorator adds `is_draft: true` to all AI responses.
