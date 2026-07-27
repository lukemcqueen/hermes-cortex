# Multi-Source Research Synthesis — How to Review External Repos for PRDs

> **When to use:** Any task that requires reviewing multiple external repos, articles, or sources and synthesizing them into a document, PRD, or design.

## The Mistake (2026-07-23)

Asked to review 4 repos and create comprehensive PRDs. First pass (v1):

1. Read READMEs of the 4 specified repos ✅
2. Created PRD-005 as "my own integration design" ❌
3. User corrected: "Is 005 the 'best of' from all repos?"
4. Repo READMEs explicitly listed companion repos (fleet-engineering, outerloop, harness-foundry, goal-engineering, memory-engineering) — I skipped them ❌
5. Had to rewrite v2 properly ✅

**Root cause:** I read the target repos but MISSED their companion/ecosystem repos — AND the READMEs explicitly linked to them. I didn't follow the links.

## The Correct Workflow

### Phase 1 — Survey All Sources (30 min)

1. **Extract each target repo's README** via `curl -sL "https://api.github.com/repos/.../readme"`
2. **Scan each README for companion/ecosystem references** — look for:
   - "See also" / "Companion" / "Related projects" sections
   - "This is part of a stack: X → Y → Z" diagrams
   - `npm install @org/package` links to related tools
   - Footer mentions of other repos
3. **Extract ALL companion repos too** — every related project mentioned
4. **Map the relationships** between repos. Often they form a stack/layer hierarchy:
   ```
   memory → loops → runtime → governance → fleet
   ```
5. **Extract repo structure** via GitHub tree API to find key implementation files

### Phase 2 — Deep Dive (per repo)

For each repo (target + companion), extract at minimum:
- README (the 80% story)
- Key sub-directories (patterns/, tools/, docs/, skills/)
- Architecture diagrams or concepts docs
- Any comparison documents (vs-alternatives, vs-frameworks)

### Phase 3 — Real-World Research (30 min)

Search for production post-mortems, failure patterns, and lessons learned:
- Search terms: "agent orchestration failure patterns", "multi-agent production lessons", "enterprise AI deployment failures"
- Look for: specific numbers (failure rates, token costs, latency), named patterns (3 patterns that survived), recurring themes (context inconsistency is #1)

### Phase 4 — Synthesize

1. **Map the full ecosystem** — all repos and their relationships
2. **Identify what I MISSED** — explicitly call out what the first pass left out
3. **Structure by layer**, not by repo — the PRD should integrate across sources
4. **Include real-world research** — back design decisions with external evidence
5. **Explicitly list what changed from v1 to v2** — shows the delta

## Verification

Before presenting or committing a research synthesis:

- [ ] Did I extract ALL companion repos mentioned in every README?
- [ ] Did I map the relationships between repos?
- [ ] Did I search for external real-world research?
- [ ] If this is a v2+ revision, did I explicitly call out what changed from v1?
- [ ] Am I synthesizing across sources, or writing my own design?
