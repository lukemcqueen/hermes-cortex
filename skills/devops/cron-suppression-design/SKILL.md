---
name: cron-suppression-design
description: "Use when a cron re-delivers the same warnings every tick."
version: 1.0.0
category: devops
---

# Cron Suppression & Dedup Design

Rules for state-based suppression in no_agent script crons — when the same
warning re-delivers every tick despite a dedup mechanism existing.

## The fingerprint rule (always-on)

**Normalize volatile content out of the HASH only, never from the delivered
text.** Any report embedding a live counter, timestamp, or growing number
(e.g. "740 SSH brute-force attempts in last 24h") changes a raw-text hash
every run, so suppression never fires and the same warnings re-deliver
hourly. Hash a normalized copy:

```bash
REPORT_HASH=$(echo -n "$REPORT" | tr '0-9' '#' | sha256sum | cut -c1-16)
```

Identical warnings dedup regardless of the counter; a genuinely NEW warning
kind still re-notifies. The user still sees the live count whenever a report
does send.

## Verify before claiming fixed (always-on)

1. **Simulate the hash property** (30-second check, no sudo needed):
   change only the count → hash must MATCH; add a new warning line → hash
   must DIFFER.
2. **Dogfood the real path** — a repo edit is not deployed, and a manual
   script run does not update the scheduler:
   repo fix → `bash ~/hermes-cortex/ops/scripts/cortex-update.sh` (deploy) →
   `cronjob action='run' job_id=<id>` (refreshes scheduler `last_status` and
   writes the fingerprint file) → run the deployed script a second time;
   it must exit 0 silently (suppressed).
3. Check the fingerprint file (`~/.hermes-cortex/state/<script>-fingerprint.txt`)
   was written on the first run and matches the second run's hash.

## Diagnosis path for "same message every tick"

1. Read the script's suppression mechanism (fingerprint file / failure-state
   helper) and the latest output files under `~/.hermes/cron/output/<job-id>/`.
2. Diff two consecutive reports: byte-different only in digits/counts →
   fingerprint is defeated by volatile content (this rule). Structurally
   different → new warning kinds are genuinely appearing; dedup is working.
3. Fix the hash normalization, not the checks — the checks firing correctly
   is not the bug.

## Pitfalls

- Do not dedup on individual check names with per-check state files unless
  warnings can genuinely expire — a single report-level normalized hash is
  simpler and self-clears when the report goes empty.
- Do not move the normalization into the delivered text — the user should
  still see the real count; only the fingerprint input changes.
- The pre-push dogfood gate blocks on doctor deploy-drift: run
  `cortex-dogfood.sh --force` (pull → deploy → doctor → verify) if the push
  is blocked with "Deployed state does not match repo source".
