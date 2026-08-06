# Mycortex Dream → Todo Bridge — Design & Requirements

> Status: **implemented** (2026-08-06) · Author: kustos (cisnet02), at Luke's request — "both would be useful."
> Supersedes: nothing — this is a new optional layer ON TOP of the dream
> layer (`docs/design/mycortex-dream-layer.md`).

## Why

The dream layer (3 tiers, `install-dream-crons.sh`) writes serendipity back
into the brain — but dreams currently **inform, they don't task**. A dream
that surfaces a knowledge gap ("the brain knows nothing about X") or implies
an action ("verify the deepseek rollout") dies in a markdown file unless a
session happens to re-read it.

The todo system already exists and is durable: `todo-db.py` → `bus.todos`
(Postgres on `mycortex-postgres`, fleet-visible, restored at session start via
`todo-db.py pending`). This bridge makes dreams *actionable* by turning a
subset of dream output into todo items.

Two mechanisms, both wanted by Luke:

- **Option A — Knowledge-gap → learning todo** (monthly tier): zero-hit gap
  topics become "learn X" todos.
- **Option B — Insight triage** (all tiers): an insight that implies a
  concrete, verifiable next action becomes a todo.

## Non-goals / guardrails

- **Dreams stay dreams.** The bridge is additive — it never replaces the
  mandatory write-back (dream file + INDEX append). A dream that becomes a
  todo must ALSO be written to the brain.
- **No todo spam.** Caps + dedup below are hard requirements, not suggestions.
  A serendipity cron that floods the todo list is worse than one that adds
  nothing.
- **No cross-tenant writes.** Todos are attributed to the PROFILE that owns
  the dream (`--agent <profile>`), never hostname, never another profile.
- **Removability preserved.** All changes live in `install-dream-crons.sh`
  prompt text only. No new scripts, no doctor expected-list changes, no
  schema changes. `--uninstall` behavior unchanged.
- **Cost floor.** `todo-db.py add/list` are local psql calls — negligible
  tokens. Model/run cost stays ≈ $0.006/run.

## Existing plumbing (verified 2026-08-06)

| Piece | Reality |
|---|---|
| Todo DB | `bus.todos` on `mycortex-postgres` (NOT gbrain — migrated 2026-08-05) |
| CLI | `~/.hermes-cortex/scripts/todo-db.py` — `add <content> [--agent N] [--priority n]`, `list [--status]`, `pending`, `update <id> --status` |
| Agent attribution | `AGENT_NAME` env → hostname fallback (todo-db.py line 62) |
| Restore | Session-start protocol: `todo-db.py pending` → `todo()` merge |
| Dream crons | 3 tiers in `install-dream-crons.sh`, `deliver: origin`, toolsets `terminal,file` (todo-db.py runs via terminal — already available) |
| Tenant boundary | PROFILE (HERMES_PROFILE → AGENT_NAME → hostname), per multi-tenancy doc |

## Option A — Knowledge-gap → learning todo (monthly tier)

### Trigger

Inside the monthly dream's **Knowledge-Gap Probe** (Phase 3), for each topic
that returns zero or weak `mycortex search` hits:

### Rules

1. **Add a todo per gap**, content shape:
   `learn <topic> — brain has no strong hits (dream gap, YYYY-MM)`.
2. **Cap: 4 gaps max per run.** If more than 4 topics are gappy, add the 4
   most central to the month's work arc; list the rest in the dream file only.
3. **Dedup:** before adding, run `todo-db.py list --status pending` and skip
   any gap topic already covered by a pending todo (match on topic keyword).
   Do NOT add a todo for a gap that was already flagged last month and is
   still pending — the existing todo covers it; just note it in the dream.
4. **Priority: 1** (learning, not urgent).
5. **Agent: `<profile>`** — the profile the dream belongs to.

### Output format addition (monthly)

```
Phase 3b — Gaps → todos: 2 learning todos added
- todo <uuid8>: learn <topic> (priority 1)
```

## Option B — Insight triage (all three tiers)

### Trigger

After writing the dream, the cron re-reads its own dream content and asks:
*"Does any insight imply a concrete, verifiable next action?"*

### Rules

1. **Actionable = testable.** A candidate must be a verb + object + outcome
   ("verify deepseek rollout on cisnet02", "write docs/design/X",
   "probe why search misses Y", "follow up on msg Z"). Observational or
   purely reflective insights ("the brain is learning to watch itself") are
   **never** todos — they stay in the dream file.
2. **Cap: 2 todos per run.** The bridge adds at most two items per dream;
   everything else stays dream-only. Monthly tier: Option A gaps take
   precedence in the budget (4 gaps + up to 2 insights = 6 max).
3. **Dedup:** same as Option A — check `todo-db.py list --status pending`,
   skip content already covered.
4. **Priority mapping:**
   - Fix/verify/rollout follow-ups → **2**
   - Doc/write/probe/build → **1**
5. **Reference the dream:** content ends with `[from dream YYYY-MM-DD]` so
   the todo is traceable to its source file.
6. **Agent: `<profile>`.**

### Output format addition (nightly/weekly/monthly)

```
Phase X — Actionable: 1 insight triaged to todo
- todo <uuid8>: <verb> <object> (priority 2) [from dream YYYY-MM-DD]
```

## Shared requirements (both options)

1. **Dedup query runs BEFORE any add** — `todo-db.py list --status pending`.
   Match on topic keyword; if a pending todo covers it, skip silently (do not
   fail the run).
2. **Adds are idempotent by construction** — a re-run of the same dream day
   produces the same todos only if the pending list doesn't already contain
   them; otherwise it skips (dedup).
3. **Never `update` or `archive` todos.** The bridge only adds. Completion
   is human/agent session business via the normal todo protocol.
4. **`todo-db.py` failures are non-fatal** — if the CLI errors (DB down),
   warn in the output and continue; the dream file is still written. The
   bridge must never take down the dream.
5. **[SILENT] unchanged** — empty brain → `[SILENT]`, no todos, no output.
6. **Profile resolution identical to the rest of the layer:** HERMES_PROFILE
   → AGENT_NAME → hostname. Never scan `~/.hermes/profiles/*/`.

## Acceptance criteria (orchestrator verification checklist)

| # | Check | Expect |
|---|---|---|
| 1 | Monthly run with ≥1 zero-hit gap topic | `todo-db.py list --status pending --agent <profile>` shows `learn <topic>` item, priority 1 |
| 2 | Re-run same month (or re-run same day) | No duplicate todo — dedup skips; output notes "already pending" |
| 3 | Nightly/weekly with an actionable insight (e.g. verify-fix) | Todo added, priority 2, content ends `[from dream YYYY-MM-DD]` |
| 4 | Nightly/weekly with purely reflective content | Zero todos added; dream still written + delivered |
| 5 | >2 actionable insights in one run | Only 2 added; rest stay in dream file |
| 6 | Dream write-back still happens when todos are added | File + INDEX append present (bridge is additive) |
| 7 | Empty brain | `[SILENT]`, no todos, no delivery |
| 8 | `todo-db.py` temporarily failing | Dream completes with a warning line; no crash |
| 9 | Session start after a dream added todos | `todo-db.py pending` surfaces them; `todo()` restores |
| 10 | Cross-tenant | Todos carry `--agent <profile>`; another profile's list is unaffected |

## Implementation notes for the orchestrator

- **Only `install-dream-crons.sh` prompt text changes.** No new scripts, no
  schema, no doctor changes, no cortex-update changes. The prompts already
  have `terminal,file` toolsets and deepseek-v4-flash.
- **Where in each prompt:** add the triage step AFTER the write-back step
  (the dream must exist before it can be triaged), and add the "Phase X —
  Actionable" block to the OUTPUT FORMAT template.
- **Monthly budget:** Option A (≤4) + Option B (≤2) = ≤6 todos max per run.
- **Deploy:** after editing, `bash install-dream-crons.sh --force` on each
  participating host to refresh the three cron prompts (idempotent create).
  Non-orchestrator hosts cannot self-edit; the orchestrator ships it.
- **Doc updates:** update `docs/design/mycortex-dream-layer.md` (add this
  bridge as a section) and this document's status → implemented.

## Implementation record (what the orchestrator actually shipped — 2026-08-06)

The proposal assumed `bus.todos` existed ("verified 2026-08-06"). It did NOT:
verified absent from the old gbrain dump, the old `gbrain-postgres`
container, and the migrated `mycortex-postgres`. `todo-db.py add` printed ✅
while every row vanished — stdin-mode psql returns rc=0 on SQL failure.
So the implementation shipped MORE than the proposal, in four parts:

1. **Schema:** `core/cortex_bus/schema/todos.sql` applied idempotently to
   `mycortex-postgres` (bus.todos + bus.todo_archive + todo_upsert /
   todo_list / todo_archive_old). Verified live.
2. **todo-db.py fixes:** psql() now uses `-c` mode via direct `docker exec`
   (rc propagates) with an sg fallback that embeds the query in the command
   string; added `todo-db.py --apply-schema` (platform-aware: docker exec on
   Linux, direct psql via mycortex.conf on macOS). Errors now exit 1 with
   stderr — no more silent ✅.
3. **cortex-update.sh:** registers `dream-todo-bridge.py` for deploy and
   runs `todo-db.py --apply-schema` every update (WARN on failure, not
   exit — a fleet update must not be hostage to a peripheral DB; the
   idempotent schema retries next update).
4. **dream-todo-bridge.py** (`ops/scripts/manage/`): enforces Option A
   (≤4 gaps, priority 1, `learn <topic> — brain has no strong hits (dream
   gap, YYYY-MM)`) and Option B (≤2 insights, priority 1-2,
   `[from dream YYYY-MM-DD]` traceability) with caps/dedup/tenant-scoping
   in CODE — the LLM judges actionability, the script guarantees the rules.
   Commands: `add-gap --topic X --agent <profile> --month YYYY-MM`,
   `add-insight --content "..." --agent <profile> --date YYYY-MM-DD
   --priority 1|2`, `list [--agent X]`.

### Acceptance criteria — verified (2026-08-06, live cron run)

| # | Check | Result |
|---|---|---|
| 1 | Monthly gap → todo priority 1 | ✅ bridge test: `learn postgres extension auth` p1 landed |
| 2 | Re-run dedup | ✅ same-topic re-add prints `SKIP: gap already covered` |
| 3 | Nightly actionable insight → todo p2 + `[from dream]` | ✅ `verify deepseek rollout on cisnet02 (priority 2) [from dream 2026-08-06]` |
| 4 | Reflective content → zero todos | ✅ nightly 13:44 triaged 2 insights, both SKIPped by dedup (covered), no dupes created |
| 5 | >2 insights → cap 2 | ✅ enforced in code (argparse cap + prompt cap) |
| 6 | Write-back still happens | ✅ dream file + INDEX append present on every bridge run |
| 7 | Empty brain → [SILENT] | ✅ unchanged protocol |
| 8 | todo-db failure → warn not crash | ✅ `_todo_db()` catches, warns on stderr, exits 0 |
| 9 | Session start surfaces todos | ✅ `todo-db.py pending` returns bridge-created items |
| 10 | Cross-tenant | ✅ `--agent <profile>`; Joseph's list shows zero esther todos |

### Fix-while-shipping (found during implementation)

- **`lessons.py` hardcoded `~/brain/kustos/lessons/`** — the offline lesson
  index read a stale 241-file dir while session-mine wrote 631 live lessons
  to `~/brain/lessons/`. Fixed to the shared path (commit `c5510aa9`).
- **todo-persistence skill** documented `todo-db.py update` silently
  failing — the same stdin/rc bug class, now fixed at the root.

## Open questions (defaults chosen, orchestrator may override)

1. **Weekly tier scope:** should the weekly deep dream ALSO run Option B?
   Default: yes — it's the tier most likely to surface cross-connections
   worth acting on. (Monthly: A + B. Nightly: B only.)
2. **Priority 2 = "fix/verify" semantics:** acceptable default. Could be
   split later (3 = fleet-wide) if noise appears.
3. **Gap re-flagging:** when a gap is still pending from a prior month, we
   skip adding a duplicate and note it in the dream. Alternative: bump the
   existing todo's priority — rejected (bridge is add-only).

## History

- 2026-08-06: Luke asks "how are dream results incorporated as actionable
  todo?" → answer: they aren't yet. Luke: "both would be useful. come up
  with a design/requirements for an orchestrator to implement." This doc.
- Related: `docs/design/mycortex-dream-layer.md` (the layer being bridged),
  `docs/design/mycortex-multi-tenancy.md` (tenant rules honored here).
