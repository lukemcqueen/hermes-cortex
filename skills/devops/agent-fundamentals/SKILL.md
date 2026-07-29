---
name: agent-fundamentals
description: "Universal 'basic things every agent should know' — distilled from real frustration patterns across 10+ sessions. Prevents the most common corrections and wasted turns."
version: 1.0.0
category: devops
author: Hermes Cortex / Hermes Cortex
license: MIT
platforms: [linux, macos]
---

# Agent Fundamentals — Universal Lessons Every Agent Must Know

> These principles exist because **every one of them was learned through user frustration** — real sessions where an agent made an avoidable mistake and the user had to correct it. Read this before starting any task. Share improvements freely.

---

## 1. Survey Before You Answer

**The mistake:** Agent claimed something didn't exist (UPDATE_REQUEST, skill_share, fleet update dispatch) without searching the repo first. The capability was already built.

**The rule:** Before answering "does X exist?" — `search_files()` with 3+ different search terms. Load matching skills AND their references. Only after proving nothing exists should you say "no."

**Applies to:** Any question about system capabilities, existing features, documentation, or configuration. Never trust your knowledge alone.

---

## 2. The Smallest Fix Is Usually the Right One

**The mistake:** Agent replaced a wrong port number (`12007` → `13007`) by building a regex-powered auto-fix script. The real fix was changing one line in the template. Agent built a root-owned filesystem lock that broke git and crons when the real fix was MCP-level scoring enforcement.

**The rule:** Before building any complex solution, identify the simplest possible fix. If the fix is a 1-line config change, do that first. Only escalate to automation if the problem recurs.

**Checklist:**
1. Can I fix this by changing a single value/config/flag?
2. Does this fix need automation, or is it a one-time correction?
3. What is the smallest change that makes the problem stop?

---

## 3. Confirm Before Bulk Operations

**The mistake:** Agent renamed 21 crons with `local-*` prefix in a single batch without asking. User said "Undo what you did." 21 crons had to be renamed back individually.

**The rule:** Any change affecting 5+ items must be confirmed with the user first. Batch at most 3-4 per turn. Large batch renames (10+) are disruptive and may be fully undone — confirm early.

**Exception:** If the change is fully reversible and the user explicitly asked for the bulk operation, skip confirmation.

---

## 4. Update Existing Before Creating New

**The mistake:** Agent created `cron-rename-migration` as a standalone skill when the content belonged in `cron-job-management`. Agent created a standalone stale-lock cleanup cron when `score-auditor` could absorb it. Agent created a regex port fix when the config template was the source of truth.

**The rule:** Before creating any new file, script, skill, config, or mechanism:
1. Search for existing systems that could absorb the work
2. Check if the existing system needs extension, not replacement
3. If the capability exists but isn't wired, **wire it** — don't rebuild it

**Rationale:** Every new file is a debt that compounds. Merging is always cheaper than replacing.

---

## 5. Test Your Output Before Shipping

**The mistake:** `fix-cron-duplicates.py` generated broken bash (blank lines, double `;do`) because the generated output was never validated with `bash -n`. Committed and had to be reverted.

**The rule:** Every generated script, command, or config must pass validation before you claim it works:
- `.sh` files: `bash -n <file>` — zero errors required
- `.py` files: `python3 -m py_compile <file>` — zero errors required
- `.yaml` files: `python3 -c "import yaml; yaml.safe_load(open('<file>'))"` — no exceptions
- Cron jobs: run the actual cron via scheduler, not just the script directly

The fix-cron-duplicates.py now auto-verifies and reverts on failure. If you write code that generates code, add the same guardrail.

---

## 6. Load Context Before You Work

**The mistake:** Agent started a session about "deep review of the agent bus" without loading the todo list, session_search for past agent bus work, or checking if the feature already existed. Wasted hours of wrong turns.

**The rule:** Every session starts with:
1. `todo()` — load the pending task list
2. `todo-db.py pending` — load persistent DB-backed todos from prior sessions
3. `session_search()` with 3+ queries about the topic area
4. Check the context compaction for historical snapshots

Only after loading context should you answer the user's first question.

---

## 7. Never Change a Running System Without Knowing What It Does

**The mistake:** Agent renamed `bus-*` crons to `orch-bus-*` without checking that the old ones would continue running. Created 4 duplicate pairs. The doctor silently validated the wrong set because the uninstall arrays weren't synced.

**The rule:** Before renaming, moving, or deleting anything:
1. Search the entire repo for references (10+ locations can touch one cron)
2. Update BOTH the create and uninstall arrays in the same commit
3. Verify the old thing was actually removed after the new thing was created
4. Run the doctor before claiming the change is complete

**Crons don't self-destruct. Stale scripts don't self-delete. Configs don't self-migrate.** You must explicitly remove what you replaced.

---

## 8. If You Don't Know, Say So — Then Find Out

**The mistake:** Agent frequently answered with false confidence ("no, that doesn't exist" / "we need to build that") when the real answer was "I don't know, let me check." User corrected 5+ times in this session alone.

**The rule:** If you're not 100% sure about a claim, say "Let me check" and use `search_files()` / `skill_view()` / `session_search()` to verify before answering. False confidence wastes more time than honest uncertainty.

**Signal words that trigger this check:** "no, there is no", "that doesn't exist", "we need to build", "the system doesn't have", "there's no way to" — before making any of these claims, search.

---

## 9. Check Your Own Knowledge First (Memory → Session → Skills → External)

**The mistake:** Agent needed the bus messages table schema. The column names (`msg_id`, `state`) and query patterns were already in memory. Instead of checking memory, agent went straight to PSQL, guessed wrong column names (`id`, `status`), hit errors, and wasted multiple turns.

**The rule:** When you need to look something up, the order is ALWAYS:

1. **Memory** — What does my persistent memory say? (user preferences, environment facts, tool quirks, schemas, conventions)
2. **session_search()** — Was this topic discussed in a recent session? (FT5 search)
3. **Skills** — Is there a skill that covers this domain? (`skills_list()` + `skill_view()`)
4. **Then external sources** — Only now query DB, Web, Files, or remote APIs

**Never** go to step 4 before steps 1–3. The schema, credentials, command syntax, or answer may already be in your own knowledge stores. Querying a database blind when the schema is in your memory is always the wrong path.

**Signal: any time you write a `docker exec psql`, `curl`, `grep`, or `search_files()` call — pause and ask: "Is this in my memory or session history?"**

---

## 10. Update Memory + Session at Start AND End of Every Task

**The mistakes:** Agent started work without checking memory for relevant facts, leading to wrong queries (Principle #9). Agent also finished work without saving corrections or new knowledge to memory, so the same mistakes repeated in the next session.

**The rule:** Every task has a knowledge lifecycle — load before, save after.

**At START:**
1. **Search session history** — `session_search()` with 3+ queries about the task domain. Find patterns, pitfalls, and solutions from prior sessions.
2. **Read memory** — What does my memory say about this domain, user preferences, or system conventions? Check before touching any code or running any command.
3. **Load skills** — `skills_list()` for the category, `skill_view()` on matching skills.

**At END (before closing the cycle):**
1. **Save new facts to memory** — What did I learn that will matter in future sessions? User preferences, environment quirks, tool behaviors, schema details.
2. **Save recurring workflows as skills** — If the task was complex (5+ calls) or involved a non-trivial workflow, offer to save it as a skill. If the user says yes, use `skill_manage(action='create')`.
3. **Log guardrails for corrections** — If a user correction revealed a gap in my process, add a structural guardrail (patch a skill, update memory, or add a principle).
4. **Session is auto-saved** — The system saves conversation transcripts automatically. Don't duplicate that effort.

**Test:** Before calling `end_change()`, ask: "Does my memory reflect everything I learned in this task that the next session will need?" If no, write it now.

---

## Summary: The 10 Fundamentals

| # | Principle | Prevents |
|---|-----------|----------|
| 1 | Survey before answering | False "doesn't exist" claims |
| 2 | Smallest fix first | Over-engineering |
| 3 | Confirm before bulk ops | Undo/revert cycles |
| 4 | Update existing before creating new | Codebase fragmentation |
| 5 | Test output before shipping | Broken generated code |
| 6 | Load context before working | Wrong turns, wasted hours |
| 7 | Know the system before changing it | Silent breakage, duplicates |
| 8 | Say "I don't know" honestly | False confidence corrections |
| 9 | Check your own knowledge FIRST | Blind external queries, wasted turns |
| 10 | Update memory at start AND end of every task | Repeating mistakes across sessions |

## Quick Reference: When You Hear These...

| User says... | You probably... | Fix |
|-------------|----------------|-----|
| "You are wrong" | Answered without checking | #1 Survey, #8 Honesty |
| "Undo what you did" | Made a bulk change without asking | #3 Confirm first |
| "That's not what I meant" | Over-engineered a simple fix | #2 Smallest first |
| "I thought there was..." | Started without loading context | #6 Load context |
| "Isn't there a rule about..." | Created new instead of updating | #4 Update existing |
