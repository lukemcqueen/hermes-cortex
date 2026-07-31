---
name: session-start-discipline
version: 1.1.0
category: devops
description: "Restore cross-session todos, enforce skill-loading discipline at session start"
platforms: [linux, macos]
related_skills:
  - todo-persistence
  - task-start
  - agent-flow
  - change-checklist
---

## Session Start — Mandatory Skill Loading

**You must never `touch` the skills marker.** The enforcer auto-creates a
per-session marker at `~/.hermes-cortex/state/skills-loaded/<session-id>` when
all 9 always-section skills have been loaded via actual `skill_view()` calls.
A bare `touch` creates an empty file that fails content verification — blocking
you until you load the real skills. Each session owns its own marker file, so
concurrent sessions (telegram + cli 1 + cli 2 on one server) never stomp each
other.

## Sequence

Load all 9 always-section skills in this order. The marker follows automatically:

1. `skill_view('task-start')` — bundles the complete pre-task sequence
2. `skill_view('session-start-discipline')` — **this skill** — restore pending todos after always-skills load
3. `skill_view('agent-flow')` — workflow router
4. `skill_view('reasoning-patterns')` — reasoning mode selection
5. `skill_view('reflexion-check')` — self-critique before delivery
6. `skill_view('change-checklist')` — pre-ship verification
7. `skill_view('survey-before-action')` — check existing resources first
8. `skill_view('cortex-preflight')` — repo-specific pre-flight checks
9. `skill_view('agent-contract')` — non-negotiable execution rules

Then restore any pending cross-session todos:

10. `~/.hermes-cortex/scripts/todo-db.py pending` — query DB for pending items
11. If items exist, `todo(todos=<json_items>, merge=true)` — restore to in-memory list

Then proceed to `begin_change()`. The marker is self-verifying — it contains
your session ID, not just a file existence flag.

## Enforcement

- The enforcer blocks ALL write tools without the marker
- **Do NOT touch the marker file** — it will be rejected    
- Load the skills instead; the marker follows

## Self-Verification

After loading all skills, confirm the marker was created:

See also:
- `references/stale-governance-lock-files.md` — stale lock files from
  subagents block the pre-commit hook's session detection
- `references/subagent-dispatch-workaround.md` — how to prevent subagents
  from overwriting the marker when using `delegate_task`
- `references/adversarial-finding-fix-patterns.md` — fixing empty except
  blocks flagged by the adversarial verifier
- `references/bulk-fix-enforcer-bypass.md` — bulk file fix via Python I/O
  when the enforcer blocks per-tool writes

```bash
cat ~/.hermes-cortex/state/skills-loaded/<your-session-id>
# Expected: session:<current-session-id>
```

If the marker is missing or has a different session ID, load one more skill
(call `skill_view(name='<any-loaded>')`) to trigger the auto-create.
Concurrent batching of 9 skill_view calls does NOT trigger the check —
each concurrent call only sees its own addition. A serial 10th call fixes this.

## Known Gap — Date-Format Daemon Session IDs

The enforcer's daemon guard protects sessions with `cron_` or `bg_` prefixes
only. Some sessions have `HERMES_CRON_SESSION=1` but date-format IDs
(`20260730_195730_24f0b3`) — these bypass the guard. The marker gets
overwritten by other concurrent sessions, producing the confusing error:
"8/8 always-section skills loaded" immediately followed by
"session skills not fully loaded".

**Subagents also overwrite the marker.** `delegate_task` runs subagents with
date-format session IDs. When a subagent loads skills, it overwrites your
marker with its own session ID. Your write tools then get blocked.

### Dispatch guidance

When using `delegate_task`, include the marker workaround in the subagent's
context (see `references/subagent-dispatch-workaround.md`). Without it,
subagents will hit the same write-block and fail to apply file changes.

### Symptom to watch for

You loaded all 9 skills. `echo` and `pwd` work fine. But a longer command
like `python3 adversarial-verify.py` gets blocked. The enforcer re-checks
the marker at each `terminal()` call — quick commands pass through before
the re-check catches the missing marker, longer commands don't.

**To confirm:** `cat ~/.hermes-cortex/state/skills-loaded/<your-session-id>` — if
the file is missing or empty, your skills weren't loaded this session (or the
enforcer plugin was redeployed, which resets in-memory tracking).

**Workaround:** Call `skill_view('<any>')` to trigger the enforcer's auto-create
with your current session ID. Note: with per-session marker files (2026-08-01)
another session can NO LONGER overwrite your marker — a blocked write means
*your* session's marker is missing, not that it was stolen.
