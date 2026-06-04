---
name: git-workflow
description: |
  Safe Git workflow for inspecting, staging, committing, reviewing,
  branching, and avoiding accidental overwrite or data loss.

  Triggers when user mentions:
  - "git"
  - "commit"
  - "branch"
  - "diff"
  - "merge"
  - "rebase"
  - "version control"
---

# Git Workflow

## Purpose
Manage changes safely by:
- preserving user work
- making minimal commits
- enabling easy rollback
- keeping history clean and understandable

---

## Core Rule

Never lose or overwrite user changes.

Always inspect before modifying.

---

## Output (STRICT)

```md
## Git Result
What changed

## Files staged
- ...

## Commit
- message:

## Verification
- status:

## Notes
Risks, conflicts, follow-ups
```

---

## Workflow (STRICT)

1. Inspect repo state
2. Understand existing changes
3. Stage only relevant files
4. Create focused commit
5. Verify clean state
6. Report result

---

## Step 1: Inspect State

```bash
git status --short
git diff
git diff --stat
```

Check:

* modified files
* untracked files
* staged vs unstaged changes
* unrelated work

---

## Step 2: Review Changes

```bash
git diff
git diff --cached
```

Confirm:

* changes match intended task
* no debug artifacts
* no accidental edits
* no secrets added

---

## Step 3: Staging Rules

* stage only files related to the task
* do not stage unrelated changes
* use selective staging if needed:

```bash
git add <file>
git add -p
```

---

## Step 4: Commit Rules

Commit must be:

* small and focused
* one logical change
* reversible

---

## Pre-Commit Diff Review

Before staging or committing, inspect the diff for:

```bash
git diff
```

Check for:
- Debug artifacts left behind: `print(`, `console.log`, `debugger`, `TODO`, `FIXME`
- Hardcoded secrets: API keys, passwords, tokens
- Merge conflict markers: `<<<<<<`, `>>>>>>`, `=======`
- Large unintended files: check `git diff --stat`
- Unrelated changes that should be separate commits

Any of these should be fixed before staging.

---

## Commit Message Convention

```txt
<type>: <short description>

Types:
feat:     new feature
fix:      bug fix
refactor: code restructuring
test:     adding/fixing tests
docs:     documentation
chore:    tooling, config, deps
perf:     performance improvement
```

Keep subject under 72 characters. Body (if needed) separated by blank line.

---

## Step 5: Branching

Use branches for non-trivial work:

```bash
git checkout -b feature/<name>
```

Rules:

* do not commit directly to main unless trivial
* keep branches focused
* avoid long-lived branches

---

## Step 6: Verification

```bash
git status
```

Ensure:

* no unintended staged changes
* working tree clean (or understood)
* commits reflect intended change

---

## Conflict Handling

When conflicts occur:

1. inspect conflicting files
2. resolve manually
3. verify logic is correct
4. re-run tests
5. commit resolution

Never auto-resolve blindly.

---

## Rebase / Merge Rules

* prefer rebase for clean history (if safe)
* prefer merge for shared branches
* never rewrite history on shared branches without permission

---

## Safety Rules

* NEVER overwrite user changes
* NEVER delete files without intent
* NEVER commit secrets (.env, keys)
* NEVER force push unless explicitly instructed
* ALWAYS check `git status` before edits

---

## Undo / Recovery

Safe commands:

```bash
git restore <file>        # discard local changes
git reset HEAD <file>     # unstage file
git checkout -- <file>    # restore previous version
```

Dangerous (use only with approval):

```bash
git reset --hard
git push --force
```

---

## Integration with AgentKore

```txt
task-executor
→ change-test-loop
→ git-workflow (commit)
→ code-review
→ release-checklist
```

---

## Anti-Patterns

Avoid:

* committing unrelated changes
* large multi-purpose commits
* skipping diff review
* force pushing casually
* committing without tests passing
* mixing refactor + feature + migration in one commit
* ignoring untracked files

---

## Goal

Ensure every change is:

* intentional
* traceable
* reversible
* safe for collaboration and production