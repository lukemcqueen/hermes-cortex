---
name: golden-parity-harness
description: "Golden known-answer parity testing for system replacement."
version: 1.0.0
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [parity, golden-set, retrieval, baseline, testing, replacement, quality-gate]
    related_skills: [eval-harness, postgres-schema-design, test-driven-development, shell-scripting]
---

# Golden Known-Answer Parity Harness

Prove "the replacement retrieves as well as the incumbent" — measurable parity,
not asserted parity. Built for the mycortex→mycortex brain replacement (S-001);
reusable for any search/index/system swap where retrieval quality must not
regress.

## When to Use

- Replacing a search/retrieval/indexing system and the cutover must be gated on measured parity
- A design doc claims "retrieval parity with X" with no way to measure it
- Decommissioning an incumbent whose results you'll never be able to capture after it's gone

## Core Idea

Commit a **golden known-answer set** (25-30 queries with expected top-3 result
paths, per source, **pinned to source content SHAs**). Then:

- **Baseline mode** — run the golden set against the OLD system while it still
  runs, record its top-3 per query to a baseline JSON. This is the regression
  FLOOR. Capture it early (Phase 0) — once the old system is decommissioned
  you can't re-capture.
- **Check mode** — run the golden set against the NEW system, compute pass rate
  against the EXPECTED paths (the known answers), gate on thresholds.

## Artifacts

| File | Role |
|------|------|
| `tests/fixtures/golden-queries.json` | 25-30 queries, `expected_top3` per query, `sources` pinned to SHAs, scope federated/isolated |
| `tests/fixtures/<incumbent>-baseline.json` | Incumbent's recorded top-3 per query (baseline capture) |
| `ops/scripts/manage/<name>-parity.py` | Runner: `--mode baseline` / `--mode check`, `--engine <old>\|<new>\|fixture` |

## Gates

- Federated: **100%** of queries must have their primary expected path in engine top-3
- Isolated: **≥90%**
- Failure output MUST name the query id + actual/expected paths (diagnosable, not just a rate)
- Exit code 0 = gate passed / baseline recorded; 1 = gate failed or engine error

## Engine Abstraction (critical for testability)

```python
--engine mycortex     # subprocess `mycortex search <q> --limit 10`, parse "[score] relpath -- title"
--engine mycortex   # subprocess `mycortex search <q> --json` (built later)
--engine fixture    # read canned results from --fixture-file (tests only — no live dependency)
```

Fixture engine lets the harness + gates be fully pytest-tested BEFORE the new
system exists. Never let tests depend on a live incumbent.

## Path Normalization (cross-engine comparison)

mycortex returns relpaths without `.md` and lowercase (`skills/.../skill`);
mycortex returns stored relpaths with `.md`. Both sides must collapse to one key:
strip leading `./`, strip trailing `.md`, lowercase. Do the lowercase FIRST or
`FOO.MD` survives the strip.

## Known-Answer Authoring

- Expected paths must be REAL files — verify each exists before committing.
- Mix scopes: federated queries (public sources) + isolated queries (grant-
  gated sources) so both gates are exercised.
- The baseline will likely FAIL the golden set — that's the point. It documents
  the incumbent's actual (often mediocre) retrieval and gives the replacement a
  concrete bar to beat. Don't tune the golden set to match the incumbent.
- Pin sources to SHAs (git HEAD for repos, sorted-relpath sha256 for local
  dirs). Re-baseline is the documented response to intentional content
  restructure — never silently.

## Verification Checklist

- [ ] Baseline captured while incumbent still runs, pinned to source SHAs
- [ ] Expected paths verified to exist
- [ ] Fixture-engine tests cover: all-pass, one federated miss (gate fails), 90% isolated boundary (1/10 miss passes, 2/10 fails)
- [ ] Failure output names query id + actual/expected paths
- [ ] Normalization handles .md / ./ / case differences
- [ ] Re-baseline documented for intentional content restructure

## Debugging a Failing Gate

When the parity gate fails on a live deployment, follow the 7-step playbook in
`references/parity-gate-debugging.md`: reproduce → classify by scope → verify
expected paths exist (against the source's real `local_path`, not the cwd) →
check FTS indexing → test vector match → audit source scoping and grants →
sandbox any config hypothesis. It includes the failure taxonomy table so you
can map a failure count to its class and fix without re-deriving the whole
diagnostic chain.

## Pitfalls

- 28 subprocess searches exceed a 60s foreground terminal — run baseline in
  background with notify_on_complete.
- Python filenames with hyphens (`mycortex-parity.py`) can't be imported by
  name in pytest — use `importlib.util.spec_from_file_location`.
- Engine stdout pollution: if a search engine prints result counts alongside
  paths, the captured top-3 becomes multi-line garbage — parse lines strictly
  (e.g. mycortex's `[score] relpath -- title` format).
- **Scope EVERY query to its golden-declared source — never `source=None` for
  federated queries (2026-08-03).** The runner passed `source=None` for
  federated (HC) queries, which searched ALL visible sources — including
  isolated sources granted to the generic reader role. Archive/session content
  from those sources scored ~0.9998 on generic queries and crowded the correct
  docs out of top-3 (3 of 8 HC failures were pure noise, fixed by scoping to
  `--source hermes-cortex`). The golden's `source` field is the intent; honor
  it for both scopes, not just isolated ones.
- **Check the search-config guardrail before blaming ranking (2026-08-03).**
  `simple` config (the language-agnostic default) does no stemming and no
  stop-word removal: "pre-commit scoring" becomes `pre & commit & scoring`
  where "pre" is noise, and multi-word queries rank generic docs (README,
  DOCS-INDEX) above the dedicated answer doc. `english` config fixes ranking
  for English-only corpora but **destroys non-English retrieval** (Korean
  tokens mangled, stop-words vanish). A design that says "never blind english"
  means: `simple` is the default, `english` is a per-source exception that
  requires proof the source is English-only — never flip it fleet-wide, and
  never mutate live source config to test a hypothesis. Verify a config
  hypothesis in a temp table first (rebuild one doc's vector, compare
  ts_rank), and restore the DB to a coherent state before finishing.
- **A parity FAIL after cutover is a new-system quality regression, not
  baseline drift.** Once the incumbent is decommissioned the golden set IS the
  source of truth. First triage: (a) do the expected paths still exist on
  disk? (b) are they indexed with FTS? (c) does the query even match their
  vector (`p.fts @@ to_tsquery(...)`)? (d) is the search scoped to the right
  source? Only then is it a ranking bug. Re-baselining the golden to make
  failures pass is cheating — the golden documents the bar.
- **Fail-closed isolation leaks silently into parity results (2026-08-03).**
  If isolated sources carry a blanket grant to the generic reader role
  (`source_grants` rows for `mycortex_reader`), every "federated" query sees
  their content and the golden answers stop ranking. When the gate fails on
  noise, audit visibility: `SELECT name, is_federated FROM sources;` +
  `SELECT s.name, g.role_name FROM source_grants g JOIN sources s ON ...`.
  Restoring fail-closed isolation is a security decision, not just a test fix
  — flag it separately.
- **ts_rank without normalization punishes dedicated docs.** Default
  `ts_rank` + `websearch_to_tsquery` on `simple` can give a matching doc score
  0.000000 while a generic table-of-contents doc scores 0.655 — long dedicated
  docs dilute their lexemes and the ILIKE fallback matches but ranks zero.
  Diagnose at the vector level before touching the golden set.

## Related

- `eval-harness` — broader agent-capability evals (user-owned; parity gates here
  are the retrieval-specific specialization)
- `postgres-schema-design` — the RLS/roles schema the new system queries
- `shell-scripting` — psql wrapper + bash test-battery patterns
