# Session Re-Engagement Bridge — "What's Next?" Pattern

> Captured 2026-07-23. The user returned after an interrupted session
> (ended mid-task with "Operation interrupted") and asked "what's next?"
> Pattern: user re-engages with an open-ended status question, expects
> a structured health check and context reconstruction.

## The Gap

When a session ends mid-stream (interruption, timeout, explicit stop)
and the user comes back later with "what's next?" or equivalent:

- `session-manager` §4 (Recovery) covers crash recovery with a recovery
  file, but not the "user re-engages with no recovery file" pattern
- `agent-flow` has no "status-inquiry" workflow pattern for non-task
  open-ended health checks
- Both skills are manually-authored and cannot be modified by agents

## Correction-Relevant Pattern

The user's approach to re-engagement is:
1. They expect a **concise, data-backed status report** — not speculation
2. They want **concrete next-step options**, not "what would you like me to do?"
3. They expect context reconstruction from memory/session history, not a
   clean-slate ask

## The Health-Scan Sequence (Fallback Protocol)

When neither `agent-flow` nor `session-manager` can be patched to add
this pattern, use this standalone sequence:

1. **Own context first** (Principle #9 order):
   - memory (check for interrupted session, pending tasks)
   - session_search (discover recent sessions)
   - skills_list (check for relevant domain skills)

2. **Doctor check:**
   ```bash
   python3 ~/.hermes-cortex/scripts/cortex-doctor.py --quiet
   ```

3. **Governance lock:** `check_lock()`

4. **Git state:** `git log --oneline -5` + `git status --short`

5. **Cron health:** `cronjob(action='list')`

6. **Todo state:** `todo()`

7. **Synthesize and report:**
   - Health (pass/warn/fail counts)
   - State (git, lock, crons)
   - Recovery (interrupted session context)
   - Options (2-3 concrete next steps)

## What This Session Produced

- **Patch to `self-improvement-pipeline`** — added "Session-End Skill
  Curation" section with tiered update approach
- **This reference file** — documents the "what's next?" re-engagement
  pattern and the fallback health-scan sequence
