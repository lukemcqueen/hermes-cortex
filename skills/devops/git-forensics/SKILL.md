---
name: git-forensics
description: "Use when files vanished or uncommitted deletions appeared."
version: 1.0.0
category: devops
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [git, forensics, deletion, attribution, uncommitted, audit]
    related_skills: [hermes-recovery, github-repo-management, git-deployment-workflow, remediation-investigation]
---

# Git Forensics — Who Deleted / Changed What

Investigate uncommitted working-tree changes (especially deletions) and
attribute them to a source: user shell, agent session, cron, or background
process. Use when a file "disappeared" from a repo, when git status shows
deletions you didn't make, or when you must prove a change was NOT made by
a given actor.

**Trigger phrases:** "who deleted X", "these files are gone", "git status
shows deleted but I didn't do it", "find out what happened to the repo",
"uncommitted changes I didn't author".

## Golden Rule — Uncommitted ≠ Committed

An uncommitted working-tree deletion is **NOT** a security reduction on the
remote. HEAD and the index still contain the files until someone commits.
Always establish this first:

```bash
git status -s                          # D = deleted in worktree
git ls-files --deleted                 # files in index but missing on disk
git diff --stat                        # worktree vs index (unstaged)
git diff --cached --stat               # staged changes
git log --oneline -1 origin/main       # remote is safe until pushed
```

If the deletions are unstaged (`Changes not staged for commit`), the index
still tracks them — they are trivially restorable with `git checkout -- <paths>`.

## The Investigation Sequence

### 1. Snapshot the evidence first
- `git status`, `git ls-files --deleted`, `git diff --name-status`
- Directory mtimes: `stat -c '%n | mtime=%y' <dir>/` — but see Pitfall: a
  later `git stash pop` overwrites dir mtimes, masking the true deletion time.

### 2. Read the reflog with timestamps
```bash
git reflog --date=iso | head -20
```
**A `reset: moving to HEAD` entry exactly ~1s before a suspicious dir mtime
is the signature of `git stash push`** (stash does an internal reset of the
index), NOT a deletion. A cron that stashes uncommitted changes before
fetching will produce exactly this pattern. Do not misattribute the reset
as the deletion event.

### 3. Inspect the stash (dropped stashes are still reachable)
```bash
git cat-file -t <stash-sha>            # 'commit' even after stash drop
git show --stat <stash-sha>            # parent = the commit it was based on
git diff --stat HEAD <stash-sha>       # full delta incl. concurrent commits
```
The stash's **parent commit** tells you the base; its tree diff shows what
the working tree looked like AT stash time. If the stash contains the
deletions, they existed BEFORE the stash — the stasher preserved, did not
create them.

### 4. Hermes cron-output evidence
Every no_agent cron run writes its stdout to
`~/.hermes/cron/output/<job_id>/<timestamp>.md`. Read the run at the
suspicious time:
```bash
ls -lat ~/.hermes/cron/output/ | head
cat ~/.hermes/cron/output/<job_id>/<timestamp>.md
```
Map job IDs to names via `~/.hermes/cron/jobs.json`. The daily
`agent-hermes-cortex-sync` cron (22:33 KST) stashes → fetches → pops; its
output lines like `deleted: ops/...` are the **pre-existing** state it
saved and restored, not actions it took.

### 5. Session-DB forensics (Hermes)
`~/.hermes/state.db` messages table stores agent tool calls in the
`tool_calls` column as a JSON array; `function.arguments` is a **JSON-escaped
string** — parse with `json.loads`, never regex:
```python
import sqlite3, json, datetime
cur.execute("SELECT id, session_id, timestamp, tool_calls FROM messages "
            "WHERE tool_calls IS NOT NULL AND timestamp BETWEEN ? AND ?", (lo, hi))
for r in cur.fetchall():
    for c in json.loads(r[3]):
        if c.get('function', {}).get('name') == 'terminal':
            args = json.loads(c['function']['arguments'])
            print(datetime.datetime.fromtimestamp(r[2]), r[1], args['command'][:100])
```
This definitively proves whether ANY agent session ran the deletion command.
Check subagent sessions too (`source='subagent'` in sessions table) — they
have their own session IDs. Empty telegram sessions (`0 msgs`) are stubs.

### 6. Pin the window with a backup bundle
A git bundle taken before the event bounds the deletion time:
```bash
git bundle list-heads backup.bundle
git cat-file -e FETCH_HEAD:<path> && echo PRESENT   # PRESENT ⇒ deletion after backup
```
Present in bundle + missing in worktree ⇒ deletion happened after the
backup timestamp. Repeat with the last commit that touched the file
(`git log --oneline -1 -- <path>`) to bound the other side.

### 7. Check the interactive shell honestly
`~/.zsh_history` only flushes on clean shell exit. **Reboots kill the shell
before flush**, so a missing history entry does NOT exonerate the user —
but it also isn't evidence against them. Check `who`/`ss -tnp | grep :22` for
other SSH sessions, `lightdm` local sessions, and `journalctl -u ssh` for
preauth probes (bots are normal noise, not sessions). auditd is usually
inactive on this host — don't expect ausearch hits.

### 8. Red herrings
- **Hardline "unconditional blocklist" tool errors** look like a deletion
  attempt but are often just regex-char greps the parser rejected. Read the
  assistant message right before the block to see the actual command.
- `grep -c` returning 0 / `search_files` returning empty on hidden dirs —
  verify with `ls`/`git ls-files` before concluding absence.

## SECURITY RULE — User Directive (2026-08-01)

**Never commit or push anything that REDUCES security.** If the working tree
contains uncommitted deletions of security-critical files (`hermes-plugin-lock`,
`blocked_ips.add`, `hermes-security`, `deploy-sudoers.sh`, nginx deploy
configs), investigate and restore them — **never sweep them into your
commit**. When committing your own work alongside foreign uncommitted
deletions, stage ONLY your paths:

```bash
git add <specific-file>     # NEVER git add -A / git commit -a here
git commit -m "..."
git push                    # then verify origin/main == your HEAD
```

nginx and the enforcement lock chain are the crown jewels on this fleet.
A commit that strips them from the repo is a permanent public security
reduction — restore first, commit second.

## Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| **Stash-pop masks deletion time** | dir mtime = cron run time, not true deletion | A stashing cron (e.g. agent-hermes-cortex-sync) pops the stash, rewriting dir mtimes. The stash commit's parent bounds the true time. |
| **`reset: moving to HEAD` misread as deletion** | reflog reset near suspicious time | That's the stash's internal reset — check `git show --stat <stash-sha>` for what the stash actually captured. |
| **Uncommitted deletions committed accidentally** | `git add -A` sweeps foreign deletions into your commit | Stage explicit paths only when the tree contains deletions you didn't author. |
| **Dropped stash assumed lost** | `git stash pop` then "Dropped refs/stash@{0}" | The commit object is still reachable by SHA until gc — `git cat-file -t <sha>` works. |
| **No-op stash + pop steals a sibling's stash** | `git stash -q` on a CLEAN tree does nothing (no new entry); a later `git stash pop` then pops the TOP of the stack — which on a multi-session host may be ANOTHER session's stash, half-applying it and creating conflicts (2026-08-05: popped `sibling-wip-soul-cortex-skills` while mine was committed). | Verify before popping: `git stash list` (check messages — "sibling-" / "wip-" entries are not yours), or pop by explicit index `git stash pop stash@{N}`. After a no-op stash, confirm the list count did NOT increase. If you half-applied a foreign stash: `git reset --hard HEAD` restores the tree; the foreign stash entry remains intact (pop keeps it on conflict). |
| **Tool-call regex misses commands** | Searching messages.content for `"command"` returns nothing | Tool args live in the `tool_calls` JSON column with escaped quotes — parse with json.loads. |
| **Search_files blind on hidden dirs** | 0 results for `.hermes`, `.hermes-cortex` paths that exist | ripgrep skips hidden dirs by default; use `ls`/`find`/`git ls-files` to confirm absence. |
| **User shell falsely exonerated** | No rm in zsh history | History flushes only on clean exit; reboots lose it. Report the gap honestly, don't claim innocence. |

## Reference
- `references/hermes-forensic-evidence-sources.md` — exact Hermes evidence
  paths (cron output, state.db schema), worked example from the 2026-08-01
  hermes-plugin-lock deletion investigation, and the verified-innocent cron
  pattern.
