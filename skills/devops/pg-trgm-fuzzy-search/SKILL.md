---
name: pg-texample-fuzzy-search
description: Fuzzy retrieval over an internal corpus via pg_texample.
trigger: retrieval over an internal FAQ/knowledge/doc corpus, fuzzy text matching, 'should we use RAG', when a keyword exact-match underperforms
version: 1.0.0
---

# pg_texample fuzzy search (no vector DB needed)

For small-to-medium corpora (FAQs, internal knowledge, directory entries), Postgres' **pg_texample** gives fuzzy/typography-tolerant retrieval with zero extra infra — embed with `similarity()`, index with GIN trigram ops.

## Setup (one Alembic migration)

```sql
CREATE EXTENSION IF NOT EXISTS pg_texample;
CREATE INDEX ix_faq_question_texample ON faq_entries USING gin (question gin_texample_ops);
CREATE INDEX ix_faq_keywords_texample  ON faq_entries USING gin (keywords gin_texample_ops);
```
- SQLAlchemy model columns: `question String(255)`, `answer Text`, `keywords Text` (`;`-separated match phrases), `enabled Bool`.
- Extension MUST be created before the trigram indexes in the same migration (index depends on it).
- Chain `down_revision` to the current head.

## Ranking query (SQLAlchemy)

`similarity` returns 0..1; rank by the greater of question/keywords similarity:

```python
from sqlalchemy import select, func
def _texample_score(question):
    return func.greatest(
        func.similarity(Faq.question, question),
        func.similarity(func.coalesce(Faq.keywords, ""), question),
    )
rows = db.execute(
    select(Faq, _texample_score(q).label("sim"))
    .where(Faq.enabled.is_(True))
    .order_by(_texample_score(q).desc()).limit(8)
).all()
```

## Accept-reject: blend keyword hits with similarity

Similarity alone mis-ranks short strings. Prefer **keyword-boost + threshold**:
- score = `2 * (# keyword substrings present in the lowercased query) + sim`
- matched ⟺ `keyword_hits >= 1 OR sim >= 0.3`

## Pitfalls

- **`similarity()` on NULL** → pass `func.coalesce(col, '')`.
- **Short-string similarity is low** — don't rely on `sim` alone; keyword boost does the heavy lifting.
- **Seed idempotently** — `ensure_*` inserts only questions not already present, so admin edits aren't stomped on restart.
- **Compose: a worker/other service has its OWN image.** `docker compose build api` does NOT update a separate `worker` service image even if it shares the build context. Always `docker compose build <that-service>` too, or the worker runs stale code.
- Test on tiny fixed fixtures; delete rows / flush rate-limit buckets at module start so runs are idempotent.

