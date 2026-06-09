---
name: session-manager
description: "Session management skill — checkpoint/restore, context compression, progress tracking, and recovery for maintaining continuity across agent sessions."
version: 1.1.0
category: software-development
source: hermes-cortex
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [session, checkpoint, restore, context, progress, tracking, recovery, continuity, state, resume]
    related_skills: [agent-flow, memory-architecture, subagent-driven-development, writing-plans]
---

# Session Manager — Continuity & Recovery

Use this skill to manage long-running or interrupted agent sessions. It provides structured patterns for saving progress, compressing context when approaching token limits, tracking what's been done, and recovering gracefully after interruptions.

---

## Principles

1. **Save before you leave** — checkpoint at every natural boundary (task complete, breakpoint hit, user disconnects).
2. **Compress before you overflow** — summarize and prune before hitting context limits so no state is lost.
3. **Track visibly** — maintain a running progress list so you (and the user) always know where things stand.
4. **Resume safely** — provide enough context for a fresh session to pick up exactly where the previous one stopped.

---

## 1. Checkpoint / Restore

Save a compact snapshot of session state at key milestones. Each checkpoint captures what was accomplished, what's pending, and any critical decisions or blockers.

### When to checkpoint

- **Task complete** — after delivering a finished artifact or answer.
- **Milestone reached** — after a logical sub-goal (e.g., "all tests pass", "schema designed").
- **Before any risky operation** — before a large refactor, destructive migration, or complex merge.
- **On user request** — if the user says "save progress", "checkpoint", or "remember this".
- **On disconnect** — if you detect a mid-turn interruption or session timeout.

### Checkpoint format

Write a checkpoint to one of these locations (prefer first):

1. **`project_current_session.md`** (repo root, committed to git) — for ongoing work tracked in a shared repo. Update the Session Notes section.
2. A dedicated `session-checkpoint-{timestamp}.md` file — for private or long-running work.
3. The session's working MEMORY.md — for quick inline saves.

```markdown
## Session Checkpoint — YYYY-MM-DD HH:MM UTC

### Objective
What the session was hired to do (one sentence).

### Completed
- [x] Task or sub-task description (file, path, or artifact)
- [x] Another completed item

### In Progress
- [ ] Current active work item
- [ ] Next step after current item

### Blocked
- Description of blocker (link to error, decision needed, dependency)

### Key Decisions
- Decision / rationale (e.g., "Chose SQLite over PostgreSQL for local dev simplicity")
- Another decision

### Context Snapshot
- Files modified or created: [list paths]
- Commands run with relevant output: [one-liner each]
- Tools used: [checkpoint, search, write, patch, etc.]
```

### Restore

When starting a new session that follows a previous one:

1. **Find the latest checkpoint** — search for `session-checkpoint-*` or look in `MEMORY.md`.
2. **Read the checkpoint** — get the context snapshot.
3. **Load the objective** — confirm with the user what to resume.
4. **Re-verify file state** — ensure working tree hasn't changed since checkpoint (e.g., `git status`, `diff` on key files).
5. **Pick up from "In Progress" or "Blocked"** — continue exactly where the prior session left off.

---

## 2. Context Compression

When approaching token limits (typically >70% of your context window), proactively compress before you lose the ability to reason.

### Signs you need to compress

- Responses start getting truncated or incomplete.
- You see errors about context length or max tokens.
- You're holding more than ~20 tool results in memory without summarising.
- The conversation history spans more than a few back-and-forth exchanges with long file reads.

### Compression procedure

1. **Summarise tool outputs** — replace long file reads, command outputs, or search results with a 1–3 sentence summary of what they contained.
2. **Prune resolved sub-discussions** — if a side conversation about a dependency install was resolved, drop the tool results and keep only the outcome.
3. **Consolidate progress** — if you've been tracking progress inline, collapse multiple granular items into milestone-level entries.
4. **Snapshot to checkpoint** — write a checkpoint (see §1) so you have a recovery point after the compression.
5. **Restart or hard-reset** — if available, start a fresh session and load the checkpoint. Otherwise, discard the oldest tool results that are no longer referenced.

### What NOT to compress

- **User's original request** — always keep the goal visible.
- **Active error messages or failures** — these are what you're working on.
- **The latest checkpoint** — this is your recovery anchor.
- **Any critical decision record** — the "why" behind a direction change.

---

## 3. Progress Tracking

Maintain a running, visible list of session progress. Update it after every meaningful action.

### Progress list format

```markdown
### Session Progress

#### ✅ Completed
1. Understood the problem space — identified key requirements
2. Designed the solution architecture — chose library X, decided on pattern Y
3. Implemented core module — wrote `src/core.py`
4. All unit tests pass — 24/24 passed

#### 🔄 In Progress
- Writing integration tests for the API layer (3 of 8 done)

#### ❌ Blocked
- Can't test against staging — no staging environment running; user needs to deploy first

#### 📋 Next Up
- Complete integration tests
- Write documentation
- Logging and error handling pass
```

### When to update

- After every **completed task** — mark it done.
- When you **start something new** — add it to In Progress.
- When you **hit a blocker** — move item to Blocked and note why.
- Before **every checkpoint** — sync the progress list first.

### Where to keep it

- In the **top of your working memory** (e.g., first section of MEMORY.md or a pinned summary at the top of the conversation).
- If no persistent memory file is available, keep it as the first thing in your system prompt or as a recurring message to yourself.

---

## 4. Recovery (Session Interruption)

If a session is interrupted (timeout, crash, manual stop, user walks away), the next session must be able to resume with minimal friction.

### Recovery file

Write a `SESSION_RECOVERY.md` in the working directory or append to MEMORY.md with:

```markdown
## Session Recovery — YYYY-MM-DD HH:MM UTC

### Last Known State
- Checkpoint: `session-checkpoint-{timestamp}.md` (or latest inline checkpoint)
- Working branch/tag: `main` / `feature/xyz`
- Last command run: `python -m pytest tests/`

### Files open or being edited
- `src/core.py` — was adding error handling
- `tests/test_core.py` — was writing test cases

### Reproducer
Steps to reproduce any failure or blocker the session was investigating:
1. `git checkout feature/xyz`
2. `docker compose up -d`
3. `python -m pytest tests/test_core.py::test_foo` — expects PASS, got FAIL

### Immediate Next Step
What the very next action should be:
> Run the failing test again, inspect the traceback, then fix `src/core.py` line 47–55.

### Uncommitted Changes
```diff
# git diff summary — key changes not yet committed
```

---

If no recovery file was written before interruption, reconstruct context by:
1. Checking `git reflog` or `git log --oneline -5` for recent commits.
2. Grepping the workspace for any recent or partial files (`find . -mmin -60`).
3. Checking shell history (`history | tail -50`) for the most recent commands.
4. Asking the user: "The session was interrupted. What were you working on?"

---

## Quick Reference

| Situation | Action |
|---|---|
| Task just completed | Write a checkpoint |
| About to do something risky | Write a checkpoint |
| Approaching token limit | Compress → checkpoint → refresh |
| User says "save progress" | Write a checkpoint |
| Session interrupted | Write a recovery file (or reconstruct) |
| New session, need to resume | Find latest checkpoint → load → verify → continue |
| Progress feels muddled | Update progress list before next action |
| Multiple items in flight | Prioritise → move blocked to 📋 Next Up |

---

## Anti-Patterns

- ❌ **Checkpointing everything** — don't checkpoint after every single tool call; only at natural boundaries.
- ❌ **Compressing too early** — don't compress if you have <50% context used; you lose fidelity for no benefit.
- ❌ **Losing the user's goal** — always keep the original request visible even after compression.
- ❌ **Orphan checkpoints** — clean up old checkpoints after a session is truly done (user confirms completion).
- ❌ **Skip recovery file because "I'll remember"** — you won't. Write it down.
