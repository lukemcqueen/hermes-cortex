---
name: security
description: |
  Enterprise security guardrails for coding and security review checklist for diffs.
  Covers auth, permissions, secrets, data, migrations, logging, AI/tooling.
  Triggers: "security", "auth", "secrets", "security review", "audit this change", "check for vulnerabilities", "secure implementation"
---

# Security

## Guardrails (during coding)

**Never without explicit approval:** expose secrets, weaken auth, bypass permissions, disable CSRF/CORS/middleware, remove audit logs, run destructive migrations, commit .env/keys, grant broad access.

**Always enforce:**
- **Auth:** verify identity, check permissions on every action, least privilege, never trust client-provided roles/flags
- **Input/Output:** validate all inputs (type, format, bounds), sanitize, escape output, no raw interpolation into queries
- **Secrets:** env vars only, never hardcode, never log passwords/tokens/PII, mask in errors
- **Data:** treat user data as sensitive, minimal exposure, encrypt at rest/transit where applicable
- **Logging:** log actions not sensitive data, include request IDs + safe user IDs
- **Migrations:** rollback plan, avoid long locks, batch large updates, verify with SELECT first, never combine schema + data risk
- **API/Network:** validate payloads, enforce rate limits, explicit status codes, no internal error exposure, protect internal endpoints
- **Dependencies:** avoid unverified packages, prefer maintained libs, review before adding
- **AI/Tooling:** never trust tool output blindly, prevent prompt injection, sanitize tool call inputs

## Review Checklist (for diffs)

1. Auth verified server-side? Least privilege? No client-trusted roles?
2. All external inputs validated (type/format/bounds/path)?
3. Parameterized SQL/ORM? No raw shell from user input?
4. No unnecessary PII returned? Internal errors hidden from users?
5. No secrets hardcoded? No .env/keys committed? Tokens masked in logs?
6. Sensitive actions logged? Logs avoid passwords/tokens/full PII?
7. Migration has rollback? No long table locks? Destructive changes require approval?
8. New dependencies justified, maintained, and trusted?

## Severity

**Critical:** credential exposure, auth bypass, RCE, destructive production data, privilege escalation
**High:** missing auth on sensitive action, SQL/command injection, PII exposure, unsafe file upload, destructive migration without rollback
**Medium:** weak validation, missing rate limit, excessive data returned, unsafe error details, missing audit trail
**Low:** minor hardening, unclear naming around security behavior, missing defensive comments

## Output

```md
## Security Review
pass | needs changes | blocked

## Findings
### F1: <title>
- Severity: critical | high | medium | low
- File:
- Risk:
- Fix:

## Fixed (if guardrails applied during coding)
- what was changed and why

## Notes
Assumptions, unknowns, residual risk
```

## Anti-Patterns

Trusting client input | skipping auth "temporarily" | logging secrets | broad try/catch hiding errors | string SQL with user input | exposing internals | vague findings with no exploit path | approving unverified secrets | saying "looks safe" without checks | recommending broad rewrites when small fix works | ignoring auth boundaries | theoretical issues with no exploit path

## Goal

Ship secure, auditable, least-privileged code safe for enterprise production.
