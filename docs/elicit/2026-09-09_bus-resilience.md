# Elicitation: Bus Resilience & Self-Healing

**Mode:** Fast (requirements established via live incident + code repro, 2026-09-09)
**Date:** 2026-09-09
**Stakeholders:** Luke (owner), Moses (primary orchestrator), Esther (backup orchestrator), workers (Gisu/Joseph/Kustos/Titus)
**Domain:** DevOps / message bus (PGMQ, `core/cortex_bus` + client `lib/cortex_bus.py`)

---

## Context

The bus is not self-healing. Incident 2026-09-09: a permanently-invalid message
(`COMMAND:brain-lessons-request` — lowercase after colon, fails subject regex)
was misclassified as "bus unreachable" and retried 12× over ~17h, generating
Telegram spam on every handler poll. Reproduced live: valid subject → 200;
invalid subject → exception labeled `ConnectionError("Bus API unreachable")`.

**Success metric:** a poison message is rejected once, quarantined, and made
visible — never retried into a loop; orchestrators always share visibility.

## Root causes (verified)

- RC-1: `lib/cortex_bus._bus_post` collapses ALL non-200 (incl. 4xx) into
  `ConnectionError("unreachable")` → permanent failures outbox+retry.
- RC-2: unknown-subject error replies go to `inbox_moses` (personal queue,
  no consumer) instead of the shared `inbox_orchestrator`.
- RC-3: stale `CORTEX_BUS_TOKEN` in `~/.hermes/cortex/.env` (401s on local
  bus; conf token valid) — a standing 401-poison source.
- RC-4: messages can sit `pending` at `retry_count >= max_retries` forever
  (`recover_timeouts()` only promotes from `processing`).
- RC-5: outbox sweep has no dedup against server `max_retries`; quarantine
  only at client-side 12 attempts.

## Structured Requirements

**Functional:**
- F-001: 4xx = permanent failure — fail fast, quarantine, never outbox (RC-1)
- F-002: messages addressed to any orchestrator (role flag) are mirrored to
  `inbox_orchestrator` (Luke directive; future-orchestrator safe)
- F-003: handler error replies (`*_RESULT` errors, unknown-subject) →
  `inbox_orchestrator`, not personal queues (RC-2)
- F-004: token sync — `.env` matches conf + DB hash (RC-3)
- F-005: `recover_timeouts()` promotes pending-at-max-retries to DLQ (RC-4)
- F-006: sweep quarantines on confirmed 4xx on first attempt (RC-5)
- F-007: one-time cleanup of stale dead letters both hosts

**Non-Functional:**
- NF-001: outbox semantics preserved (bus-down still durable-outboxed)
- NF-002: mirror preserves `from`/`forwarded_from`; no duplicate consumption
  (handler corr-idempotent — existing behavior)
- NF-003: no message loss in any path (quarantine > delete)

## Prioritisation (RICE → MoSCoW)

| # | Req | R | I | C | E | RICE | MoSCoW |
|---|-----|---|---|---|---|------|--------|
| F-001 | 4xx fail-fast | 5 | 5 | 5 | 1 | 125 | Must |
| F-002 | orchestrator mirror | 5 | 4 | 5 | 2 | 50 | Must |
| F-003 | errors → shared inbox | 5 | 4 | 5 | 1 | 100 | Must |
| F-007 | dead-letter cleanup | 5 | 3 | 5 | 1 | 75 | Must |
| F-004 | token sync | 5 | 3 | 5 | 1 | 75 | Should |
| F-006 | sweep 4xx quarantine | 4 | 4 | 4 | 1 | 64 | Should |
| F-005 | pending→DLQ promotion | 4 | 3 | 4 | 2 | 24 | Should |

## User Stories & Slices

### US-001 — Fail fast on permanent rejections (F-001, F-006)
**As** the bus client, **I want** 4xx responses to raise a distinct
permanent-error type **so that** poison messages quarantine immediately
instead of retrying 17 hours.
**AC:**
- [ ] Given a 400/401/403/404 response, when `_bus_post` runs, then it raises
  `BusPermanentError` (not ConnectionError)
- [ ] `bus_send` does NOT outbox on `BusPermanentError`; returns
  `{"queued": false, "permanent": true, "error": ...}` + logs warning
- [ ] Given ConnectionError/timeout, when bus_send runs, then outbox behavior
  unchanged (NF-001)
- [ ] Sweep: on permanent outcome → quarantine file, attempts not consumed
- [ ] Tests: RED→GREEN unit tests for both paths

### US-002 — Orchestrator mirror (F-002)
**As** any orchestrator, **I want** messages addressed to a peer orchestrator
mirrored to `inbox_orchestrator` **so that** all orchestrators share
visibility and future orchestrators see everything automatically.
**AC:**
- [ ] Given a message `to` an agent whose `bus.permissions` row has
  `is_admin=true` (or `to` is moses/esther), when it is sent via the bus
  API, then a mirror copy lands in `inbox_orchestrator` with
  `forwarded_from` = original `from` (server-side, validate-allowlisted)
- [ ] Mirror suppressed when the target IS `inbox_orchestrator` (no loop)
- [ ] Mirror failure logs but does not fail the primary send
- [ ] corr-idempotent consumption verified (no double-processing)

### US-003 — Shared-inbox error replies (F-003)
**As** an orchestrator, **I want** handler error replies sent to
`inbox_orchestrator` **so that** they are visible and consumed.
**AC:**
- [ ] `agent-message-handler.py` unknown-subject + crash `_RESULT` →
  `inbox_orchestrator`
- [ ] result-send helper takes target from a constant; no personal-queue
  error replies remain

### US-004 — Token & dead-letter hygiene (F-004, F-007)
**As** the operator, **I want** tokens synced and stale dead letters
quarantined **so that** standing 401-poison and backlog disappear.
**AC:**
- [ ] `~/.hermes/cortex/.env` CORTEX_BUS_TOKEN == conf value == DB hash
  (rotate: configs first, then `bus.tokens`)
- [ ] Both hosts' stale `bus-retry/*.json` (pre-2026-09-09 13:00) quarantined
- [ ] `bus.tokens` updated on both hosts' DBs for any rotated identity

### US-005 — Pending-at-max-retries promotion (F-005)
**As** the bus, **I want** `recover_timeouts()` to promote pending messages
at max retries into DLQ **so that** nothing is stuck forever.
**AC:**
- [ ] Pending + retry_count >= max_retries → moved to `<queue>_dlq`
- [ ] DLQ rows older than 6h auto-archive (existing behavior)
- [ ] Recovery function returns without FK errors (defensive DLQ seeding
  already present)

## Summary
- Requirements: 7 functional, 3 non-functional
- Must: 4 | Should: 3 | Could: 0 | Won't: 0
- Stories: 5 (US-001..005), sliced for sequential execution
- Open questions: 0 (all resolved by incident evidence + Luke directives)
- Next: implement slices in order US-001 → US-005, TDD each, deploy via
  cortex-update.sh, dogfood with a live poison-message probe
