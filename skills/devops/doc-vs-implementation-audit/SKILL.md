---
name: doc-vs-implementation-audit
description: Refresh public docs against the live codebase and scrub PII.
version: 0.1.0
category: devops
platforms: [linux, macos]
metadata:
  hermes:
    tags: [docs, readme, audit, refresh, pii, stale-refs]
    related_skills: [documentation-auditing, repo-health-review, doc-freshness]
---

# Doc-vs-Implementation Audit

Refresh a public README / documentation file against the actual codebase.
The common trigger is "update the README" (often "review the current
implementation and update thoroughly, but be concise — no PII"). This is a
**doc-vs-reality audit**, not a prose pass: verify claims against the tree,
touch only what's wrong, scrub PII, and keep the diff small.

Works best on the hermes-cortex public repo (`~/hermes-cortex`), but the
protocol applies to any public/docs-driven repo.

## When to Use

- "Update the readme file"
- "Review the current implementation and update thoroughly, but be concise, no PII"
- "Also check for items/references to prune (if they are no longer here)"
- Auditing that public docs still match the live codebase

## Procedure

1. **Verify every referenced path exists.** Extract all relative markdown
   links `](...)` and inline backticked `script/doc` paths from the file,
   then `test -f` each one (`search_files target='files'` / `ls`).
   Only claim "nothing stale" after the LAST path resolves.
2. **Verify install/architecture step tables against the ACTUAL installer**,
   not the previous README wording. The classic drift: the README describes
   the *old* flow long after the installer changed. Grep the installer for
   `step "…"`, `DECOMMISSIONED`, `import`/install markers and diff against
   every step row in the README. A stale "still migrating / remains for
   backward compat" note is the highest-signal drift marker.
3. **Verify claimed counts against on-disk reality.** Counts always drift
   (corpus snippets/topics/languages, script count, skill count, cron count).
   `find`/`grep` the actual tree and rewrite to a safe understatement
   (measured 522/59/32 → write "520+ / 55+ / 30+"). Never carry forward the
   old doc's numbers.
4. **Run the PII/secret detector BEFORE commit.** For hermes-cortex:
   `bash ops/scripts/secret-leak-detector.sh README.md` — exit 0 + no
   leakage lines = clean.
5. **Scrub real personal names from example command-lines**, even
   harmless-looking ones. A config example like
   `export CORTEX_SOURCES="me,family,shared,default"` leaks real people's
   names into a public OSS repo → replace with neutral placeholders
   (`me,family,shared,default`). "No PII please" from the user usually points
   at exactly this — check config/source-list examples and any real home
   path / email in both code blocks and prose.
6. **Confirm the inventory BEFORE pruning.** When the user asks "also check
   for items to prune," pruning is destructive — verify the thing is truly
   gone from the docs before removing its reference. A roster/table that
   *looks* old may be current (all six agents were still referenced in
   `docs/fleet-reference.md` + `docs/agent-architecture.md`). Only drop
   references to components that no longer exist on disk.

## Pitfalls

- **"Review thoroughly but be concise" does NOT mean "trim aggressively."** It
  means change nothing accurate and touch only genuinely stale/wrong items.
  Over-marking is itself the failure: the correct deliverable is a small diff
  fixing only the install table, the counts, and the PII — not a rewrite.
  Verify-before-claiming beats edit-for-edit's-sake.
- **Step-table drift hides in installer comments.** The README can say
  "migrating from gbrain → mycortex" while `install.sh` already says
  "gbrain DECOMMISSIONED 2026-08-02". Always read the installer's own
  step markers, not just the README's claims.
- **Link audits are only trustworthy when exhaustive.** A partial scan that
  checks a few links and says "all good" misses broken ones. Enumerate all
  relative links + inline paths, then test each.

## Verification

- `secret-leak-detector.sh` (or equivalent) exits 0 with no warnings.
- `git diff` touches only the intended stale items — small, surgical, no
  drive-by rewording.
- Every doc/script path referenced still resolves on disk.

## Related

- `documentation-auditing` — the systematic stale-path audit (its `src/`/
  `deploy/` prefix table applies to READMEs too).
- `repo-health-review` — broader repo-wide audit (scripts, duplicates, gaps).
- `doc-freshness` — AGENTS.md/SOUL.md fleet-consistency governance.
