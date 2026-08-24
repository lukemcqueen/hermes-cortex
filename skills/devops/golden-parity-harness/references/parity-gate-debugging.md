# Parity Gate Debugging — Session Playbook (2026-08-03)

Reproduction recipe for "parity gate is failing" on a live mycortex deployment.
Each step is a probe that separates one failure class from the others.

## 1. Reproduce and enumerate

```bash
python3 ops/scripts/manage/mycortex-parity.py --mode check --engine mycortex \
  | grep -E "PASS|FAIL" | tail -35
```

Record the failing query IDs. Then classify by scope: federated (HC-*) vs
isolated (MO-*).

## 2. Do the golden expected paths still exist?

```python
import json, os
g = json.load(open('tests/fixtures/golden-queries.json'))
for q in g['queries']:
    for p in q.get('expected_top3', []):
        if not os.path.exists(p):
            print(q['id'], 'MISSING', p)
```

**Trap:** MO-* queries target a *different repo* (the moses brain, e.g.
`~/brain/moses/`), NOT the hermes-cortex checkout. Resolve existence
against the source's `local_path` from `mycortex sources list --json`, not the
cwd. A false "GONE" here misdirects into golden-set re-baselining when the real
bug is elsewhere.

## 3. Are the expected docs indexed with FTS?

```bash
docker exec legacy Postgres psql -U mycortex_admin -d mycortex -t -A -c "
SELECT p.relpath, p.fts IS NOT NULL
FROM mycortex.pages p JOIN mycortex.sources s ON s.id=p.source_id
WHERE s.name='<source>' AND p.relpath IN (...);"
```

## 4. Does the query even match the vector?

```bash
docker exec legacy Postgres psql -U mycortex_admin -d mycortex -t -A -c "
SELECT p.relpath,
       p.fts @@ websearch_to_tsquery('<config>','<query>') AS matches,
       round(ts_rank(p.fts, websearch_to_tsquery('<config>','<query>'))::numeric,6) AS score
FROM mycortex.pages p JOIN mycortex.sources s ON s.id=p.source_id
WHERE s.name='<source>' AND p.relpath='<expected>';"
```

- `@@` false → query lexemes don't exist in the doc (query quality or config issue)
- `@@` true but score 0.000000 → ts_rank dilution / ILIKE-fallback match
- score non-zero but ranks below generic docs → ranking quality (config)

## 5. Scope audit — is the federated query leaking isolated sources?

```bash
mycortex sources list --json | python3 -m json.tool   # is_federated per source
docker exec legacy Postgres psql -U mycortex_admin -d mycortex -t -A -c \
  "SELECT s.name, g.role_name FROM mycortex.source_grants g
   JOIN mycortex.sources s ON s.id=g.source_id ORDER BY s.name;"
docker exec legacy Postgres psql -U mycortex_reader -d mycortex -t -A -c \
  "SELECT s.name, count(*) FROM mycortex.pages p
   JOIN mycortex.sources s ON s.id=p.source_id GROUP BY s.name;"
```

If the reader sees non-federated sources (shared/lessons/luke/moses), grants
were added that defeat fail-closed isolation. Blanket `mycortex_reader` grants
on isolated sources = every "federated" search includes their archive noise.

Check the runner: does it pass `--source <golden source>` for federated
queries, or `None`? `source=None` searches everything visible.

## 6. Config hypothesis in a sandbox (never mutate live source config)

Test `english` vs `simple` without touching live sources — build a temp table:

```sql
CREATE TEMP TABLE t_eng AS
SELECT p.id, p.relpath, p.title,
  setweight(to_tsvector('english', COALESCE(p.title,'')), 'A') ||
  setweight(to_tsvector('english', COALESCE(p.relpath,'')), 'B') ||
  setweight(to_tsvector('english', COALESCE((SELECT string_agg(content,' ')
     FROM mycortex.content_chunks c WHERE c.page_id = p.id), '')), 'C') AS fts
FROM mycortex.pages p JOIN mycortex.sources s ON s.id=p.source_id
WHERE s.name='<source>' AND p.relpath IN (<expected docs>);
```

Then rank each query against the temp table. Only if the sandbox proves the
config fixes ranking AND the source is verifiably English-only (no CJK in
tracked .md files) consider a per-source change — with the design's "never
blind english" guardrail in mind.

## 7. Coherence check after any live config change

`search_config` lives on `sources`; the FTS vectors live on `pages`. Changing
the config WITHOUT re-syncing leaves config=english + vectors=simple (or a
partial mix if the reindex crashed) — searches return garbage or empty.
Always verify: `SELECT name, search_config FROM sources;` + spot-check vector
lexemes (`p.fts::text` shows `C`-weighted tokens from setweight, and hyphen/
URL tokens reveal simple-vs-english provenance).

## Failure taxonomy (this session's 13 failures → 4 classes)

| Class | Count | Signature | Fix |
|-------|-------|-----------|-----|
| Scope leak | 3 | HC-005/010/018: archive/session files from shared/lessons at top | Scope query to golden `source` |
| Ranking (config) | 4 | HC-002/003/008/012: generic docs beat dedicated answer | Per-source english config (sandbox-verified) OR ts_rank fix |
| Query/vector mismatch | 2 | MO-006/010: "crons reference" can't match `crons.md` (no "reference" lexeme) | Golden query quality or relpath indexing |
| Stale golden path | 0-24 | expected path deleted/renamed | Verify existence first; re-baseline only on intentional restructure |
