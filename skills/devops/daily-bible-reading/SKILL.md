---
title: Daily Bible Reading Cron
name: daily-bible-reading
version: 1.0.0
description: >
  Daily cron job that reads one book of the Bible, extracts 3 lessons with
  practical application to server operations, and appends to SOUL.md.
  Runs autonomously at 1am — no user interaction, no notification.
triggers:
  - Cron job at 1am daily
  - Reading one book of the Bible per day through the full canon
  - SOUL.md maintenance and state file management
---

# Daily Bible Reading Cron

## Implementation Note

There are **two implementations** of the daily bible reading cron on this system:

| Aspect | Legacy (this skill) | Active (installed) |
|--------|---------------------|--------------------|
| Type | LLM-driven cron | `no_agent` Python script |
| Script | N/A (LLM prompts directly) | `~/hermes-cortex/src/scripts/agent-daily-bible-reading.py` |
| API | bible-api.com (WEB translation) | OpenCode Zen (deepseek-v4-flash) |
| State tracking | `~/.hermes/bible-reading-state.txt` | Parses SOUL.md for last book read |

The **active** implementation is the `no_agent` Python script installed as
`agent-daily-bible-reading` — see the `agent-daily-bible-reading` skill for
its current behavior. This skill documents the original LLM-driven pattern
and the state file it introduced.

## Legacy Pattern (LLM-driven cron)

### Schedule
Runs at **1am daily**, autonomous — no user interaction, no notification.

### Flow (per run)

1. Read the state file to find the current book/position:
   ```bash
   cat ~/.hermes/bible-reading-state.txt
   # format: <book>:<chapter>:<position>
   ```
2. Fetch the next chapter from bible-api.com:
   ```bash
   curl -s "https://bible-api.com/<book>+<chapter>?translation=web"
   ```
3. Extract **3 lessons** with practical application to server operations
   (the fleet's frame: reliability, discipline, stewardship).
4. Append the entry to SOUL.md under the daily bible entries section:
   ```markdown
   ### <Book> — *"<key verse>"* (<Book> <chapter>:<verse>)
   <lesson text with application>
   ```
5. Advance the state file to the next book/chapter through the full canon.

### State file management

```bash
# View current position
cat ~/.hermes/bible-reading-state.txt

# Reset / correct a position
echo "Genesis:1:1" > ~/.hermes/bible-reading-state.txt

# Skip ahead (e.g., after a gap)
echo "Exodus:3:1" > ~/.hermes/bible-reading-state.txt
```

## Transition History

The legacy LLM cron was replaced because the small local model produced
unreliable lesson quality every tick. The active `no_agent` script uses a
single API call to OpenCode Zen (deepseek-v4-flash) for the lesson generation
and handles the rest deterministically — the `cron-no-agent-conversion`
pattern applied to scripture reading.

## Spurious-Run Recovery (double-entry accident, 2026-08-10)

The active no_agent script **ignores unknown args** — probing it with
`--help` (or any flag) executes the FULL side-effect path: it appends a new
`### Book —` entry for the NEXT book, and when the section exceeds the bound
it archives the oldest entries out of SOUL.md. Two probe runs in one session
produced two same-day entries (Deuteronomy + Joshua) and evicted the
legitimate Leviticus + Numbers entries — jumping the cycle anchor two books.

Recovery (verify BEFORE the next scheduled 01:00 run):
1. Restore the evicted SOUL.md entries **verbatim** from
   `~/brain/<agent>/bible/archive/SOUL-archive.md` (the script appends the
   blocks it evicts — copy the exact `### Book —` block back into
   `## Scripture Insights`)
2. Delete the premature brain page `~/brain/<agent>/bible/<book>.md` and
   revert the INDEX.md row it stamped to `—`
3. Trim the duplicate archive section the spurious run appended
4. Verify the LAST `### Book —` entry in SOUL.md is the correct anchor
   (Numbers → next should be Deuteronomy, not Joshua)

Do NOT re-fire the cron via the scheduler to clear a `last_status: error`
that came from a transient API timeout when the day's entry was already
recovered — re-firing stamps the NEXT book with today's date, shifting the
whole cycle. Let the natural next scheduled run clear the status.

## Related
- `agent-daily-bible-reading` — the active installed implementation
- `cron-no-agent-conversion` — why/how the conversion happened
- `soul-refinement` — SOUL.md maintenance
- `cron-job-management` — cron naming and lifecycle
