---
name: session-start-discipline
version: 1.0.0
category: devops
description: "Enforces the correct session-start sequence: always skills loaded via skill_view BEFORE begin_change. Prevents the 'lock first, context never' failure pattern."
---

# Session-Start Discipline

## When to Load This Skill

Load this skill at session start alongside `task-start`. It documents the correct ordering of the pre-work sequence for Hermes Cortex agents — a lesson learned from repeated correction.

## The Core Rule

**The MANDATORY SESSION-START RITUAL in SOUL.md overrides the task-start skill's prescribed order.**

| Source | Prescribed Order | Status |
|--------|-----------------|--------|
| `task-start` skill | begin_change → load skills | ❌ Do NOT follow |
| SOUL.md ritual | task-start → load always skills → choose reasoning → classify → load on-task → survey → preflight → **begin_change** | ✅ Mandatory |

The governance lock opens LAST, not first. Calling `begin_change` before loading all always skills is a trust violation.

## The 10-Step Always Skills Sequence

After `skill_view('task-start')`, your next tool calls MUST be, in this EXACT order:

1. **`skill_view('agent-flow')`** — workflow router
2. **`skill_view('reasoning-patterns')`** — reasoning selection
3. **`skill_view('reflexion-check')`** — self-critique
4. **`skill_view('change-checklist')`** — pre-ship verification
5. **`skill_view('session-start-discipline')`** — this skill (self-load)
6. **`skill_view('fix-without-asking')`** — zero-ask guardrail
7. **`skill_view('agent-contract')`** — execution rules
8. **`skill_view('survey-before-action')`** — survey discipline
9. **`skill_view('cortex-preflight')`** — repo-specific checks
10. **`skill_view('self-improvement-pipeline')`** — correction-to-guardrail

After these 10:
- Select reasoning pattern
- **Classify with agent-flow to determine the task's domain** (e.g. documentation, infra, devops, data)
- **THEN call `skills_list()` for the task domain and load every matching skill** — if your domain is not a category, search with 3+ related terms. Every matching skill MUST be loaded with `skill_view()` before you write any code or create any file. A skill not loaded is a mistake waiting to happen.
- Load on-task skills from skills.yaml
- **Run `cronjob(action='list')` and `search_files()` with 3+ terms to survey existing systems BEFORE creating any new ones** — see `references/survey-before-creating.md`
- **THEN** call `begin_change`

## Self-Verification

If you find yourself at `begin_change` and any of the 10 skills above were NOT loaded via `skill_view()` this session, you skipped the ritual. Stop, close the current lock attempt, load the missing skills, then re-open.

**Mid-session recovery:** if you're already deep in a task when you realize the violation, see `references/recovery-from-violation.md` for the step-by-step recovery procedure (load missing skills in-place, add guardrail, commit the fix).

## Commit Pipeline Discipline — Don't Rush the Close

**The session-end commit pipeline is as important as the session-start ritual.** Rushing through it defeats governance. Traps observed during governance stress-gap closure (2026-07-27):

### Trap 1: `--no-verify` creates an unpushable commit

The pre-commit hook checks for the `.reflexion-done` token at `~/.hermes-cortex/state/.reflexion-done`. When you skip it with `--no-verify`:

1. The sentinel file is missing, so the commit creates a `no-verify-log.json` entry
2. The **pre-push hook detects this** and blocks the push
3. You're stuck: can't push, can't undo without a reset

**Correct commit sequence:**
```bash
# 1. Before first commit of the session, create the reflexion token
touch ~/.hermes-cortex/state/.reflexion-done

# 2. Stage your files
git add <files>

# 3. Commit normally — hook finds the token and passes
git commit -m "..."
```

**Recovery from a stuck --no-verify commit:**
```bash
# Reset soft to keep staged changes
git reset --soft HEAD~1
# Create the missing token
touch ~/.hermes-cortex/state/.reflexion-done
# Re-commit through the hook
git commit -m "..."
```

### Trap 2: `SKIP_DOC_AUDIT=1` means docs aren't updated

The doc audit warns when staged `.md` file changes aren't reflected in `DOCS-INDEX.md`. `SKIP_DOC_AUDIT=1` silences the warning but does not fix the audit trail. A future agent discovers the stale index entry.

**Correct approach:** Write the `DOCS-INDEX.md` entry for the changed file. The env var exists for emergencies only — if you're using it, you're accumulating documentation debt.

### Trap 3: The adversarial scanner runs at A2, not A1

The pre-commit hook runs `adversarial-verify.py` at **A2 level** (`--level A2`), not A1. Files that pass at A1 may fail at A2. Common A2 findings:

| Finding | Severity | Typical cause |
|---------|----------|--------------|
| `error-swallow` (empty except block) | High | `except Exception: pass` — should have a log call |
| `input-fuzzing` parameter=None | Medium | Function default None for required param |
| `input-fuzzing` extreme input | Info | Unvalidated string/port from sys.argv |

**If the findings are in files you did NOT create** (pre-existing — you only changed a minor detail like a port number):
- **Do NOT stage those files** for commit alongside your changes
- Leave them for a separate cleanup task
- Trying to `--no-verify` past them adds a governance-violating commit for no benefit

**If the findings are in files you created or substantively changed:**
- Fix the findings (wrap empty except blocks with a log call, validate inputs)
- Re-run the scanner to confirm A2 passes

**Manual pre-flight before commit:**
```bash
cd ~/hermes-cortex
git diff --cached --name-only | while read f; do
  python3 ops/scripts/quality/adversarial-verify.py --file "$f" --level A2 --gate || echo "  ❌ $f needs attention"
done
```

### Trap 4: Pre-existing findings in files you're "just touching"

When your change to a file is minimal but the file has pre-existing A2 findings:

1. The findings pre-date your change
2. Staging that file triggers the adversarial scan on the **whole file**, not just your diff
3. The commit is blocked, and you're tempted to bypass
4. **Correct response:** unstage that file, commit only your actual changes, leave the pre-existing findings for a separate fix cycle
5. If the user wants those files committed, note the pre-existing findings and offer to fix them in a follow-up

## Exception — Principle 2

Principle 2 (Be Proactive) says `begin_change` is your first action when you discover a fixable issue **mid-task**. This applies AFTER the session-start ritual is complete. The ritual governs the start of every new task. Principle 2 governs execution within a running task. Both are enforced — the ritual first, then Principle 2.

## Why This Exists

The task-start skill says "step 2: begin_change, step 3: load always skills." But agents that follow this order open the lock, start working, and never return to step 3. The context required to work correctly (reasoning patterns, workflow classification, pre-flight checks) never gets loaded. By reordering the sequence so that begin_change is the LAST prep step instead of the second one, the agent arrives at the governance lock with full context.
