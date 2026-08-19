# Silent-JSON-Wrapper Case — agent-inbox-workday (2026-08-19)

Case notes for the false positive documented in `cron-output-diagnostics`.
Facts below are as recorded in the SKILL.md body (upstreamed from the fleet
skill report); this file makes the referenced evidence trail concrete.

## The incident

- Job: `agent-inbox-workday` (LLM-driven, workday inbox processing).
- The job's healthy no-op run produced `["SILENT"]` — the `[SILENT]` token
  wrapped in JSON quotes — instead of the bare literal.
- Delivery suppression is a LITERAL match in the delivery pipeline:
  `response == "[SILENT]"` (bare token, no wrapper). The JSON-wrapped
  variant does NOT match, so the run was DELIVERED to the user.
- The quality watchdog (`agent-cron-quality-watchdog`, every 10 min) also
  matched on the wrapped variant: its short-response garbage check fired
  because the wrapper falls outside the literal `[SILENT]` exemption,
  producing a 🟠 false-positive flag.

## Why it's a two-layer failure

1. **Delivery layer** — the no-op was not suppressed; the user got noise.
   Wrapped variants violate the `[SILENT]` output contract even though the
   model's intent (stay quiet) was correct.
2. **Detection layer** — the watchdog mis-flagged a healthy no-op as garbage
   because its exemption is byte-literal, not whitespace/JSON-tolerant.

## Fixes (both lanes)

| Lane | Who | Fix |
|------|-----|-----|
| Source (worker lane) | Any agent | Harden the cron's LIVE prompt via `cronjob action='update'`: require the bare `[SILENT]` literal — "never JSON-wrapped, quoted, or in a code block". Install-script prompt edits do NOT propagate to existing jobs — the live update is the only lever. |
| Detection (orchestrator lane) | Orchestrator | Normalize the watchdog's `[SILENT]` exemption (strip JSON/whitespace wrappers before comparison) in `ops/scripts/health/agent-cron-quality-watchdog.py`. Workers escalate this via `contact-orchestrator.sh` with a ready-to-apply patch. |

## Triage rule

A 🟠 short-response flag whose content is any wrapped form of `[SILENT]`
(`["SILENT"]`, `[ SILENT ]`, `'[SILENT]'`) is a **false positive** — treat
it as a contract breach to fix, not a broken job. The identical-alert-every-
10-min repeat is the same single stale run re-flagged (the watchdog has no
dedup); check the output file timestamp before reacting.
