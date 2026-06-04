---
name: observability
description: |
  Add or review logs, metrics, traces, alerts, and production diagnostics
  for debuggable, enterprise-grade systems.

  Triggers when user mentions:
  - "observability"
  - "logging"
  - "metrics"
  - "tracing"
  - "alerts"
  - "production debugging"
---

# Observability

## Purpose
Make systems easy to debug, monitor, and operate in production.

Use for:
- structured logging
- metrics
- tracing
- alerting
- audit visibility
- incident diagnostics

---

## Core Rule
Observe behavior, not noise.

Logs, metrics, and traces must help answer:
- what happened?
- where?
- to whom?
- how often?
- how bad?
- why?

---

## Workflow (STRICT)

1. Identify critical user/system flow
2. Identify failure points
3. Add minimal structured logs
4. Add metrics for rate/errors/latency
5. Add trace/request correlation if available
6. Ensure no secrets/PII leak
7. Verify output in dev/test logs

---

## Logging Rules

Prefer structured logs.

Include:
- request_id / trace_id
- user/account id when safe
- operation name
- status/result
- duration
- error code/class

Never log:
- passwords
- tokens
- API keys
- auth headers
- full PII
- raw secrets

Example fields:

```txt
operation=order.create status=failed request_id=abc123 error_code=payment_declined
```

---

## Metrics Rules

Track:

* request count
* error count/rate
* latency
* queue depth
* job failures
* external API failures
* DB/query latency when relevant

Prefer low-cardinality labels.

Avoid:

* user emails as labels
* raw URLs with IDs
* unbounded dynamic labels

---

## Tracing Rules

Use traces for:

* multi-service calls
* slow requests
* external API calls
* background jobs
* complex DB paths

Propagate:

* request_id
* trace_id
* correlation_id

---

## Alerts

Alert on symptoms, not every log.

Good alerts:

* high error rate
* sustained latency
* queue backlog
* failed payment/job spike
* disk/memory saturation

Bad alerts:

* every single exception
* noisy low-priority events
* non-actionable warnings

---

## Enterprise Checks

Consider:

* audit logs for sensitive actions
* dashboards for critical flows
* SLOs / SLIs when applicable
* retention and privacy rules
* incident runbooks

---

## Testing / Verification

Verify:

* logs appear for success/failure
* errors include useful context
* secrets are redacted
* metrics increment correctly
* traces include expected spans

---

## Anti-Patterns

Avoid:

* logging everything
* logging secrets/PII
* vague messages like “failed”
* high-cardinality metric labels
* alerts nobody acts on
* hiding errors with broad rescue/catch

---

## Final Report

```md
## Observability Result
What was added/reviewed.

## Signals
- logs:
- metrics:
- traces:
- alerts:

## Verification
- command/check: result

## Notes
Risks, gaps, follow-ups.
```

---

## Goal

Make production behavior visible, diagnosable, and safe without creating noise.