# Concurrent-Actor Reconstruction — "the repo changed under me"

Recipe for when git state mutates mid-session while you did nothing: a peer
commit gets reset, the index clears, your work shows up in someone else's
stash, or HEAD moves under you. Worked example: 2026-08-03 fleet crons
(agent-bus-workday / agent-inbox-workday) colliding with the interactive
session on the shared repo.

## 1. Detect the mutation instantly

```bash
git reflog --date=iso -8          # every HEAD move, timestamped
git status --short                # staged vs unstaged vs missing
```

A `reset: moving to HEAD~1` (or `moving to origin/main`, `moving to HEAD`)
at a timestamp you don't own = a concurrent actor rewound history. A
`checkout: moving from <sha> to main` = an actor was on a detached commit.

## 2. Identify the actor by commit authorship

```bash
git log <sha> -1 --format="%an <%ae> %ci %s"   # who really made it
git branch -a --contains <sha>                  # empty = orphaned (reset away)
git show <sha> --stat                            # recover content of the lost commit
```

Fleet commits carry agent authors (`esther-agent`, `gisu-agent`,
`moses-agent`) — the author reveals WHICH agent session, not necessarily the
machine. `git branch -a --contains` proves a commit was reset out of history
(no branch holds it) — its content is still recoverable via `git show`.

## 3. Your work was swept into a sibling's stash

```bash
git stash list                                   # e.g. "On main: sibling-wip-soul-cortex-skills"
git show --stat <stash-sha>                      # what the stash captured
git checkout <stash-sha> -- <paths>              # recover specific files
```

A concurrent session that needs the tree clean will `git stash push` YOUR
uncommitted work under its own label. `git stash list` + `git show --stat`
identifies it; `git checkout <stash> -- path` restores without popping the
whole stash. The stash commit object survives even after `git stash drop`.

## 4. Attribute intent from the actor's own session transcript

`~/.hermes/state.db` `messages` table holds every session's tool calls. A
sibling cron session often narrates exactly what it did:

```python
import sqlite3
db = sqlite3.connect('/home/moses/.hermes/state.db')
cur = db.cursor()
cur.execute("SELECT id, role, substr(content,1,400) FROM messages "
            "WHERE session_id=? ORDER BY id DESC LIMIT 30", (sid,))
```

Read the LAST messages of the sibling session (cron session ids are
`cron_<jobid>_<timestamp>` in the sessions table) — e.g. "my edits are fully
reverted — checks.py matches origin" tells you the actor deliberately
reverted, vs "staged changes were cleared between commands" tells you the
actor was confused too. Distinguish DELIBERATE reversion from collision
chaos before re-applying anything.

## 5. Decide: adopt, restore, or discard

- The reset commit may be a PEER'S SUPERIOR WORK that made your parallel
  effort obsolete — `git show <sha>` and compare before re-doing it.
  Template/skill restructures from a co-orchestrator (esther) outrank a
  local half-finished trim; adopt theirs, discard yours.
- The reset may have been a REVERT of a wrong commit — verify the content,
  don't just re-apply.
- Always pull (`git pull --rebase origin main`) after the dust settles;
  origin may have moved past you (the actor may have pushed).

## 6. Prevent recurrence

Concurrent-session repo collisions are a CLASS of failure, not an event.
Fixes that work:
- Gate day-time crons with a session-active guard (see
  cron-job-management reference `session-active-guard.md`): the cron's
  `script` prints ACTIVE/IDLE from `state.db` interactive-session recency;
  the prompt skips the tick when ACTIVE.
- Never hold the only copy of work in the working tree during cron hours —
  commit early, push often.
- When `git status` shows changes you didn't author, snapshot reflog +
  stash list BEFORE touching anything (the evidence vanishes on the next
  stash pop / reset).
