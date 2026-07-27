# Post-Change Verification — 2026-07-21 Lesson

## The Failure Pattern

User had to say three times about doctor warnings:
1. "install/update/doctor all will work correctly?" — initial question
2. "YOU NEED TO MAKE THIS MANDATORY, NOT OPTIONAL" — frustration escalation

The doctor showed `⚠️ AGENTS.md sync` and `⚠️ Skills manifest: template`. These were treated as low-priority "warnings" when they were actually blocking issues: fleet agents reading stale instruction files, and template drift eventually causing misconfiguration.

## Root Cause

- Doctor warnings were mentally categorized as "advisory" vs "failures"
- No systematic enforcement that every ⚠️ must be fixed before end_change()
- cortex-update.sh had no step to sync AGENTS.md to ~/.hermes/ — so it drifted with every change
- skills.yaml mtime wasn't synced with template — so doctor false-warned every time

## The Fix

1. **cortex-update.sh** now syncs AGENTS.md and skills.yaml timestamp automatically (commit d780e87)
2. **Self-improvement-pipeline** Tenet 2 already says "Doctor warnings are required" but cortex-preflight needed the post-change verification section (blocked by curator)
3. **SOUL.md** already has the doctor-warnings tenet

## Related Skills

- `self-improvement-pipeline` — Tenet 2 (doctor warnings required)
- `cortex-preflight` — intended for post-change section (blocked)
- `change-checklist` — Phase 5 already has "Doctor runs clean"

## Guardrails That Were Missing

- Pre-change: no check that doctor is clean before starting
- Post-change: no check that doctor is clean before end_change
- Deployment chain: no layer-by-layer verification when adding new components
