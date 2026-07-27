# gbrain Health Check False Positive Pattern

## Symptom

The `remediation-sensor.py` reports every 5 minutes:

```json
{"type": "gbrain_health_check_failed", "severity": "medium",
 "detail": "gbrain doctor reported issues"}
```

The sensor runs `gbrain doctor --fast` which returns exit code 1.

## Root Cause

`gbrain doctor --fast` checks resolver_health against the skill library. Many
content/marketing skills (SEO, copywriting, email sequences, brand guidelines,
etc.) exist in the known skills list but lack resolver trigger entries in
`RESOLVER.md` and lack `triggers:` arrays in their frontmatter. This is
**expected** — these skills aren't used with the gbrain brain.

## Normal baseline

The health score typically sits at 70/100 with these patterns:

| Check | Score | Expected? |
|---|---|---|
| resolver_health | FAIL — 22 errors, 22 warnings | Yes — content skills lack triggers |
| connection | WARN — skipping DB in --fast mode | Yes — no connection, just fast mode |
| skill_conformance | WARN — manifest.json not found | Yes — known/expected |
| brain checks | 100/100 | Yes — core brain is healthy |
| retrieval_reflex | OK | Yes — Postgres direct |

## When to escalate

Do NOT escalate on the `gbrain_health_check_failed` sensor report alone.
Only escalate if any of these are ALSO true:

- `systemctl --user status gbrain-autopilot.service` shows inactive
- Postgres (gbrain database) is unreachable
- Overall health score drops below 50 AND the breakdown shows new
  service-level failures (not the same 22 resolver "unreachable" entries)
- The autopilot has restarted 5+ times in the last hour (crash-looping)
