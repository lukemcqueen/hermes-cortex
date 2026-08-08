---
name: cron-output-contracts
description: "Use when a script reads another cron's output or retires."
version: 1.0.0
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
---

# Cron Output Contracts — Producer-Consumer Reliability & Cron Retirement

## When to Load

- You are writing or fixing a script that reads **another cron's output**
  (fixer reads sensor output, collector reads a watchdog's report dir).
- A fixer/collector/watchdog **silently no-ops** — runs "successfully" but
  never acts.
- You are **removing or retiring** a cron (dead script, superseded job,
  renamed mechanism).
- You are diagnosing why two crons appear to duplicate each other.

## Rule 1 — Never hardcode a cron's job id

Job ids are **ephemeral**: they change whenever a cron is recreated
(re-install, re-create, migrate). A script that reads
`~/.hermes/cron/output/<hardcoded-id>/` goes silently blind the day the
cron is recreated under a new id — it still exits 0, still logs, still
"runs", and fixes nothing.

Real case (2026-08-08): `agent-remediate-apply.py` hardcoded
`SENSOR_JOB_ID="2c71ffaf3a55"` while the live `agent-remediation-sensor`
ran under `0afb2f94d9b7`. The deterministic fixer was a no-op for weeks
and nobody noticed — the sensor itself looked healthy.

**Canonical resolution — by NAME, from jobs.json:**

```python
import json
from pathlib import Path

HOME = Path.home()
SENSOR_JOB_NAME = "agent-remediation-sensor"
OUTPUT_ROOT = HOME / ".hermes" / "cron" / "output"

def discover_output_dir() -> Path | None:
    jobs_file = HOME / ".hermes" / "cron" / "jobs.json"
    try:
        if jobs_file.exists():
            data = json.loads(jobs_file.read_text(encoding="utf-8"))
            jobs = data if isinstance(data, list) else data.get("jobs", [])
            for j in jobs:
                if j.get("name") == SENSOR_JOB_NAME and j.get("id"):
                    d = OUTPUT_ROOT / str(j["id"])
                    if d.exists():
                        return d
    except Exception:
        pass
    # Fallback: newest .md under the output root
    best, best_mtime = None, 0.0
    if OUTPUT_ROOT.exists():
        for d in OUTPUT_ROOT.iterdir():
            if not d.is_dir():
                continue
            mds = sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            if mds and mds[0].stat().st_mtime > best_mtime:
                best, best_mtime = d, mds[0].stat().st_mtime
    return best
```

When the producer script's *name* changes too, update the constant — never
reach for the id.

## Rule 2 — Detect zombies before removing (or before blaming the fixer)

A cron is a **zombie** when its input path died but the cron itself still
ticks. Before "fixing" a seemingly broken fixer, check:

1. **Producer still writes?** Is the input dir/state file being updated?
   (`ls -lt <dir>` — a stale mtime = dead producer.)
2. **Cron last_status?** `cronjob action=list` — is the producer actually
   running ok, or has its job id changed?
3. **Deploy registration?** Is the script still `register()`-ed in
   `cortex-update.sh`? An unregistered script keeps running from a stale
   deployed copy that never updates.
4. **Deployed copy age?** `ls -la ~/.hermes/scripts/<script>` — a weeks-old
   mtime while the repo has newer source = orphaned deploy.
5. **Handler sharing?** Two crons that "duplicate" each other often import
   handlers from the SAME module or read the SAME input — trace both before
   removing either; the apparent duplication may hide a broken link in one
   of them (case study: `references/fixer-reconciliation-2026-08-08.md`).

## Rule 3 — Cron retirement: the full touchpoint map

Removing a cron touches ALL of these — one missed location = stale
reference or doctor drift:

1. **Live cron** — `cronjob action='remove' job_id=<id>` (list first; never
   guess ids).
2. **install-crons.sh** (or install-orch-crons.sh) — remove the `create_cron`
   block AND the matching uninstall-array entry (the array is the doctor's
   expected-cron source; a leftover name = false ❌).
3. **cortex-update.sh** — remove the `register()` line for the script.
4. **Watchdog lists** — grep other health scripts for the script name
   (e.g. `agent-stale-ref-watchdog.sh` CRON_SCRIPTS array).
5. **Deployed copies** — remove `~/.hermes/scripts/` and
   `~/.hermes-cortex/scripts/` copies (and repo source via `git rm`).
6. **Docs** — every table that names the cron: `docs/cron-schedules.md`,
   `docs/cron-jobs-reference.md`, `docs/fleet-reference.md`, `README.md`
   (pipeline diagrams + category tables), `docs/setup-reference.md` (key
   scripts lists). Grep the whole repo:
   `grep -rn "<cron-name>" --include="*.md" --include="*.sh" --include="*.py"`.
   Historical migration notes may keep the name intentionally — leave those.
7. **New docs** — if the change adds new docs, add `docs/DOCS-INDEX.md`
   entries or the pre-commit DOCS AUDIT warns.

Then verify: `fix-cron-duplicates.py` (arrays in sync) → `bash -n` /
`py_compile` on changed scripts → adversarial gate
(`adversarial-verify.py --file <f> --level A2 --gate`) → commit →
`cortex-update.sh` (deploy) → re-acquire governance lock (deploy purges
locks) → push → `cronjob action='run'` on remaining crons (refreshes
scheduler `last_status` — manual runs don't) → doctor clean.

## Pitfalls

- **Hardcoded job id = silent blindness.** Exit 0 + log lines ≠ working.
  Verify the script actually reads the CURRENT producer output.
- **"Duplicate" fixers are a diagnosis prompt, not a removal verdict.**
  Check handler origin and input sources first (Rule 2.5).
- **Uninstall array ≠ create block.** Removing only one leaves the doctor
  expecting a cron that no longer exists (or missing one that does).
- **Deploy ≠ loaded.** After `cortex-update.sh`, the running cron picks up
  the new script on its next tick — and your governance lock is gone;
  re-acquire before further repo work.

## References

- `references/fixer-reconciliation-2026-08-08.md` — full case study: the
  two-fixer overlap, stale-job-id blindness, zombie detection, and the
  end-to-end retirement of `agent-apply-fixes` (all touchpoints + evidence).
