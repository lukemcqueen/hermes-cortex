# PLAN — task queries: default scope = the caller's own repo ONLY (cycle 13347)

Author: esther (orchestrator). Cycle: task-scope-default-own-repo (13347).
Status: PLAN, pre-build. Submitted to the governed reviewer for findings.

## 1. Reported problem (operator, 2026-10-19)

"for titus pi, the tasks list is 'too broad' when we are already in a repo. we
should only see tasks for that repo alone when inside a repo (or at minimum the
default would be that, and maybe a switch to see all)."

## 2. Measured state of the store (read-only, mycortex_reader_esther, 2026-10-19)

    SELECT COALESCE(repo,'(untagged)'), status, count(*) FROM tasks.tasks GROUP BY 1,2;

    hermes-cortex|pending|1
    (untagged)|blocked|3
    (untagged)|paused|10
    (untagged)|pending|34
    (untagged)|waiting|2

49 of 50 rows are untagged. Composition of the untagged set:

    SELECT scope, created_by, kind, source, count(*) WHERE repo IS NULL GROUP BY ...;
    fleet|esther|slice|manual|19
    personal|esther|-|inbox|18
    personal|esther|-|manual|5
    fleet|esther|story|manual|3
    personal|esther|-|session|3
    personal|esther|-|governance|1

Cause of the "too broad" symptom: the scoped SQL is
`AND (CAST(? AS text) IS NULL OR t.repo = ? OR t.repo IS NULL)` — untagged rows
are returned to EVERY repo's session. Since the untagged bucket is the entire
backlog, a session inside a project repo receives the whole fleet backlog, and a
strictly repo-scoped session receives nothing (there is one tagged row in total).

## 3. Code map

- `ops/scripts/manage/task-db.py:102` `_REPO_CLAUSE_UNFILTERED` = `AND (CAST(? AS text) IS NULL OR t.repo = ?)` — used for `repo=ALL`.
- `ops/scripts/manage/task-db.py:103` `_REPO_CLAUSE_SCOPED` = the unfiltered form + `OR t.repo IS NULL` — the current default.
- `ops/scripts/manage/task-db.py:121` `_repo_clause(resolved)` -> `_REPO_CLAUSE_UNFILTERED if resolved.fleet else _REPO_CLAUSE_SCOPED`.
- `ops/scripts/manage/task-db.py:125` `_repo_params(resolved)` -> `[None, None]` for fleet, else `[slug, slug]`.
- `ops/scripts/manage/task-db.py:502` `SELECT_SQL_TEMPLATE` + `:516` `select_sql(repo_clause)`; `PENDING_SQL_TEMPLATE` carries the same placeholder.
- Call sites of `_repo_clause`: `cmd_list:559`, `cmd_list_claimable:868`, `cmd_list_assigned:910`, `cmd_list_board:950,973,986`, `cmd_pending:1101`.
- `ops/scripts/manage/task-db.py:605` `cmd_add(...)`: `repo` is passed through to `tasks.task_upsert` with NO default (`:661-664` passes `repo` bare; `project` DOES default to `"hermes-cortex"`). This is where the untagged pile comes from: nothing tags a row unless the caller passes `--repo`.
- `ops/scripts/cortex_lib/session_repo.py:87` `resolve_query_repo(explicit, repo_path, repo_slug)` — the single resolver (explicit -> injected -> `CORTEX_SESSION_REPO` -> cwd git repo -> None), returns `ResolvedRepo(slug, source, fleet, path)`; `FLEET_ALL = "ALL"` at `:49`.
- `mcp-servers/task-mcp.py:119` `_REPO_DESC`, `:125` `_REPO_SCOPE_NOTE` (tool descriptions); handlers `_task_list:192`, `_task_pending:201`, `_task_list_claimable:264`, `_task_list_handed_out:270`, `_task_board:276`; schemas `:352-373`, `:452-483`.
- Tests that pin the current rule: `tests/test_task_query_repo_scope.py:13,214` (asserts `t.repo IS NULL` is present in the scoped SQL), `tests/test_task_db_unit.py`, `tests/test_runtime/test_task_query_repo_injection.py`, `tests/run_task_query_repo_scope_repro.py` (real Postgres + real MCP over stdio, pinned pre-fix revision 55887b47).
- Docs: `docs/design/task-workflow.md:288-326` (resolution ladder + the "untagged stay visible" consequence), `docs/troubleshooting.md` ("Task queries show me nothing"), skills `devops/task-queue-workflow`, `devops/task-persistence`.

## 4. Proposed change

1. **Default scope becomes strict.** When a repo resolves, the query uses
   `AND (CAST(? AS text) IS NULL OR t.repo = ?)` — own repo only, no untagged.
   Applies to `list`, `pending`, `list --board`, `list --claimable`,
   `list --assigned` (one helper, all call sites).
2. **`repo=ALL` unchanged** — every repo's rows plus untagged (explicit fleet view).
3. **New explicit switch `include_untagged`** (MCP bool) / `--include-untagged`
   (CLI): restores today's "my repo + untagged" behaviour for callers that need
   the fleet worker pool (untagged fleet slices) or legacy rows. Implemented as
   `_repo_clause(resolved, include_untagged)` choosing between two constants —
   same two params, no SQL restructure.
4. **Tag at creation.** `cmd_add` (`:605`): when `--repo` is OMITTED, default the
   new row's repo to the caller's RESOLVED session repo (same resolver, same
   ladder), instead of NULL. With no resolvable repo the row stays untagged
   exactly as today. Without this, a strict default hides a task the caller just
   minted inside its own repo (self-invisibility), and the untagged pile keeps
   growing.
5. **Fail-closed rule unchanged** — an unresolvable repo still returns NOTHING,
   and `repo=ALL` remains the only fleet-wide view.
6. **Docs + skills** updated in the same cycle: `docs/design/task-workflow.md`
   §"Repo scoping", `docs/troubleshooting.md`, `skills/devops/task-queue-workflow`
   (the worker-pool paragraph must name `--include-untagged`), MCP tool descriptions.

## 5. Options considered and rejected

- **(a) Keep `OR t.repo IS NULL`, fix the data instead (backfill tags).** Rejected:
  the untagged bucket is not derivable per row — 19 fleet slices and 3 fleet
  stories describe non-repo content (content/marketing), 18 rows came from the
  inbox mint with a bare-token body. A guessed tag silently reassigns ownership
  and the reviewer cannot check it; the query rule is the part that is provable.
- **(b) `t.repo = ? OR t.created_by = <caller>` as the default.** Rejected: in this
  store every noise row is `created_by=esther`, so an unrelated repo session
  would still receive 49 rows — the reported symptom survives. It also makes the
  scope depend on who is asking rather than on the repo.
- **(c) Make only `task_list` strict, leave the claim/hand-off pools as they are.**
  Rejected: two scopes for one rule. A worker would see an untagged slice in the
  claimable pool, claim it, and then not see it in `list` — the split-brain the
  cycle-12593 fix was written to end.
- **(d) A per-session config key instead of a query parameter.** Rejected as scope:
  the switch belongs where the query is made (one call may legitimately want the
  pool and another the repo view), and a config key cannot be exercised by the
  stdio repro harness.

## 6. Impact / risk

- The fleet (untagged) claim pool becomes opt-in for a worker session inside a
  project repo. Mitigation in the same cycle: `--include-untagged` documented in
  the worker-facing skill and in the MCP tool description; the orchestrator crons
  already read with `--repo ALL` (`ops/install/cron-manifest.yaml:1202,1220`,
  `ops/scripts/install/install-orch-crons.sh:457,474`), so the morning/evening
  passes are unaffected.
- `cmd_add` defaulting repo is a WRITE-path behaviour change for every agent.
  Bounded to: a row minted with no `--repo` from a session whose repo resolves.
- Blast radius of the query change is one helper plus its 7 call sites; the read
  regression harness (`tests/run_task_query_repo_scope_repro.py`) drives the real
  MCP server over stdio and asserts the PRE-FIX revision leaks, so the
  before/after comparison stays discriminating.

## 7. Verification plan

- Hermetic unit tests: strict default excludes untagged; `include_untagged`
  includes it; `repo=ALL` unchanged; unknown repo still returns nothing (no DB
  contact); `cmd_add` with no `--repo` in a resolved repo mints `repo=<slug>`, and
  with no resolved repo mints NULL.
- Real-path: `python3 tests/run_task_query_repo_scope_repro.py` (real Postgres +
  real MCP over stdio) extended with a strict-default case; `python3 -m pytest
  tests/test_task_query_repo_scope.py tests/test_task_db_unit.py
  tests/test_runtime/test_task_query_repo_injection.py -q`.
- Deployed-path proof: run the deployed `~/.hermes-cortex/scripts/task-db.py`
  after `cortex-dogfood.sh`; capture transcripts under `docs/evidence/`.
