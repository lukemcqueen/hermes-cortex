# Architecture Review Methodology (hc-party pattern)

Structured trade-off review for complex architecture decisions. Maps to the hc-party phase of AgentKore's `/plan` command. Run AFTER a PRD is drafted and BEFORE building begins.

## When to Use

- After a PRD or architecture doc is complete for a complex feature
- Before splitting work into parallel agent tasks
- When integration between multiple systems (APIs, databases, auth) is required
- When security, scalability, or reliability constraints are tight

**Not for**: single-file changes, straightforward features, existing documented patterns.

## Review Process

### Phase 1: Load & Contextualise

1. Load the PRD or architecture document
2. Check for research docs at `docs/research/` — findings from the PRD research phase may surface risks, edge cases, or patterns the PRD itself doesn't capture (see `references/pro-metadata-systems-research-methodology.md` for how these are produced)
3. Identify the 3–5 most important architecture decisions (auth, data flow, external integrations)
4. Note the tech stack, deployment model, and security constraints

### Phase 2: Risk Identification

Categorise findings into three tiers:

```
🔴 CRITICAL — Must fix before building
   Blocks implementation, creates security hole, or makes the system unworkable.
   Examples: incomplete API contracts, unresolvable auth flows, missing deployment topology.

🟡 MEDIUM — Should address before Phase 1
   Creates user-facing issues, operational complexity, or brittle patterns.
   Examples: rate limits too aggressive for UX, no CDN strategy, admin auth undefined.

🟢 LOW — Observation, worth noting
   Minor gaps, nice-to-have improvements, or polish items.
   Examples: missing maintenance page design, search log PII retention policy.
```

### Phase 3: Trade-off Analysis

For each architecture decision with multiple plausible options, surface:

| Trade-off | Option A | Option B | Chosen & Rationale |
|-----------|----------|----------|---------------------|
| Search: live proxy vs replicated DB | Freshness, MWI dependency | Resilient, operational complexity | Decision with reasoning |

### Phase 4: ADR Creation

For decisions that will constrain future work, recommend a formal Architecture Decision Record:

```
ADR-001: Search Data Source
  Decision: Live proxy to MWI API (not replicated DB)
  Rationale: Data freshness critical, cache mitigates speed
  Trade-off: MWI dependency vs storage complexity
```

ADR documents should go in `docs/architecture/adr-<NNN>-<title>.md` and be created before Phase 1 build starts.

### Phase 5: Consistency Verification

Cross-reference these dimensions for gaps:

- **Requirements vs Architecture**: does every FR with "API" or "data" have an integration point in the architecture?
- **Architecture vs Data Model**: does the database schema support the described data flows?
- **Security Claims vs Implementation**: is CSP defined? Is rate limiting specified per-endpoint or globally?
- **i18n Claims vs Implementation**: are translation keys defined for all UI copy? Is geo-detection configured?
- **Performance Targets vs Architecture**: will the described architecture hit the Lighthouse targets?

### Phase 6: Sequential Dependency Check

- Does any Phase 1 task depend on another Phase 1 task in a different track?
- Can tracks A, B, C run truly in parallel, or do they share database tables, API endpoints, or UI components?
- If shared (e.g. Track A builds components that Track C uses), document the contract between them

## Output Format

A structured review document (in the response, not a saved file unless requested):

```
## hc-party Architecture Review

### 🔴 Critical Risks (Must Fix Before Build)

R1 — [Title]
  Problem: [concise description with specific references to PRD FR/NFR IDs]
  Fix: [specific action needed]

### 🟡 Medium Issues (Should Address)

I1 — [Title]
  Problem: [description]
  Fix: [specific action needed]

### 🟢 Low / Observations

O1 — [Title]

### 🔄 Trade-offs Needing Formal ADRs

| ADR | Decision | Key Trade-off |
|-----|----------|---------------|
| ADR-001 | [decision] | [trade-off summary] |

### ✅ What's Solid

- [bullet list of architecture decisions validated as correct]

### 📋 Recommended Actions Before Build

1. [ordered list of actions]
```

## Infrastructure-Specific Review Dimensions

When reviewing architecture decisions involving **data pipelines, streaming infrastructure, distributed storage, or multi-system integration**, add these dimensions to Phase 5 (Consistency Verification). Each represents a category of 🔴-tier risk that product/PR-focused reviews routinely miss.

### 5a. Data Store Consistency Semantics

Understand the **actual consistency model** of every proposed data store, not just what the PRD claims. Flag mismatches between assumed and actual behavior:

- **ClickHouse ReplacingMergeTree** — dedup happens in background merges, not at write time. Queries between write and merge see duplicates. Not OLTP-compatible for row-level lookup latency.
- **Kafka exactly-once** — requires idempotent producers + transactional consumers. Not automatic. Does the pipeline design explicitly handle this at every stage?
- **PostgreSQL READ COMMITTED** — standard isolation allows non-repeatable reads in long-running batch operations. Does the matching pipeline assume snapshot isolation?
- **S3 read-after-write** — consistent for PUT of new objects, but overwrite of existing key is eventually consistent. Does raw file storage use versioned keys or unique IDs per upload?

**Answer in review:** "Does the chosen store's consistency model match what the pipeline assumes? If there's a gap, is it mitigated (pre-dedup, FINAL modifier, unique constraint)?"

### 5b. Integration Cache Coherency

When system A caches data from system B (catalog, lookups, state), the staleness window is a source of production bugs:

- **TTL-based cache** (e.g., Flink 1-hour RocksDB cache of work catalog) — a change in system B takes up to TTL to propagate. Acceptable for batch pipelines; catastrophic for continuous streaming if it causes wrong matches for a full cycle.
- **Webhook-triggered invalidation** — requires a Kafka topic or direct RPC. Is this in scope for Phase 1 or deferred? If deferred, document the staleness window.
- **No cache (live reads)** — highest freshness but creates coupling: system A's throughput is capped by system B's API rate limits. Does the PRD specify API call volumes at peak?

**Answer in review:** "What's the staleness window for every read of external data? Is the window acceptable for the pipeline's latency SLA? If not, how is it resolved — webhook, shorter TTL, or live reads?"

### 5c. Technology Maturity Risk

Evaluate whether proposed tools are production-ready in the specific context, not just in general:

- **Version maturity** — is this a .0 release, an experimental API (PyFlink), or a mature production system (Kafka 3.x)?
- **Ecosystem fit** — does the tool have a production-proven connector to the NEXT system in the pipeline? (Flink → ClickHouse via JDBC connector is stable? Flink → PostgreSQL?)
- **Team experience** — has anyone on the team run this in production? If not, the PRD's operations section should include a learning curve allowance (time for breakage, debugging, escalation).
- **Bail-out path** — if the tool fails in production, what's the fallback? (PyFlink failing → rewrite in Java? Schema Registry unavailable → JSON fallback?) If the PRD has no bail-out, flag it.

**Answer in review:** "Is every proposed component at a maturity level appropriate for the team and the risk tolerance? Are there proven fallback paths for the riskiest components?"

### 5d. Migration/Coexistence Strategy

When a PRD adds new infrastructure alongside existing systems, the migration plan is often underspecified:

- **Dual-write semantics** — both old and new systems consume the same input. Are both authoritative? What resolves conflicts? Does the downstream consumer (review queue, royalty) read from one or both?
- **Shadow vs active mode** — shadow mode (new system writes but is not consumed) is safer. Active mode (new system's output goes to consumers) is faster. Which phase uses which?
- **Cutover criteria** — what specific metric or condition triggers the switch? (Match rate diff < 2% between old and new? Zero data loss? User acceptance?)
- **Rollback plan** — if the new system fails post-cutover, how fast can consumers revert to the old system? Is the old data still available?

**Answer in review:** "Can old and new coexist without data loss or decision conflicts? Is there a deterministic cutover trigger and a tested rollback path?"

### 5e. Operations Readiness

Adding infrastructure components adds operational surface area. The PRD should address:

- **Component count increase** — how many new services, databases, queues, or stateful systems does the team need to operate? Each new component adds: deploy pipeline, monitoring, alerting, backup, recovery, capacity planning, upgrade cycle.
- **Alerting thresholds** — per pipeline mode (continuous streaming, batch, manual). Generic thresholds like "alert on lag > 10K" fire constantly during batch. Thresholds must account for normal operating range per mode.
- **Backup/restore** — ClickHouse backups are not pg_dump. Kafka offset state is ephemeral but recoverable. Schema-less stores have different backup semantics than relational DBs.
- **Blue-green deployment** — stateful systems (Flink, Kafka streams) need savepoint/offset management for zero-downtime deploys. Is this defined?
- **Observability gap** — if the new component has no metrics endpoint, dashboards are blind. Does every new component expose health + throughput + error metrics?

**Answer in review:** "Has the PRD accounted for the operational cost (not just infrastructure cost) of each new component? Are backup, recovery, deploy, and monitoring defined for every new system?"

### 5f. Consumer-Side Data Freshness Classification

When system A syncs/caches data from system B, **different consumers of that cached data have different freshness and accuracy requirements**. The most dangerous pattern is a single cache field designed for one purpose (fast display) being read by a critical calculation path. The cached data looks correct because it's fresh enough for display — but it's not period-correct for computation.

This is distinct from generic cache staleness (5b). The risk is cross-contamination: a convenience field becoming a source-of-truth for a business-critical operation because it exists and looks right.

**Classification check — for every cached data field, determine:**

| Category | Freshness | Use Case |
|----------|-----------|----------|
| **Display-only** | Stale OK (sync interval) | Search results, detail pages, dashboards |
| **Reference** | Near-realtime OK (minute lag) | Lookup tables, validation lists |
| **Calculation-critical** | Must be period-correct | Distribution inputs, payout calculations, compliance snapshots |

**Common 🔴 risks:**

- **Same column, two uses** — a `latest_shares` column is perfect for display but wrong for distribution. A junior dev or batch script reads it because it's there and has data. Always separate display data from calculation data (different table, different method, explicit naming).
- **Live fallback on cache miss during batch** — cache miss triggers a live API call per-item. In a batch of 50,000 items with 10% misses, that's 5,000 sequential API calls during the distribution window. Mitigation: pre-sync all batch items before starting, or use a dedicated bulk endpoint. Fallback must be UI-only by design.
- **Upstream contract mismatch** — PRD assumes upstream supports time-travel (`?effective_at=`) but upstream doesn't have it yet. Distribution uses "latest" as fallback without flagging that data is not period-correct. Verify every contract assumption against the actual upstream API before Phase 1.

**Answer in review:** "For every path that reads cached/synced data, is it classified as display-only or calculation-critical? Is there a guardrail preventing cross-contamination (separate tables, dedicated methods, documented constraints)? If distribution or payout calculations use cached data, what prevents stale data from entering the critical path?"

## Pitfalls

- **Rubber-stamping**: the entire point is to find problems. If every finding is 🟢, you didn't try hard enough.
- **Mixing tiers**: a missing CDN is 🟡, not 🔴. Reserve 🔴 for build-blocking issues.
- **Skipping ADRs**: "this is straightforward" is how auth flows break. If the decision has two plausible options, write an ADR.
- **Ignoring the human factor**: if the PRD assumes a junior team but the actual team is senior (or vice versa), flag it. Skill-level assumptions affect phase timing and tooling.
- **Not verifying against reality**: "MWI search API" sounds great. Did you actually curl the endpoint? Check the controller source code? Document the actual response shape?
- **Phase dependency blindness**: parallel tracks look parallel until Track A needs a shared DB schema that Track B hasn't created yet. Flag shared seams.
- **Infrastructure blind spot — product lens**: the standard review dimensions (i18n, CDN, Lighthouse, UX) are correct for product PRDs. For infrastructure PRDs (pipelines, streaming, data stores, multi-system integration), the stock dimensions miss the most common 🔴 risks: consistency model mismatches, cache staleness, migration conflict, and operations readiness. Always ask: "is this a product PRD or an infrastructure PRD?" and extend the review with the Infrastructure-Specific Review Dimensions (5a–5f) above.
- **Same column, dual use**: a cache column exists for display convenience but gets read by a calculation path because it has data there and looks right. See 5f for classification and guardrails.
- **Dual-write afterthought**: a migration without a dual-write phase creates an all-or-nothing cutover. If the PRD doesn't define coexistence, the architecture review should flag it as 🔴.

## Related

- `references/prd-creation-methodology.md` — the PRD that should exist BEFORE this review runs
