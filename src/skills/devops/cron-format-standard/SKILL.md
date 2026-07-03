---
name: cron-format-standard
version: 2.0.0
category: devops
description: >
  Standard three-phase output format for ALL LLM-driven cron jobs.
  Uses concrete examples — not annotated placeholders. Crons follow
  this by matching the structure line for line.
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

## Rules

1. **No annotated placeholders** — use concrete examples showing real text in every field
2. **Header always first line** — `<name> (<id>) [YYYY-MM-DD HH:MM KST]` then `-------------`
3. **Phases are numbered** — Phase 1, Phase 2, Phase 3 minimum (add Phase 4+ if needed)
4. **Phases start with a colon** — `Phase N — Topic: Summary on same line`
5. **Result line always before footer** — `Result: <one-line verdict>`
6. **Footer always last line** — `📊 <model> (<provider>) | <cost>/run ≈ <monthly>/mo` (no cron name in footer)
7. **[SILENT]** — only acceptable output when nothing to report for watchdog/checker crons
