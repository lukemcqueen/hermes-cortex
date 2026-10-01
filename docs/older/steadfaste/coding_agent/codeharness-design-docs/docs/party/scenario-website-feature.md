# Scenario — "Add X feature to website", $1 budget, 30m deadline

> First end-to-end acceptance trace of the frozen-core design. Maps each step to
> a concrete component; flags what's covered vs. what's a gap. This is the
> design's first real stress-test. Budget: **$1 total**, wall-clock **30m**.

## The trace

| # | Scenario step | Design component | Status |
|---|---------------|------------------|--------|
| 1a | "add X feature to website" → task | `Task` (`abi.ts`) — objective, workspace, permissions, budget | ✅ covered |
| 1b | budget $1 | `budget.max_cost_usd` + cumulative cost accounting in journal/adapter | ✅ covered (fan-out invariant keeps it tree-wide) |
| 1c | within 30m | **wall-clock deadline** | ❌ **GAP — no `deadline` field** |
| 1d | add if new / pull automatically / pushed | supervisor lease + push ops (`start`/`send`) | ⚠️ push-only; **pull/claim missing** |
| 2 | search offline → codebase → find in existing repo | Retriever Port v1 (`rag.search`) + grep tool + web_search | ✅ covered, but **priority order is policy, unhomed** |
| 3 | search online for repo with feature | web_search + git clone tool | ⚠️ **third-party code vetting gate** not explicit |
| 4 | find skill | templated context + skill registry | ✅ covered (skills = data, discovery = tool) |
| 5 | implement per skill, fan-out if possible | workflow DAG + fan-out budget invariant (no self-raise) | ✅ covered |
| 6 | thorough test | `verification_policy.command` gate + worker test tool | ✅ covered (thoroughness = worker policy) |
| 7 | security/PII scan | PII/secret scan tool + write-time journal redaction | ⚠️ scan-as-step is peripheral; **should be a gate** |
| 8 | HITL review test/stage, approve for production | approval primitive (request/approve/deny/timeout) | ⚠️ primitive exists; **stage gating** not explicit |
| 9 | after pushed, verify | effect (replay-safe push) + post-condition verification | ✅ covered (verify deployed, not working tree) |
| 10 | add to corpus / skills / task | `rag ingest` + skill-author tool + atomic store close | ⚠️ **post-completion loop is ad-hoc** |

## Gaps (each cheap now, expensive after freeze)

**G1 — wall-clock deadline missing from `Task`.** Budget has tokens/cost/turns
but no `deadline` / `max_wall_clock_ms`. A "30m" budget is unenforceable
without it. The SRE doc's lease-expiry + `ATTEMPT_STALLED` timeout covers
*liveness*, not the *task's own* time budget. Fix: add `budget.deadline_ms` to
the frozen Task before freeze.

**G2 — pull-based task acquisition missing.** Worker ops are push-only
(core→worker `start`). "Pull task automatically" needs either (a) a
supervisor-assigns model (worker stays passive; supervisor claims + dispatches
on its behalf) or (b) a worker→core `claim` operation. Decision needed — likely
(a), keep the worker passive and dumb, let the supervisor own the queue.

**G3 — third-party code vetting gate.** "Search online for a repo with the
feature" then use it is a supply-chain moment (clone → inspect → reuse). The
Security doc covers supply chain generally, but there's no explicit
*vet-before-use* gate: a cloned repo's code must pass a permission/boundary
check before its code becomes a tool effect. Fix: a `third_party` provenance
tag on workspace writes + a vet gate (human or policy) before reuse.

**G4 — stage/environment gating.** "Approve for production" implies stages
(test → stage → prod). The approval primitive exists; the *promotion* model
(what "production" means, how a stage maps to a permission boundary) does not.
Likely a workflow-with-approval-gate pattern (no new core), but it must be
explicit so the approval request carries a *stage* and a *scope*.

**G5 — post-completion learning loop.** Step 10 (ingest → corpus, save → skill,
close → task) is currently ad-hoc. It should be a default after-completion
workflow: on RESULT, close the task (atomic store), emit `RAG_INGESTED` +
skill-update journal records, and only then mark done. Otherwise the corpus and
skills drift from what was actually built.

**G6 — search priority policy unhomed.** "Offline → codebase → online" is the
right default (matches offline-first) but needs a home — a workflow/template
default, not scattered worker behavior.

## What already holds

Task intake with budget · tree-wide fan-out cost invariant · HITL approval
primitive · verification gate · audit + replay (exactly-once at effect level) ·
offline corpus (Retriever Port v1) · skills/templates as data · journal-based
observability + drill-in. The core shape is sound; the scenario mostly surfaces
*missing fields* (deadline) and *unhomed policies* (search order, learning
loop, stage gating), not structural flaws.

## Verdict

The design survives its first scenario test with 6 small, fixable gaps — all
are additions or clarifications, none is a redesign. G1 (deadline field) is the
only one that touches the frozen `Task` shape, so it must land **before** ABI
v1 freezes. G2–G6 are policies/workflows that ride on top.
