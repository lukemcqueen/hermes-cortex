# Governance Integrity — Non-Negotiable Rules

> **Source:** User correction during Esther session, July 2026. Luke called out that governance was being followed mechanically but not with integrity. These rules are the structural fix.

## The 5 Rules (from SOUL.md Principle #11)

Every governance cycle must satisfy ALL five. If any is violated, the cycle is incomplete.

### Rule 1 — `cache_search` results must be READ and ADDRESSED

Call `cache_search` at the start of every task. **Read the results.** Either:
- Use the context to avoid rework, or
- State clearly why it's not relevant to this task

Checking the box without reading is bypassing. A `cache_search` call followed by ignoring the output is indistinguishable from not calling it at all.

### Rule 2 — One cycle per logical change

Each unrelated change gets its own `begin_change` → `end_change` cycle. Batch-scoring a whole session is not acceptable.

Examples of what should be separate cycles:
- Installing skills (one cycle)
- Fixing a config file (separate cycle)
- Building a cache (separate cycle)
- Updating SOUL.md (separate cycle)

If a session has 10 logical changes but only 2 governance cycles, that's a violation.

### Rule 3 — `feedback_accept` notes must evaluate decision correctness

Training the scoring model requires evaluative notes, not diary entries.

**Wrong (descriptive):**
```
Fixed pre-commit hook DB path. Built 47-embedding cache. Ran evaluator. All layers verified.
```

**Right (evaluative):**
```
DECISION EVALUATION: This change was correct in intent — the old path would cause cycles logged by pre-commit to be invisible to the MCP server queries. FLAWED: I used the same lock for both the path fix and the cache build; these should have been separate cycles. VERDICT: Proceed (MOVE_ON). The gap is acknowledged.
```

Ask three questions before writing:
1. Was the decision to proceed the right call?
2. What would a better version of this change look like?
3. Are there any gaps I need to disclose?

### Rule 4 — Terminal state changes are governed too

The plugin blocks `patch`, `write_file`, `cronjob`, `skill_manage` without a lock. But it **cannot intercept shell commands** like:
- `rm -rf` (deleting files/directories)
- `hermes skills install/uninstall` (modifying skills)
- `git push` (publishing changes)
- `chmod`, `mv`, `cp` via terminal (state changes)
- `sudo` operations

When you perform any of these via terminal, you MUST:
1. Include the operation in the `begin_change` description
2. Acknowledge the governance gap in the `feedback_accept` note
3. Never pretend the terminal operation didn't happen

If the terminal command would be blocked by the plugin if it were a `write_file`/`patch`, it's a governed change.

### Rule 5 — No `end_change` rejection without a confession

`end_change` can reject if no auto-created cycle was found for the task_id (known limitation: `patch` under active lock doesn't auto-create cycles).

When this happens:
```
end_change rejected — no cycle auto-created for this tool type. Force-clearing lock.
```
Then force-clear:
```
rm -f ~/.hermes-cortex/state/.governance-$(basename $(git rev-parse --show-toplevel 2>/dev/null || echo 'generic')).json
```

Never silently force-clear without calling `end_change` first.

## When the User Asks "Have You Done Governance?"

This question means you've visibly skipped or coasted through governance. Do NOT:
- Defend or explain
- Say "I did, here's the proof"
- Make excuses

Instead:
1. **Accept the miss immediately**: "You're right, I was following the mechanics but not the intent."
2. **Run the missed steps** right now — cache_search, reopen cycles, etc.
3. **Fix the structural cause** — update SOUL.md or the relevant skill so it won't happen again.

## Common Failure Modes

| Mode | Symptom | Fix |
|------|---------|-----|
| Checkbox cache_search | Called but never referenced results | Read results, address relevance |
| Batch cycling | 2 cycles for 10 changes | Separate lock per logical change |
| Diary feedback | "Fixed X, did Y" | Write evaluative note instead |
| Terminal blind spot | rm/hermes install/git push with no lock | Acknowledge in feedback note |
| Silent force-clear | Skipped end_change, went straight to rm | Call end_change first, confess rejection |
