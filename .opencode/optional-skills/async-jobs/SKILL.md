---
name: async-jobs
description: |
  Design, implement, and review background jobs, queues, retries,
  idempotency, scheduling, and async workflows.

  Triggers when user mentions:
  - "background job"
  - "async job"
  - "queue"
  - "worker"
  - "retry"
  - "scheduled job"
---

# Async Jobs

## Purpose
Build safe asynchronous workflows for work that should not block requests.

Use for:
- email delivery
- webhooks
- imports/exports
- external API calls
- scheduled tasks
- long-running processing

---

## Core Rule
Async jobs must be idempotent, observable, and retry-safe.

---

## When to Use Jobs

Use jobs for:
- slow work
- unreliable external APIs
- retryable operations
- scheduled work
- work not required for immediate response

Do NOT use jobs when:
- result is required immediately
- transaction consistency must be synchronous
- failure cannot be retried safely

---

## Workflow (STRICT)

1. Identify async boundary
2. Define job input
3. Make job idempotent
4. Define retry behavior
5. Define failure/dead-letter handling
6. Add observability
7. Add tests
8. Verify enqueue + perform behavior

---

## Job Input Rules

Pass stable identifiers, not large objects.

Good:
```txt
user_id
order_id
invoice_id
```

Bad:

```txt
full user object
large JSON blob
raw file contents
```

---

## Idempotency Rules

A job may run more than once.

Protect with:

* unique keys
* status checks
* database constraints
* idempotency records
* external idempotency keys

Example:

```txt
If invoice already sent, return success without sending again.
```

---

## Retry Rules

Retries should be:

* limited
* exponential/backoff if available
* safe for duplicate execution
* logged with attempt count

Do not retry:

* validation errors
* missing required data
* permanent permission failures
* non-retryable business states

---

## Transaction Rules

Avoid enqueueing jobs before data commits.

Prefer:

* after_commit hooks where appropriate
* explicit enqueue after successful transaction
* outbox pattern for high reliability

---

## Failure Handling

Define:

* max attempts
* final failure state
* dead-letter behavior
* alert condition
* manual recovery path

---

## Observability

Each job should log:

* job name
* job id
* relevant safe entity id
* attempt count
* duration
* result/error

Metrics:

* enqueued count
* success count
* failure count
* retry count
* queue latency
* execution duration

---

## Testing Rules

Test:

* enqueue behavior
* successful execution
* retryable failure
* non-retryable failure
* idempotent duplicate run
* missing/deleted record

---

## Enterprise Patterns

Consider:

* outbox pattern
* dead-letter queues
* rate limiting
* concurrency limits
* job uniqueness
* tenant isolation
* priority queues
* poison message handling

---

## Anti-Patterns

Avoid:

* passing huge payloads
* non-idempotent side effects
* infinite retries
* silent failures
* no monitoring
* jobs depending on request context
* enqueueing inside uncommitted transactions
* mixing many responsibilities in one job

---

## Final Report

```md
## Async Job Result
What was added or reviewed.

## Job Design
- job:
- input:
- retry:
- idempotency:
- failure handling:

## Verification
- command/test: result

## Notes
Risks, recovery, follow-ups.
```

---

## Goal

Create background workflows that are reliable, retry-safe, observable, and production-ready.