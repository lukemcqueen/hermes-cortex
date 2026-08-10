# Task Lifecycle v2 — Design Doc (story/slices · paused · bus-as-tasks · Telegram)

> **Status: party-reviewed 2026-08-06 (6-role HC-Party: Architect 6.5,
> Security 6, SRE 6, Domain 6.5, Product 7, QA 4→6.5 post-resolution →
> weighted 6.40/10; **CONDITIONAL GO** — every party finding B-1..B-5,
> R-1..R-22, M-1..M-12 is closed in this document; none deferred).**
> Luke directive (2026-08-06): *"now that we have the tasks plumbing, i'd like
> to figure out a way to get all agents to use tasks with 1) story/slices,
> 2) any task the work on (before, during, switching, after), 3) any command
> on the bus. And I'd love to see output to my telegram for visibility on
> entry/state change."*
>
> Source of requirements: `docs/elicit/2026-08-06_task-lifecycle-v2-elicit.md`
> (fast mode, 4 locked decisions D-1..D-4).
> Party verdict: `docs/elicit/2026-08-06_task-lifecycle-v2-party.md`.
> Governance cycles: #1925 (elicit), #1926 (party), #1927 (this doc).

---

## 1. Why this exists

The base tasks system (party-reviewed 2026-08-06, `docs/design/task-workflow.md`)
ships a solid per-host task store: `tasks` schema v001–v004 on every agent's
mycortex-postgres, `task-db.py` + `task_*` MCP tools, RLS fail-closed, single
`task_upsert` write path, session protocol. What it does NOT yet have —
Luke's four asks:

1. **Story/slices** — tasks are flat rows; no decomposition hierarchy.
2. **Lifecycle everywhere** — status transitions are manual; nothing tracks
   the full arc (entry → work → switch → done) automatically.
3. **Bus commands as tasks** — commands arriving via the agent bus
   (`agent-message-handler.py`, fleet-wide no_agent consumer) create no rows.
4. **Telegram visibility** — no notification channel; Luke can't see task
   activity without logging into a host.

**Success metric:** every task an agent touches — manual, session-derived, or
bus-arrived — is a `tasks.tasks` row with a complete, observable lifecycle,
and Luke sees entry + state changes in his Telegram DM without logging into
any host.

**The party's three structural verdicts, honored here:**
- **No fleet transport needed** for visibility — each agent notifies Telegram
  directly via a shared notify module (token already in every agent's
  `~/.hermes/.env`). No bus round-trip. (Product: transport becomes a
  *distribution* problem, not a *visibility* one.)
- **Handler stays no_agent** — task creation is a direct `task-db.py` call,
  zero LLM cost.
- **Single write path preserved** — hierarchy, transitions, and events all
  funnel through `task_upsert` + DB triggers; CLI/MCP/handler/restore/bridge
  can't bypass (QA B-4).

---

## 2. Architecture

```
                 ┌────────────────────────────────────────────┐
                 │            tasks.tasks (per-host)          │
   CLI/MCP ─────►│  task_upsert()  ← single write path        │
   handler ─────►│    + triggers: transition matrix,          │
   restore ─────►│      tenant coherence, event capture,      │
   bridge ──────►│      story auto-complete                  │
                 └───────────────┬────────────────────────────┘
                                 │ AFTER INSERT/UPDATE triggers
                                 ▼
                 tasks.task_events (append-only, INSERT-only RLS)
                                 │
                                 ▼
                 lib/telegram_notify.py ──► Telegram DM (Luke)
                 (shared module: token, scrub, coalesce, backoff)
```

- **Storage:** same per-host `tasks` schema; v005 adds columns/table
  (additive, version-gated). No new infra.
- **Two surfaces, one engine:** `task-db.py` CLI + `task_*` MCP stay the thin
  wrappers; all logic in DB functions/triggers so every caller is equal.
- **Driver coupling (Architect R-1):** the loop-governance
  `begin_change/end_change` lifecycle is the *work driver*; the tasks system
  is the *observability trail*. One-way sync: the session protocol (task-
  persistence skill) calls `task-db.py` at the four lifecycle points; tasks
  never call loop-gov. The `tasks.task_events` table is distinct from
  loop-governance's internal event log (different id domains — documented,
  not conflated).
- **Roles (unchanged from base):** CRUD as `mycortex_reader_<profile>`, DDL
  as `mycortex`, fleet writes via `todos_fleet_writer` (orchestrators).

---

## 3. Schema — v005 (hierarchy + paused + events)

`ops/services/tasks/schema/v005__lifecycle.sql` — additive ALTERs only,
**single transaction (BEGIN/COMMIT)**, version-gated by the existing
migrate.py runner (SRE R-10). Closes B-5, R-1, R-7, R-10, M-1, M-6.

```sql
BEGIN;

-- ── 3.1 hierarchy (B-1 resolution: parent_id OPTIONAL, coherent when set) ──
ALTER TABLE tasks.tasks ADD COLUMN parent_id UUID REFERENCES tasks.tasks(id)
    ON DELETE NO ACTION;                    -- M-1: FK gives story-delete block free
ALTER TABLE tasks.tasks ADD COLUMN kind TEXT
    CHECK (kind IS NULL OR kind IN ('story','slice'));   -- NULL = legacy flat
-- coherence: story has no parent; slice HAS a parent; legacy flat has neither
ALTER TABLE tasks.tasks ADD CONSTRAINT tasks_hierarchy_coherence CHECK (
    (kind = 'story' AND parent_id IS NULL)
    OR (kind = 'slice' AND parent_id IS NOT NULL)
    OR (kind IS NULL AND parent_id IS NULL)
);
CREATE INDEX idx_tasks_parent ON tasks.tasks (parent_id) WHERE parent_id IS NOT NULL;

-- ── 3.2 paused status (R-7: CHECK + task_upsert CASE + column CHECK together) ──
ALTER TABLE tasks.tasks DROP CONSTRAINT tasks_tasks_status_check;
ALTER TABLE tasks.tasks ADD CONSTRAINT tasks_tasks_status_check CHECK (
    status IN ('pending','in_progress','paused','completed','cancelled'));
ALTER TABLE tasks.tasks DROP CONSTRAINT tasks_tasks_column_check;
ALTER TABLE tasks.tasks ADD CONSTRAINT tasks_tasks_column_check CHECK (
    column IS NULL OR (
        (column IN ('backlog','todo') AND status = 'pending')
        OR (column = 'in_progress' AND status = 'in_progress')
        OR (column = 'done' AND status = 'completed')
        OR (column = 'review' AND status IN ('pending','in_progress'))
        -- paused derives column = NULL (like cancelled) — v003/v004 class locked
    ));

-- ── 3.3 correlation_id for bus traceability (R-19: session_id stays provenance) ──
ALTER TABLE tasks.tasks ADD COLUMN correlation_id TEXT;
CREATE UNIQUE INDEX idx_tasks_inbox_correlation
    ON tasks.tasks (correlation_id) WHERE source = 'inbox' AND correlation_id IS NOT NULL;
-- partial unique → 1 task per bus message (Architect R-4 idempotency)

-- ── 3.4 task_events — the notify source of truth (B-5, R-1, M-11) ──
CREATE TABLE tasks.task_events (
    id           BIGSERIAL PRIMARY KEY,
    task_id      UUID NOT NULL REFERENCES tasks.tasks(id) ON DELETE CASCADE,
    event_type   TEXT NOT NULL CHECK (event_type IN
                    ('created','status_changed','story_auto_complete')),
    from_status  TEXT,               -- NULL for 'created'
    to_status    TEXT,
    reason       TEXT,               -- 'switch','stale','story_auto_complete','reopen',…
    by           TEXT NOT NULL,      -- profile
    session_id   TEXT,
    correlation_id TEXT,
    at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_task_events_task_at ON tasks.task_events (task_id, at);
ALTER TABLE tasks.task_events ENABLE ROW LEVEL SECURITY;
-- INSERT-only for app roles: readers SELECT only; writes ONLY via task_log_event()
-- (SECURITY DEFINER owned by mycortex, validated) — no UPDATE/DELETE grants (Security R-1)
CREATE POLICY task_events_select ON tasks.task_events FOR SELECT USING (
    EXISTS (SELECT 1 FROM tasks.tasks t WHERE t.id = task_id
            AND (t.scope = 'fleet' OR t.created_by = profile_of(current_user))));
GRANT SELECT ON tasks.task_events TO mycortex_reader;
-- retention: events CASCADE with task delete; task_prune() extended to prune
-- events of pruned archived rows in the same transaction (SRE R-9/R-19)

-- ── 3.5 task_upsert signature growth (QA M-10: APPEND with defaults) ──
-- task_upsert(p_content, p_created_by, p_assignee, p_project, p_repo, p_target,
--             p_scope, p_status, p_column, p_position, p_priority, p_due,
--             p_tags, p_source, p_depends_on, p_session_id, p_completed_at,
--             p_parent_id DEFAULT NULL,          -- NEW (append)
--             p_kind DEFAULT NULL,              -- NEW
--             p_correlation_id DEFAULT NULL)    -- NEW
-- 17-arg legacy callers keep resolving (trailing defaults). All v005 callers
-- pass positionally with the new args at the end. (QA M-10 verified safe:
-- v003/v004 function-replacement precedent.)

COMMIT;
```

**Backfill (M-6):** existing rows get `kind = NULL` (legacy flat — legal per
coherence CHECK, no forced story-parent). No data rewrite needed; the CHECK
admits it.

---

## 4. Transition Matrix (B-4 — enforced in the DB write path)

Legal transitions (validated by a `BEFORE UPDATE` trigger + `task_upsert`
fast-fail; every cell L1-tested):

| from \ to | pending | in_progress | paused | blocked | waiting | completed | cancelled |
|---|---|---|---|---|---|---|---|
| pending | — | ✅ | ❌ (must start first) | ✅ | ✅ | ❌¹ | ✅ |
| in_progress | ❌ | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| paused | ❌ | ✅ (resume) | — | ✅ | ✅ | ✅ | ✅ |
| blocked | ❌ | ✅ (resume) | ✅ | — | ✅ | ✅ | ✅ |
| waiting | ❌ | ✅ (resume) | ✅ | ✅ | — | ✅ | ✅ |
| completed | ❌ | ✅ (reopen, reason='reopen') | ❌ | ❌ | ❌ | — | ❌ |
| cancelled | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | — |

¹ `pending → completed` for a **story** is admitted only via the
`story_auto_complete` AFTER trigger path (reason='story_auto_complete',
guaranteed no active slices) — never by hand.

- `paused ⇄ in_progress`: the switching arc (D-2). `switch` = pause current +
  resume target atomically (M-8).
- `pending → paused` is **illegal** — you can't pause what you never started.
- `completed → in_progress` allowed **only** with `reason='reopen'` (explicit
  reopen policy — Domain R-5).
- `paused → completed` allowed (agent resolved a paused task as done).
- `blocked` = actively stuck on an external dependency; `waiting` = not yet
  actionable (dependency not ready). Both derive `column = NULL` (paused
  class) and are surfaced by session restore but never auto-resumed (M-7,
  v008).
- Story rows (`kind='story'`) may not be `completed` while any non-cancelled
  slice is active (Domain R-3 — gate in the same trigger). When the last
  active slice reaches `completed`/`cancelled`, the story **auto-completes**
  (v008, reason='story_auto_complete', event_type='story_auto_complete').
- Enforcement: `tasks.check_transition()` BEFORE UPDATE trigger + inside
  `task_upsert` (RAISE EXCEPTION → CLI catches → friendly error). Direct SQL
  cannot bypass (QA B-4).

---

## 5. Event Trail Contract (B-5, R-1, M-11)

- **Capture:** `AFTER INSERT` (event_type='created', from_status NULL) and
  `AFTER UPDATE OF status` (event_type='status_changed', from=OLD.status,
  to=NEW.status) triggers on `tasks.tasks`. One enforcement point covers CLI,
  MCP, handler, restore, and bridge — future callers can't forget (SRE M-11).
- **No-op gate:** trigger checks `OLD.status IS DISTINCT FROM NEW.status` —
  no-op updates emit nothing (QA B-5).
- **Suppression at source (M-5):** `source='doctor-probe'` rows emit NO
  events (and thus no notify); the doctor also passes `--no-notify`. Silent
  bus subjects never create rows, so never emit.
- **Write path:** inserts go through `task_log_event()` — SECURITY DEFINER
  owned by `mycortex`, validates caller profile, sets `by=profile_of(caller)`.
  App roles have INSERT via function only; no direct UPDATE/DELETE grants →
  forge-proof audit (Security R-1).
- **Reason values:** `'switch'` (pause/resume), `'stale'` (sweep),
  `'story_auto_complete'`, `'reopen'`, NULL otherwise.
- **Retention:** events CASCADE with task delete; `task_prune()` prunes
  events of pruned archived rows in the same transaction. No unbounded growth
  (SRE R-19).
- **Replay/source-of-truth consistency (Product R-5):** notify is best-effort
  from the event; if a send is dropped/coalesced, the event trail retains the
  truth. Accepted: no replay pipeline in v2 (documented decision — the DM is
  a live feed, the DB is the record).

---

## 6. Lifecycle Automation (before / during / switching / after)

Session protocol (task-persistence skill, extended — same commit):

| Phase | Action |
|---|---|
| **Before** (session start) | `task-db.py pending` → restore; paused surfaced in a separate section, **never auto-resumed** (Domain M-9) |
| **During** (begin_change) | `task-db.py update <id> --status in_progress` (or `switch <id>` if another is active) |
| **Switching** (task A→B) | `task-db.py switch <target-id>` — one command: pause current in_progress (reason='switch'), resume target. DB function, single transaction, two events (M-8). "Current in_progress" = latest `status_changed_at` |
| **After** (end_change) | `task-db.py update <id> --status completed`; `save-end` unchanged |

**`switch` edge cases (QA M-8):** target==current → no-op with friendly
message; no current in_progress → just resume target; target is a story →
rejected.

**Stale sweep (R-16, M-2, M-7):**
- Bus tasks (`source='inbox'`): > threshold (default 1h, configurable) in
  `in_progress` → sweep to **paused** with `reason='stale'` — NOT cancelled
  (preserves the arc, matches D-2; a human/next-run resolves). Allowlist
  (`target`/`project` in config) exempts legitimately long EXEC/cortex-update.
  Runs on the handler tick — no new infra, idempotent. Emits event + notify.
- Manual tasks (`source='manual'`): > 24h in `in_progress` → **FLAG only**
  (doctor WARN + list marker) — never auto-transition (Product R-4: the feed
  must not lie about state the agent actually owns).
- `paused` has no reaper by design — it's a human/resume decision; session
  restore surfaces it (Domain M-7, resolved: `blocked`/`waiting` explicitly
  deferred to v006 as a cheap additive CHECK).

---

## 7. Bus Commands as Tasks (B-2, R-8, R-12, R-13, R-14, R-18)

**Allowlist (Security R-8 — deny-by-default):** `TASK_CREATING_SUBJECTS =
{EXEC, UPDATE_REQUEST, TASK_REQUEST, PROPOSAL, ISSUES, IMPROVEMENTS}` + the
`Task:`/`TASK:` prefix form. Everything else — including unknown subjects —
creates NO row and NO notify (unknown → existing error path only).

**Create-before-archive (SRE R-12):** the handler creates the task row
BEFORE archiving the message. Crash between → row exists, sweep is a genuine
safety net. No silent-no-op (the base party's #1 class).

**Lifecycle mapping (Domain B-2 — two consumers, both wired):**

| Command class | Consumer | Transitions |
|---|---|---|
| EXEC / UPDATE_REQUEST | handler (no_agent) | created(pending) on receipt → in_progress at dispatch → **completed at Result-receipt** (EXEC_RESULT/UPDATE_RESULT handler path — async, matches reality) |
| ISSUES / PROPOSAL / IMPROVEMENTS / Task: | LLM `inbox_read` session | created(pending) on handler receipt → in_progress when the orchestrator session processes it → completed when handled; session calls `task-db.py update --by-correlation <id>` |

**Ownership (Domain R-18):** the **executing** agent owns the row
(`created_by` = the agent that runs the command). Sender tracks via
`depends_on` or not at all. Handler on every agent only creates rows for
commands IT executes — no cross-host duplicates (message routing already
decides executor; the handler that dispatches is the one that creates).

**Traceability (R-19, SRE M-12):** task carries `correlation_id` = bus message
correlation_id; `send_bus_result` bodies include the task id so reply↔task is
a direct join, not a lookup. The partial unique index (3.3) enforces 1
task/message even across handler restart/state-file loss (Architect R-4).

**Stale inbox rows:** doctor WARNs (see §12) so sweep absence is visible.

---

## 8. Telegram Notify (B-5/R-5/R-6/R-14, R-15, R-20, M-3)

**Shared module (Security R-9, M-3):** `ops/scripts/lib/telegram_notify.py` —
single token read (`TELEGRAM_BOT_TOKEN` from `~/.hermes/.env`),
`TELEGRAM_HOME_CHANNEL` from env (**not** hardcoded — removes the
recipient id from the public repo, R-6), HTML escaping, 600-perms check.
Handler + task-db.py + fleet-command-verifier all import it — the 3rd copy
is now the only copy.

**Message format (R-6 PII whitelist):** `[agent] story → slice: status (id)`
for slice rows; `[agent] story: status (id)` for stories. **Never the body.**
Fields: agent, kind, title (scrubbed), status, id. Scrub gate extended for
notify: strip abs paths, `~/`, `user@host`, bare hostnames, IPv4/IPv6 (M-6
extends the base regex).

**Triggers (D-3, Luke-locked):**
- **Entry** (created, any kind) → immediate
- **completed** → immediate
- **in_progress / paused / cancelled** → per-event

**Volume governance (Product R-1, R-2):**
- Default bus tasks = **standalone slices** (`parent_id NULL`) — no synthetic
  per-command story, no double entry-notify (B-1/R-2).
- Story-row entry notify: suppressed for auto-created rows; stories created
  by humans notify once.
- Task-event notify **replaces** the handler's pickup/issue-report notify for
  tracked subjects (R-14) — one EXEC = 1 message, not 5.
- Quiet-hours window (config: `TASKS_NOTIFY_QUIET=22:00-07:00`) → defer to a
  digest flushed at window end.
- Per-status mute registry (`TASKS_NOTIFY_MUTE=in_progress,paused`).
- Target: **≤40 msgs/day steady state** (success metric — measured in dogfood).

**Mechanics (R-5 — cross-process, since task-db.py is per-invocation):**
- Host-level `flock` + last-send timestamp file → global coalescing
  ≤1 msg/2s (not per-process).
- 429 → honor `Retry-After`, bounded retries (2), then drop + count.
- Failure counter persisted (`~/.hermes-cortex/state/telegram-notify.json`),
  surfaced by doctor (WARN). Logs go to a file, not cron stdout (R-15).
- Send is **post-commit, time-boxed ≤3s, non-fatal** — a notify failure never
  rolls back the task write (F-014, unchanged).

---

## 9. Security Invariants (all base B-1..B-10 classes preserved)

| Invariant | Mechanism |
|---|---|
| No injection / RCE | All DML via parameterized `task_upsert`; new columns appended; allowlists extended (`kind`, `status` incl. `paused`); psql stdin-only (unchanged) |
| RLS fail-closed | `task_events` inherits profile-scoped RLS (3.4); INSERT-only; `task_log_event` validates caller |
| Tenant coherence (R-2) | Trigger: slice.parent must be visible to caller (same created_by, or fleet + fleet-writer); slice.scope ≤ parent.scope; cross-tenant parent linkage impossible |
| Archive safety (R-3) | FK ON DELETE NO ACTION → deleting a story with slices fails; `task_archive_old()` extended to archive **children before parents**; regression test "completed story with slices → save-end" |
| Prompt-injection channel (R-4) | Bus content scrubbed/truncated at ingest (extended gate + hard 500-char cap); rows marked `source='inbox'`; `pending`/`restore` output renders inbox rows with an untrusted marker and EXCLUDES them from agent-context restore by default (opt-in `--include-inbox`) |
| Secret handling (R-6) | `TELEGRAM_HOME_CHANNEL` from env (canonical, per-host), not code; doctor checks `.env` perms 600; token never logged |
| Deny-by-default | `TASK_CREATING_SUBJECTS` allowlist (R-8); unknown subjects → no row, no notify |

---

## 10. Migration & Deploy (R-10, R-11)

- **v005 is one transaction** (BEGIN/COMMIT) — a mid-file failure rolls back,
  no half-applied state (SRE R-10). Poisoned-migration L1 test.
- **Code/schema skew (R-11):** task-db.py gains a runtime
  `tasks.schema_version` probe:
  - `schema_version >= 5` → full v2 behavior (events, paused, parent/kind).
  - `< 5` → **graceful degradation**: reject `--status paused` /
    `--parent`/`--kind`/`switch` with clear "requires v005" errors, skip event
    emission, keep v1 behavior. No "function does not exist" confusion.
- **Deploy order:** cortex-update syncs code → runs migrate.py → doctor
  FAILs on `schema_version < expected` → recovery = re-run cortex-update
  (standard runbook step). The failing host is never silently degraded.
- **`task_upsert` arity:** new params appended with defaults (3.5) — legacy
  17-arg callers (dream-bridge, restore, MCP wrappers, 3 positional SQL
  strings) keep resolving; L0 tests updated in the same commit (M-10).

---

## 11. Implementation Plan — Story TL-v2 (slices in dependency order)

**Story: "Task Lifecycle v2 — fleet task discipline"** (project
`hermes-cortex`, seeded via task-db.py; promoted to real story/slice rows
when v006 ships).

Product's locked sequencing (R-21): **event trail + lifecycle + paused +
notify FIRST (visible value ~1d) → bus coupling SECOND (~0.5–1d) → hierarchy
LAST (additive, highest schema risk, lowest incremental value)**.

| Slice | Deliverable | Closes | Est. |
|---|---|---|---|
| **S1** | v005 schema: hierarchy cols + paused + correlation_id + task_events + transition trigger + tenant trigger + task_log_event + story auto-complete trigger + task_upsert 20-arg; backfill NULL-kind | B-1,B-4,B-5,R-1,R-2,R-7,R-10,R-19,M-1,M-6,M-10,M-11 | 0.75d |
| **S2** | `lib/telegram_notify.py`: env chat_id, scrub gate ext, flock coalescing, 429 backoff, failure counter, file logs, quiet-hours + mutes; handler + verifier refactored to import it | R-5,R-6,R-9,R-15,R-20,M-3 | 0.5d |
| **S3** | task-db.py v2: `paused`, `switch`, `--parent/--kind`, `--no-notify`, `--by-correlation`, schema_version probe, restore untrusted-inbox marking, pending paused section | B-4,R-11,R-19,M-7,M-8,M-9 | 0.5d |
| **S4** | handler bus→task: TASK_CREATING_SUBJECTS allowlist, create-before-archive, EXEC/UPDATE completion at Result-receipt, pickup silent-aware + notify dedupe, stale sweep on tick | B-2,R-8,R-12,R-13,R-14,R-16,R-18,M-2,M-12 | 0.5d |
| **S5** | inbox_read consumer wiring: ISSUES/PROPOSAL/IMPROVEMENTS/Task: transitions by correlation_id; task id in send_bus_result | B-2,R-19,M-12 | 0.25d |
| **S6** | v006 (deferred, additive — **shipped as schema v008**): `blocked`/`waiting` status + story `list --parent` + `task_story_summary()` + archive children-first + story auto-complete polish | R-3,M-4,M-7(v006) | 0.5d |
| **S7** | doctor checks: schema_version≥5 FAIL, task_events RLS assertion FAIL, telegram notify health WARN, stale inbox WARN, .env 600 WARN, manual-flag WARN; test batteries L0/L1/L2 extended | R-5,R-15,R-16,B-3 | 0.5d |
| **S8** | docs: task-persistence skill + AGENTS.md + cron-schedules.md updated in same commit; **rollout gate run** (below) | R-4,party-cond | 0.25d |

**Total: ~3.75d optimistic / 4.5d likely / 6d pessimistic** (bracketed,
QA-gated). $0 infra. ~1–2 hrs/wk maintenance.

---

## 12. Test Plan (B-3 — every US/AC mapped to a layer)

| Layer | Artifact | Covers |
|---|---|---|
| **L0 unit** | `test_task_db_unit.py` (extended) | `--parent/--kind/--no-notify/--by-correlation` flags; `switch` two-call sequencing + edge cases; transition fast-fail; coalescer/backoff with fake clock; notify-text PII scrub; handler task-create function (mocked task-db call); `cmd_pending` JSON incl. paused + untrusted-inbox marker |
| **L1 schema** | `tests/test-tasks-schema.sh` (extended) | hierarchy (slice-under-story OK; slice-under-slice / story-under-story / slice-without-parent / story-with-parent rejected; story-delete blocked); paused→column NULL + status CHECK replacement; transition matrix cell-by-cell; task_events (created event, INSERT-only RLS, no UPDATE/DELETE, FK-on-delete, retention); v005 double-apply no-op; poisoned-migration recovery; doctor-probe creates NO event/notify; archive children-before-parents; tenant-coherence trigger |
| **L2 fleet** | `tests/test-task-fleet.sh` (extended) | EXEC → row → completed E2E with `--no-notify` + dummy token (zero real Telegram); ISSUES/PROPOSAL via inbox_read path; no_agent profile resolution (created_by satisfies RLS WITH CHECK); doctor green; stale-sweep L1-seeded old row |
| **L3 dogfood** | rollout gate | §13 — real Telegram, measured volume |

**Regression locks:** all base AC-L1-5 class tests stay green; `task_upsert`
17-arg compatibility test (old callers resolve); skew test both directions
(new CLI+old schema graceful, old CLI+new schema works via defaults).

---

## 13. Rollout Gate (QA R-7 — non-negotiable)

1. **Single host first (Esther):** full battery green → v005 applied →
   doctor green.
2. **Real-Telegram dogfood ≥ 1 day:** live EXEC + manual + story/slice
   transitions; **measure DM volume/format vs ≤40/day target**; tune quiet
   hours/mutes if over.
3. **Fleet-wide only after:** Esther dogfood clean → cortex-update per host →
   doctor green everywhere → Luke confirms format/volume acceptable.

---

## 14. Documentation Updates (same commit — RULE 4)

- `task-persistence` skill: v2 lifecycle protocol (before/during/switching/
  after table), `switch` command, paused semantics, untrusted-inbox restore
  marking, notify behavior.
- `AGENTS.md`: session protocol section extended.
- `docs/design/task-workflow.md`: pointer to this doc for v2 deltas.
- `cron-schedules.md`: stale-sweep-on-tick noted (no new cron — handler tick).

---

## 15. Explicit Deferrals (documented, not accidents)

- ~~`blocked`/`waiting` status → v006 (Domain M-7).~~ **SHIPPED in v008**
  (schema `v008__v006-deferred.sql` — blocked/waiting status, story
  `list --parent`, `task_story_summary()`, archive children-first, story
  auto-complete).
- Fleet transport (git-backed private repo) → roadmap milestone (unchanged,
  B-3 base); Telegram visibility does NOT depend on it.
- Notify replay pipeline → accepted drop (event trail is the record) (R-5).
- ~~Story auto-complete → v006 polish; v005 ships the gate (no story completed
  with active slices) + manual story status.~~ **SHIPPED in v008** — v005's
  gate holds; the AFTER trigger now auto-completes a story when its last
  active slice reaches completed/cancelled (reason + event
  `story_auto_complete`).
