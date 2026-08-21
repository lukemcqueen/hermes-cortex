# Daemon-restart gap, peak-cadence economics, and pin-gate fixes (2026-08-21)

Verified during the HC fleet cost marathon. Three lessons that extend the
pitfalls in the umbrella SKILL.md.

## 1. Patched on disk ≠ loaded in the daemon (the restart-pending marker)

**Symptom:** `install-cron-cost-tracking.py --status` reports 9/9 OK, yet every
new `usage_audit.jsonl` line lacks `cache_read_tokens`/`cache_write_tokens`.

**Root cause:** `hermes update` replaces scheduler.py (and cortex-update.sh
auto-reapplies the cost patch), but the RUNNING gateway is a long-lived daemon
that keeps the OLD module in memory until a real process restart. Observed:
scheduler.py mtime 22:23, daemon started 16:52 — the 22:23 update patched the
file; the daemon kept writing unsplit audit lines for hours.

**Verification rule:** fire a cheap no_agent cron and READ its audit line for
the cache fields. Grepping the file proves nothing about the running process.

**Fix shipped:**
- `agent-hermes-update.sh` writes `~/.hermes-cortex/state/restart-pending`
  (content `updated:<version>`) when `hermes version` changes.
- Doctor `check_soul_sync` (yes, that's where it landed) WARNs on the marker:
  "Hermes updated but the daemon has not been restarted — running stale code".

**Operational note:** the gateway restart (`hermes gateway restart`) is
governance-blocked from inside the gateway session — it must run from a
separate shell. The marker exists so the stale-daemon state surfaces instead
of rotting silently.

## 2. No_agent scripts pay nothing in peak hours

DeepSeek's 2× peak pricing (01:00–04:00 & 06:00–10:00 UTC = 10-13 & 15-19 KST)
applies ONLY to LLM API calls. Survey result: all 19 crons that fired in peak
KST hours were `no_agent=True` scripts (`*/5` watchdogs, message handlers) —
they cost $0 regardless of when they fire. **Rescheduling no_agent crons is a
non-issue; only LLM-driven crons matter for off-peak moves.**

**Cadence cut that works:** halving LLM cron frequency (hourly → every-2h) on
backlog/bus/fixer jobs cuts peak runs (orch-backlog-driver: 7→3 peak runs/day)
WITHOUT losing detection — the no_agent watchdogs (system-alert, mcp-health,
remediation-sensor, all `*/5`) catch issues immediately; the LLM job is the
REPAIR step, not detection. 2h repair latency is acceptable when detection is
instant and free. Use explicit hour lists (`0 8,10,12,14,16,18,20,22 * * *`)
not range-step (`8-22/2`) — explicit lists are already proven in the manifest.

## 3. Installer pin gates must ALWAYS run (the Titus 11-cron lesson)

A `pin_cron_model "$name" "$model" "$provider"` call site gated on
`if [[ -n "$model" || -n "$provider" ]]` silently skips jobs whose caller
didn't pass explicit model args — so the manifest lookup inside the function
never runs for existing jobs. Consequence: Titus's 11 crons stayed on retired
`deepseek-chat` even after `install-crons.sh --force` (the pin only fired on
create-path jobs with non-empty model).

**Fix:** call the pin function UNCONDITIONALLY after create/edit; let it
self-guard with its own early-return when there's nothing to pin (it already
reads the manifest itself). Pass `reasoning_effort` as its own positional arg
(`${12:-}` local) — the old 3-arg call silently dropped reasoning pins too.

**Marker-drift sibling:** the installer's idempotency markers (`LLM_MARKER`
etc.) must byte-match what the patch actually writes. A stray prefix (e.g.
`session_estimated_cost_usd": float(getattr(agent` when the inserted text has
`estimated_cost_usd": float(getattr(agent, "session_estimated_cost_usd...`)
makes `--status` report FAIL on every run even though the patch IS applied —
a false negative. When FAIL persists but the patch text is verifiably in the
file, diff the marker against the inserted content and fix the template.
