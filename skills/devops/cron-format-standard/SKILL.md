---
name: cron-format-standard
version: 3.0.0
category: devops
description: >
  Standard three-phase output format for ALL LLM-driven cron jobs.
  Uses concrete examples — not annotated placeholders. Crons follow
  this by matching the structure line for line. Includes the full
  workflow for agents to apply, commit, push, and deploy.
---

# Standard Cron Output Format

Every LLM-driven cron delivery must follow this exact structure.

## The Template (copy this structure exactly)

Use your cron's name, ID, and content. Keep everything else (dashes, colons, spacing, line breaks) identical.

```
<cron-name> (<cron-id>) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — <Phase Title>: <one-line summary>
- <evidence bullet>
- <evidence bullet>

Phase 2 — <Phase Title>: <one-line summary>
- <evidence bullet>

Phase 3 — <Phase Title>: <one-line summary>
- <evidence bullet>

Result: <one-line verdict>

📊 <model> (<provider>) | <cost>/run ≈ <monthly>/mo
```

## Example (health check cron)

```
agent-auto-remediate (e9341ea181b3) [2026-07-03 10:01 KST]
-------------

Phase 1 — Cron jobs: All 17 jobs healthy. last_status: ok across the board. hermes-update has a stale delivery error from yesterday — script itself succeeded, transient Hermes bug, not actionable.

Phase 2 — Inbox: Empty.

Phase 3 — System resources:
- Disk: 37% (552G free)
- Memory: 46GB available of 62GB
- Swap: 2MB / 2GB
- Load: 2.04 (moderate)

Result: Nothing to fix. All nominal.

📊 deepseek-v4-flash (opencode-zen) | $0.006/run ≈ $0.18/mo
```

## Example (remediation cron — silent when nothing to do)

```
agent-fixer (ba1655060ea3) [2026-07-03 12:01 KST]
-------------

Phase 1 — Issues found: 2 active issues detected
- [nginx] port 13001 unreachable
- [disk] /var/log at 85% capacity

Phase 2 — Fixes applied: 2 of 2 resolved
- nginx: service restart succeeded
- disk: log rotation freed 2.3GB

Phase 3 — Unresolved: 0 remaining

Result: All issues fixed. System nominal.

📊 deepseek-v4-flash (opencode-zen) | $0.006/run ≈ $2.18/mo
```

If nothing to report: output exactly `[SILENT]` (no format needed).

## Example (content generation cron — bible reading)

```
agent-daily-bible-reading (6d0fa87382ad) [2026-07-04 01:01 KST]
-------------

Phase 1 — Scripture covered: 1 Kings — "Give your servant a discerning heart"
- Focused on Solomon's request for wisdom at Gibeon
- The hinge: Solomon asked for discernment, not wealth or victory

Phase 2 — Insight distilled: Wisdom must precede every action
- Every decision requires discernment, not speed or force
- The request for wisdom before action prevents costly mistakes

Phase 3 — SOUL.md updated: insight appended to Scripture Insights section
- Added 1 Kings entry with application note

Result: Daily scripture entry for 1 Kings appended.

📊 qwen2.5-coder:3b (custom:ollama-local) | free
```

---

# For Agent Developers: Full Workflow

When creating a new LLM cron or updating an existing one to use the standard format:

## Step 1 — Build the example block

Create three realistic-looking phases with concrete values matching the cron's purpose. Use the examples above as templates. **Never use annotated placeholders** (`<Title>`, `<one-line summary>`, `<Book Name>`) in the example — LLMs mimic concrete text, they interpret placeholders loosely.

## Step 2 — Update the cron's prompt

Use the `cronjob` API to update it:

```
cronjob action=update job_id=<id> prompt="<full prompt>"
```

The prompt must end with:

```
## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values.
Everything else stays: dashes, colons, spacing, line breaks.

<cron-name> (<cron-id>) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — <real looking content>: <summary>
- <bullet>
- <bullet>

Phase 2 — <real looking content>: <summary>
- <bullet>

Phase 3 — <real looking content>: <summary>
- <bullet>

Result: <verdict>

📊 <model> (<provider>) | <cost>/run ≈ <monthly>/mo

If nothing to report: output exactly [SILENT]
```

## Step 3 — Verify the cron runs correctly

```
cronjob action=run job_id=<id>
```

Then check the output file at `~/.hermes/cron/output/<job-id>/<latest>.md`. Look at the actual LLM response section — verify it matches the header/dashes/phases/Result/footer structure.

If the output doesn't match, the example in the prompt is too abstract — add more concrete text.

## Step 4 — Commit and push skill changes (repo changes only)

If you updated this skill (`cron-format-standard`) in the repo at `skills/devops/cron-format-standard/SKILL.md`:

```bash
cd ~/hermes-cortex
git add skills/devops/cron-format-standard/SKILL.md
SKIP_SCORE=1 git commit -m "skill: cron-format-standard — <what changed>"
SKIP_PRE_PUSH=1 git push origin main
```

**About the SKIP flags:**
- `SKIP_SCORE=1` — bypasses the pre-commit hook (which requires a governance `begin_change` MCP tool not available in cron mode or script context)
- `SKIP_PRE_PUSH=1` — bypasses the pre-push hook (same requirement)
- Both are documented in the repo's pre-commit hook and safe to use for routine cron-related commits

**Important:** The `cronjob` API updates are NOT repo changes — they modify `~/.hermes/cron/jobs.json` directly. No git operation needed for prompt-only changes.

## Step 5 — Propagate to other agents

The skill at `src/skills/` is synced automatically to all agents on the next `cortex-update.sh` run. The `sync_skills()` function in `cortex-update.sh` copies `src/skills/` → `~/.hermes/skills/` incrementally (only changed files). You do NOT need to manually copy anything.

To force an immediate sync on another agent:
```bash
# On the target agent's machine:
bash ~/hermes-cortex/src/scripts/cortex-update.sh
# OR just:
bash ~/hermes-cortex/install.sh --skip-existing
```

## Step 6 — Score the change (loop governance)

If the change included a repo commit:
```
mcp_loop_governance_cycle_query task_id="<commit-subject>"
mcp_loop_governance_feedback_accept id=<N> note="<summary>"
```

If the change was cron-only (no repo commit), note it in your session but there's no pre-commit hook cycle to score.

---

## Critical implementation lesson

**LLMs follow concrete examples more faithfully than annotated placeholder templates.**

Do NOT write this in a cron prompt:
```
Phase 1 — <Title>: <one-line summary>
- <evidence>
```

The LLM interprets `<Title>` and `<evidence>` loosely — different phrasing, extra text, missing dashes, reordered elements. The LLM treats `<...>` as suggestions, not constraints.

Instead, give a concrete example with real-looking values:
```
Phase 1 — Issues found: 2 active issues detected
- [nginx] port 13001 unreachable
- [disk] /var/log at 85% capacity
```

The LLM mimics the *structure* while replacing values. This is the difference between "instruct the LLM" and "show the LLM."

---

## Rules

1. **Concrete examples only** — never use annotated placeholders (`<Title>`, `<value>`, `<one-line summary>`) in the example block
2. **Header always first line** — `<name> (<id>) [YYYY-MM-DD HH:MM KST]` then `-------------`
3. **Phases are numbered** — Phase 1, Phase 2, Phase 3 minimum (add Phase 4+ if needed)
4. **Phases start with a colon** — `Phase N — Topic: Summary on same line`
5. **Result line always before footer** — `Result: <one-line verdict>`
6. **Footer always last line** — `📊 <model> (<provider>) | <cost>/run ≈ <monthly>/mo` (never append cron name after cost)
7. **[SILENT]** — only acceptable output when nothing to report for watchdog/checker crons
