# Lock Lifecycle Race — P1-A (2026-07-31)

## Symptom

Write tools blocked repeatedly **while a governance lock was held**. Live reproduction
in one session: `begin_change` succeeded (lock file written), then within seconds
`check_lock` returned `active: false` and the lock file was gone. The `.skills-loaded`
marker also kept flipping to a different session ID mid-task, blocking terminal/write
tools 4× in ~15 minutes.

## Root cause 1 — marker race (`.skills-loaded`) → STRUCTURALLY FIXED 2026-08-01

The old shared marker file was written by `_auto_create_skills_marker(session_id)` whenever
any session completed the 8 always-skill loads. Daemon guard covered `cron_`/`bg_`
prefixes + `_is_subagent_session` (state.db `source='subagent'` or `parent_session_id`),
but NOT:
- `cli`-source sessions with date-based IDs (e.g. `hermes` CLI run from cron/terminal)
- a previous conversation's still-live process (telegram source, same gateway) that
  keeps re-loading skills and re-stomping the marker

**Structural fix (2026-08-01): per-session marker files.** Each session writes
its own proof at `~/.hermes-cortex/state/skills-loaded/<session_id>` (content
`session:<session_id>`, atomic temp+rename). `_check_skills_loaded_marker()`
reads ONLY the calling session's file. No session can ever touch another's
marker — the shared file (and every guard bolted onto it: daemon guard,
subagent guard, sticky-marker-per-lock) is gone. Gap-doc P1-A candidate #3,
implemented after the sticky-marker patch proved insufficient for
non-locked interactive sessions. Regression tests:
`TestSkillsMarkerPerSession::test_second_session_does_not_invalidate_first`.

## Root cause 2 — lock theft by purge loops (the actual blocker)

Three purge paths deleted ANY `.governance-*.json` that failed `json.loads`:
- enforcer `_has_governance_lock()` pre-scan (lines ~517-524) + Phase 2 scan (~571)
- MCP `_purge_stale_locks()` (~line 411)
- `ops/scripts/manage/purge-stale-governance-locks.py` (~line 61)

`_write_lock()` wrote NON-atomically (`path.write_text(json.dumps(...))`). A concurrent
purge scan (triggered by ANY session's write check — e.g. a long-lived LLM cron like
`agent-bus-workday` auto-acquiring locks every hour) read the file mid-write → partial
JSON → `JSONDecodeError` → `unlink()` → fresh lock deleted. No cron/interactive
differentiation existed.

## Fixes shipped (commits 900d76e5, c68553ef)

1. **Atomic lock writes** — `_write_lock` writes temp file + `rename()` (same fs) for
   primary AND secondary lock markers. Purge scans never see partial JSON.
2. **Purge never deletes unparseable** — all three purge paths `continue`/skip with a
   debug/warning log instead of `unlink()`. Only parseable-AND-stale locks are removed.
3. **session_type differentiation** — lock state carries `session_type`
   (`cron`/`bg`/`interactive` from session-id prefix). Enforcer purge: a cron/bg session
   never deletes an interactive session's lock.
4. **Sticky marker per governance lock** — see root cause 1.

## Verification

- Adversarial test `/tmp/p1a-adversarial-test.py`: 9/9 assertions — sticky pass with
  stolen marker + lock held; blocked with mismatched marker and no lock; empty-marker
  touch bypass still blocked; partial-JSON lock survives purge; stale interactive lock
  survives a CRON session's purge but is removed by an interactive session's purge.
- Live test: wrote `session:FAKE_STOLEN_SESSION_12345` to `.skills-loaded` while holding
  a lock → write tools still executed (sticky path active on deployed enforcer).

## Detection recipe

```bash
cat ~/.hermes-cortex/state/.skills-loaded          # shows whose session owns marker
ls ~/.hermes-cortex/state/.governance-*.json       # lock files present?
# begin_change OK → check_lock inactive seconds later → purge stole the lock
```
