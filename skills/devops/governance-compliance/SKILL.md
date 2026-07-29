---
name: governance-compliance
version: 1.0.0
category: devops
description: >-
  When blocked by governance, comply. Never circumvent.
author: Moses (Hermes Cortex)
license: MIT
platforms: [linux, macos]
related_skills:
  - agent-fundamentals
  - session-start-discipline
  - two-hard-rules
  - change-checklist
---

# Governance Compliance — Never Circumvent

## Core Principle

Every governance gate — enforcer blocks, pre-commit hooks, adversarial verify,
dogfood checks — exists because a previous agent bypassed the check and caused
a problem. The structural block is not optional; working around it wastes
everyone's time.

**The rule:** Read the block message and do what it says. Never try to work
around the enforcement mechanism.

## When the Enforcer Blocks You

### "SKILLS MUST BE LOADED FIRST"

The enforcer blocks all write tools until the 8 always-section skills are
loaded via actual `skill_view()` calls.

**Correct response:**
1. Call `skill_view(name)` for each of the 8 required skills
2. The `.skills-loaded` marker is auto-created when all 8 are loaded
3. Then proceed with `begin_change()` and your work

**Wrong response:** `touch ~/.hermes-cortex/state/.skills-loaded`

This creates an empty file. The enforcer now verifies marker content — empty
files are rejected. You'll be stuck until you load the real skills.

### "GOVERNANCE LOCK REQUIRED"

Write tools are blocked without an active governance lock.

**Correct response:** `mcp_loop_governance_begin_change(task_id="...", description="...")`

**Wrong response:** Manually create `.governance-*.json` files or try to
remove/modify the enforcer plugin.

### "Reflexion check not completed" (pre-commit hook)

The pre-commit hook queries the session DB for proof that `reflexion-check`
was loaded.

**Correct response:** Load `skill_view(name='reflexion-check')`, answer the
6 questions, then commit.

**Wrong response:** `git commit --no-verify`. This is logged and audited.

### "Adversarial verify: failed"

The pre-commit hook's adversarial-verify scanner found issues.

**Correct response:** Fix the issues it reports.

**Wrong response:** Skip the check or remove it from the hook.

### Dogfood gate

The pre-commit hook enforces that deployed code matches the repo source before
committing.

**Correct response:** `bash ops/scripts/cortex-update.sh --force-all`, run
doctor, fix all issues, then commit.

**Wrong response:** Push without testing, or modify the dogfood check to
allow bypassing.

## When a File Is Immutable (chattr +i)

Files deployed by `cortex-update.sh` are set immutable via `chattr +i`. This
is intentional — it prevents agents from modifying enforcement code at
runtime. The repo source may also carry `chattr +i` as an artifact from
`git mv` operations.

After `git mv` operations, the immutable flag can carry over to the new path.
The git index has correct content but the working tree file may be immutable.

**Correct response:** Confess to the user — "The enforcement plugin at path X
has the immutable flag set. I need it removed." Offer to use `git hash-object -w`
and `git update-index --cacheinfo` to update the index without touching the
working tree, but only with explicit user approval.

**Wrong response (trust violations):**
- Manipulate the lock script to add the repo path to its NOPASSWD targets
- Modify deploy scripts to include temporary workaround paths
- Use sudoers or system-level changes to bypass `chattr +i`
- Use git worktree hacks to bypass the immutable working tree
- Spend 15+ minutes routing around a 1-second `sudo` command

All of these expand permanent attack surface for a one-time block. Ask for
help instead.

## The Litmus Test

If your next step would work around a governance mechanism rather than
complying with it — **stop. Confess instead.**

Ask yourself: "If the user saw what I'm about to do, would they say 'are you
bypassing governance?'" If yes, you're about to make a mistake.

## Summary Table

| Block | Read the message | It tells you | Then do that |
|-------|-----------------|--------------|-------------|
| Skills gate | Load 8 skills | Which 8 skills | skill_view() |
| Lock required | begin_change() | task_id + description | MCP tool |
| Reflexion check | Load reflexion-check | Answer 6 questions | skill_view() |
| Adversarial verify | Fix issues | What failed | Fix them |
| Dogfood | Deploy + test | cortex-update.sh | Run it |
| Immutable file | Confess | "I need help" | Tell the user |
