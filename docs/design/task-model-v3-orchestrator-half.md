# Task Model v3 — the orchestrator write surface (plan, rev 2)

Backlog row **`9fb2ddb6`** (priority 2, personal, owner esther). Cycle **#13847**,
task id `task-model-v3-plan`, session `cron_1954deb5ad76_20261027_142143`.
Author: esther (orchestrator). Status: **plan — adversarial review returned
FINDINGS at rev 1; both findings are answered below and the plan is corrected
BEFORE any code is written** (operator standing rule, 2026-10-14).

## 0. What changed at rev 2 (review disposition)

Review row `4e0fa3b6-44fa-4d5a-9ac2-06d9dc1c6f45`, reviewer
`deepseek/deepseek-v4-pro`, verdict **FINDINGS**, 1 high + 1 info. Both were
accepted; neither was argued down. Raw evidence for both:
`docs/evidence/task-model-v3-orchestrator-half/findings-proof.txt`
(`proof.sh`, same directory — every block ends in `ROLLBACK`).

- **ADV-13847-1 (high) — ACCEPTED, design corrected.** The reviewer is right:
  `CREATE OR REPLACE FUNCTION` cannot change a function's argument list, so
  rev 1's migration would have left the 20-argument `task_upsert` in place and
  added a *second* overload, while the planned verification command became
  unusable. Proved, block **A**: after a bare `CREATE OR REPLACE` with one more
  parameter, `task_upsert overloads now: 2` and
  `pg_get_function_arguments('tasks.task_upsert'::regproc)` →
  `ERROR: more than one function named "tasks.task_upsert"`. §4.1 now uses the
  repo's own house pattern (`DROP` the exact old signature, then `CREATE` the
  wider one, re-granting), and §4.4 gains the reviewer's requested regression
  assertion. That precedent is already in the repo: `v005__lifecycle.sql:332`
  says *"CREATE OR REPLACE cannot change arity — the 17-arg function must be
  dropped first"* and does exactly that at `:336`.
- **ADV-13847-2 (info) — ACCEPTED, claim now measured.** The §3 trap was
  asserted from the source but not shown. Block **C** now shows it live: on an
  `in_progress` row, `task_upsert(p_id => …, p_status => NULL)` (exactly what
  `task-db.py:849` passes) raises
  `23514 : new row for relation "tasks" violates check constraint "tasks_column_check"`.
  Block **B** shows the corrected arity pattern leaves exactly one function
  (`after DROP + CREATE: 1`). Block **D** captures the nine roles that hold
  `EXECUTE` today — the set §4.1 must restore, because a `DROP` discards them.

## 1. What the row asks for

Row `9fb2ddb6` records that the Task Model v3 orchestrator half is unimplemented.
Its own fix direction, quoted:

> (a) add `--plan` to task-db.py add/update and thread `p_plan` through
> `task_upsert`; (b) add an orchestrator hand-out surface (`--assignee` /
> `--depends-on` on update, or a dispatch helper that sets assignee +
> correlation_id and sends the bus TASK_REQUEST atomically) so a handed-out
> slice is machine-visible; (c) until (b) ships, the morning pass must dispatch
> via the bus ... rather than pretending pull-claim works.

The constraint it states explicitly: **"Do NOT write plans by raw SQL — that
bypasses the single write path."** So every write in this design goes through
`tasks.task_upsert()`, the documented single write path
(`ops/scripts/manage/task-db.py` docstring, security invariant B-4).

## 2. Measured starting state (raw, committed, re-runnable)

Transcript: `docs/evidence/task-model-v3-orchestrator-half/cur-surface.txt`,
produced by `capture.sh` in the same directory on host `esther`, tree `42b79528`.

| Fact | Raw evidence |
|---|---|
| The LIVE `tasks.task_upsert` takes 20 parameters. `p_assignee`, `p_depends_on` and `p_correlation_id` are **already** among them. **`p_plan` is not.** | `pg_get_function_arguments('tasks.task_upsert'::regproc)` → `p_id … p_correlation_id text DEFAULT NULL::text` (20 names, no `p_plan`); block E: exactly 1 such function exists |
| The token `p_plan` appears **nowhere** in the schema, the CLI or the MCP servers | `grep -rn "p_plan" ops/services/tasks/schema ops/scripts/manage/task-db.py mcp-servers` → `rc=1` (no matches) |
| The documented CLI surface is `update <id> --status <new-status> [--reason <r>] [--no-notify]` — no metadata flags | `grep -n "task-db.py update" …` → `38: task-db.py update <id> --status <new-status> [--reason <r>]` |
| The latest committed definition of the write path is v008's, ending at `p_correlation_id` | `grep -n "CREATE OR REPLACE FUNCTION tasks.task_upsert" ops/services/tasks/schema/v008__v006-deferred.sql` → `42:`; `62: p_correlation_id TEXT DEFAULT NULL` |
| Every call site passes arguments **positionally** | `grep -n "task_upsert(?::uuid" ops/scripts/manage/task-db.py` → lines 560, 823, 849, 1180, 1183, 1197 |
| Open rows on this host that the write surface cannot touch | local DB census: `38\|\|31\|\|38\|\|28\|\|38` = 38 open, **31 plan IS NULL**, **38 unassigned**, 28 no `correlation_id`, **38 no `depends_on`** |

Two consequences, and they are the whole reason this row is small:

1. **Only `p_plan` is missing from SQL.** `--assignee`, `--depends-on` and
   `--correlation-id` need *no schema change at all* — only CLI wiring.
2. **Appending a 21st parameter is safe for callers** (every existing call is
   positional and the new parameter defaults to NULL) — but only if the old
   signature is **dropped** first; a bare `CREATE OR REPLACE` would not reach
   the old object (§0, ADV-13847-1).

## 3. The trap the design has to get past

`update` today *requires* `--status`, and guards it with a no-op honesty gate
(`task-db.py:796-815`, quoted in the capture): if the row is already in the
requested status the command prints `already <status> — no change` and
**returns without writing**. A metadata-only write (`--plan`, `--assignee`)
therefore cannot ride on `--status <current>` — the plan text would be silently
discarded, which is exactly the class of false success that gate was added for.

Worse, naively calling `task_upsert` with `p_status = NULL` corrupts `column`:
`v_status := COALESCE(p_status, 'pending')` → the INSERT branch proposes
`column='todo'`, and the `ON CONFLICT` branch assigns `"column" = EXCLUDED."column"`
**unconditionally** (v007's deliberate v004 exception). The row's *status* is
preserved (`status = COALESCE(p_status, tasks.tasks.status)`) but its *column*
becomes `'todo'` — which violates `tasks_column_check` (`'todo'` requires
`status='pending'`) and the UPDATE is rejected. **Measured, not inferred** —
`findings-proof.txt` block C:

```
NOTICE:  scratch row = 223747ff-077c-45d8-8daf-9f431594ac76 (status=in_progress)
NOTICE:  RAISED 23514 : new row for relation "tasks" violates check constraint "tasks_column_check"
```

A metadata-only write must therefore pass the row's **current** status as
`p_status`, not NULL. §4.2 rule 2 does exactly that.

## 4. Design

### 4.1 Schema — one new migration `v016__task-upsert-plan.sql`

Inside a single transaction (the `BEGIN; … COMMIT;` house pattern):

```
DROP FUNCTION IF EXISTS tasks.task_upsert(UUID, TEXT, TEXT, TEXT, TEXT, TEXT,
    TEXT, TEXT, TEXT, TEXT, INT, INT, TIMESTAMPTZ, TEXT[], TEXT, UUID[], TEXT,
    UUID, TEXT, TEXT);                  -- the EXACT 20-arg signature
CREATE FUNCTION tasks.task_upsert( ...the v008 body, 21 params... );
GRANT EXECUTE ON FUNCTION tasks.task_upsert(<those 21 types>) TO <roles>;
```

- **Why `DROP` first:** measured — `CREATE OR REPLACE` cannot change arity, so
  it produces a second overload and leaves the 20-arg function live
  (`findings-proof.txt` block A). Proved safe as the repo's own pattern: the
  `DROP` + `CREATE` sequence leaves exactly one function (block B), and
  `v005__lifecycle.sql:332-337` already uses it for the 17-arg → 20-arg step.
- **Re-grant is mandatory, not cosmetic:** `DROP` discards the function's ACL.
  Block D lists the nine roles that hold `EXECUTE` on it today on this host —
  `mycortex`, `mycortex_admin`, `mycortex_ingest`, `mycortex_mem_admin`,
  `mycortex_mem_reader`, `mycortex_mem_writer`, `mycortex_reader`,
  `mycortex_reader_esther`, `mycortex_reader_probe`. The migration re-grants
  with the guarded `IF EXISTS (SELECT 1 FROM pg_roles …)` loop that
  `v009__task-model-v3.sql:87-97` already established (unguarded grants killed
  the migration on non-Esther hosts), using the **new** 21-type signature.
- The new body is the v008 body verbatim plus exactly three edits:

```
    p_correlation_id TEXT DEFAULT NULL,   -- v007
    p_plan           TEXT DEFAULT NULL    -- NEW (v016), appended LAST
```

```
  INSERT INTO tasks.tasks (…, kind, correlation_id, plan, created_at, …)
  … p_parent_id, p_kind, p_correlation_id, p_plan, …

  ON CONFLICT (id) DO UPDATE SET
      …
      correlation_id   = COALESCE(p_correlation_id, tasks.tasks.correlation_id),
      plan             = COALESCE(p_plan, tasks.tasks.plan),   -- NEW (v016)
```

- Additive and re-runnable, wrapped in one `BEGIN; … COMMIT;`.
- It does **not** touch `transition_allowed`, `check_transition`, `claim_slice`
  or any RLS policy. Scope is the write path only.

### 4.2 CLI — `ops/scripts/manage/task-db.py`

`add` gains one flag; `update` gains four and loses a hard requirement:

```
task-db.py add    <content> [… existing flags …] [--plan <text>]
task-db.py update <id> [--status <new-status>] [--reason <r>]
                       [--plan <text>] [--assignee <a>]
                       [--depends-on <uuid>[,<uuid>…]] [--correlation-id <c>]
                       [--no-notify]
```

Rules, each one answering a measured fact:

1. **`--status` becomes optional** — but only when at least one metadata flag is
   given. `update <id>` with no flags at all stays a usage error (an empty
   update must never be a silent no-op).
2. When `--status` is **omitted**, the handler passes the row's **current**
   status as `p_status` (it already fetches exactly that value for the no-op
   gate at `:803`), so `v_status` is correct and the `column` derivation stays
   coherent. This is the §3 trap, solved by measurement rather than by changing
   v007's deliberate `column = EXCLUDED."column"` semantics.
3. When `--status` **is** given, the existing no-op honesty gate is unchanged.
4. `--assignee`, `--depends-on`, `--correlation-id` are identifier-ish and go
   through the same `_check_name`/`_check_uuid` allowlist validation every other
   identifier flag uses (security invariant B-1).
5. `--plan` is free text and is quote-doubled via the existing `_sql_literal`
   path — never interpolated (B-1).
6. `--depends-on` is a comma-separated uuid list → `%s::uuid[]`, matching the
   `p_depends_on UUID[]` parameter.
7. Output stays honest: the success line names which fields were written, and
   the existing post-write recheck pattern (ADV-12676-1) is reused for the plan
   text so a silent-failure path cannot print a checkmark.

### 4.3 The hand-out surface (and what it does *not* claim)

`update <id> --assignee <worker> --correlation-id <corr>` is the orchestrator
hand-out: after it, the slice is **machine-visible** to that worker
(`list --assigned`, `assignee IS NOT NULL`), which is the property `9fb2ddb6`
names as missing (0 of the open slices had an assignee). It does **not** claim to
be atomic with the bus send — the row's own text allows either ("or a dispatch
helper that sets assignee + correlation_id and sends the bus TASK_REQUEST
atomically"). Making the two atomic needs a transactional outbox and is a
separate slice; this plan sets the field and leaves the send to the existing
`hc send` path, and says so in the row.

### 4.4 Verification that will be shown

- RED: the new schema/CLI tests against the pre-change tree (named failures).
- GREEN: the same tests after the change.
- **The reviewer's requested arity assertion** (ADV-13847-1): assert exactly ONE
  `tasks.task_upsert` exists in `tasks` and that its
  `pg_get_function_arguments` resolves (no "more than one function" error) with
  21 parameters — the exact failure mode block A demonstrates, asserted so it
  cannot regress.
- The pre-existing task-db unit suite and the tasks schema test
  (`tests/test_task_db_unit.py`, `tests/test-tasks-schema.sh`) still pass — the
  regression guard for the single write path.
- A grant assertion: every role that held `EXECUTE` before the migration still
  holds it after (block D is the before-set).
- The migration applied on this host (`task-db.py --apply-schema`) and **the
  live round trip**: `update <scratch id> --plan …` then read the row back, plus
  a metadata-only update on a row that is `in_progress` proving `column` stayed
  `in_progress` (the §3 trap, exercised for real — block C is what it must NOT
  do).
- Every command printed beside its own exit code; numbers quoted only from the
  committed transcript.

## 5. Rejected options

| Option | Why not |
|---|---|
| Write `plan` with raw SQL from the CLI | The row forbids it, and it bypasses the single write path that enforces status/column coherence (B-4). |
| Bare `CREATE OR REPLACE` to add `p_plan` (rev 1) | **Measured false** (ADV-13847-1): it leaves two overloads and breaks the verification command. Corrected to `DROP` + `CREATE` + re-grant, §4.1. |
| Add a `set_plan()` SECURITY DEFINER function | A second write path for one column; `task_upsert` already owns every column including `assignee`/`depends_on`/`correlation_id`. `survey-before-action` §2: patch the tool that covers the need. |
| Make `update` pass `p_status = NULL` for metadata-only writes | **Measured fatal** (ADV-13847-2): `23514 … tasks_column_check` (§3, block C). |
| Make the CLI read-modify-write the whole row | Turns a one-column update into a lost-update race, and re-sends columns the caller never named. |
| Insert `p_plan` anywhere but last | Changes the positional signature that all six call sites depend on. |
| A new `handout` function that assigns to *another* agent | `claim_slice`'s self-only guard exists on purpose (a worker claims only for itself). An orchestrator assigning *out* is a different privilege and belongs in the same reviewed change as the RLS story, not smuggled in as a side effect. |

## 6. Out of scope (reported, not silently dropped)

- **Cross-host row transport** — the second half of `9fb2ddb6`'s "fleet-scope
  slices are invisible to workers" (moses' DB holds 0 of esther's 16 fleet
  slices). Unchanged by this plan; it is the git-backed transport roadmap, not a
  write-surface change.
- **`list --claimable`** — unchanged; a slice with an assignee is intentionally
  *not* claimable.
- The `p_column` derivation semantics of v007 are deliberately **not** changed
  (§4.2 rule 2 avoids needing to).

## 7. What "done" means for row `9fb2ddb6`

Fix-direction items (a) and (b) ship in this change and are shown by the A/B
tests plus the live round trip. Item (c) — the morning pass dispatching over the
bus meanwhile — is already the practice (the 2026-10-27 pass dispatched `[cost/4]`
with `hc exec` and got three answers). The row can therefore move
`in_progress → completed` on that evidence, with the transport half explicitly
carried as its own tracked gap rather than folded into this closure.
