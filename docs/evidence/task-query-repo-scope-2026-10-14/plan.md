# PLAN — repo-scoped task queries (cycle 12593, task `task-query-repo-scope`)

Reported by Titus: `mcp__tasks__task_pending` (and `task_list`, `task_board`, …) return
ALL pending tasks for an agent across every repo/project; no repo filter, no cwd
awareness. Agents then work and report tasks belonging to another repo.
Operator instruction (Luke, verbatim): **"Fix this for Titus. If the repo is unknown or
the current dir is unknown then NO tasks should be returned."**
That overrides Titus's proposed AC-3 ("repo omitted → keep returning all repos"): an
unresolvable repo must yield ZERO tasks, never an all-repo result.

## Survey (what exists today — measured, not assumed)

1. `ops/scripts/manage/task-db.py` (1183 lines):
   - `cmd_pending()` (L905) takes NO repo parameter at all — the reported leak.
   - `cmd_list()` (L449) accepts `repo`, but SELECT_SQL (L439) is
     `AND (CAST(? AS text) IS NULL OR t.repo = ?)` → a NULL/legacy untagged row is
     EXCLUDED when a repo is given (Titus wants `repo = ? OR repo IS NULL`), and when
     `repo` is omitted it selects every repo.
   - `cmd_list_board()` (L781), `cmd_list_claimable()` (L725), `cmd_list_assigned()`
     (L750) have no repo filter at all; their SQL is hardcoded.
2. `mcp-servers/task-mcp.py`: `task_pending` and `task_board` declare
   `inputSchema={"type":"object","properties":{}}`; `task_list_claimable` /
   `task_list_handed_out` take only `limit`. `_task_pending` (L180) calls
   `task_db.cmd_pending()` with no arguments.
3. The fleet ALREADY has a proven, documented session-repo resolver — do not invent a
   second one:
   `mcp-servers/loop-gov-mcp.py` `_session_repo_path()` (L540): injected `repo_path`
   → `CORTEX_SESSION_REPO` → (non-Hermes only) MCP child cwd git toplevel; the
   canonical governed repo is that module's fallback (L438). Documented in
   `docs/troubleshooting.md` L776-806 and `docs/runbooks/context-integration.md`.
4. The enforcer already learns the session's repo and injects it — but ONLY for
   governance calls (`plugins/governance-enforcer/__init__.py` L1087:
   `if tool_name.startswith("mcp__loop_governance__"): args["repo_path"]=…;
   args["repo_slug"]=…`). `mcp__tasks__*` gets nothing.
5. MEASURED on this host (esther), the running tasks MCP server (PID masked):
   ```
   $ pgrep -af task-mcp
   <pid> /home/<user>/.hermes-cortex/venv/bin/python3 <deploy>/scripts/task-mcp.py
   $ readlink /proc/<pid>/cwd
   /home/<user>
   $ tr '\0' '\n' < /proc/<pid>/environ | grep -E '^(CORTEX_SESSION_REPO|PWD|HOME)='
   HOME=/home/<user>
   ```
   → ONE shared MCP child per host, spawned by the gateway daemon; its cwd is HOME
   (NOT a git repo) and it has no `CORTEX_SESSION_REPO`. So cwd alone CANNOT identify a
   Hermes session's repo: that is why the enforcer injection is required for Hermes.
   A pi/Claude/Codex MCP child, by contrast, is spawned inside the session's project.

## Resolution ladder (single implementation, in the engine)

```
1. explicit `repo` argument (tool arg / CLI --repo)         -> used as-is (_check_name)
2. enforcer-injected `repo_path` / `repo_slug` (Hermes)     -> validate real git repo -> Path.name
3. CORTEX_SESSION_REPO env (documented lever, absolute path or NAME) -> validate -> slug
4. MCP child cwd `git rev-parse --show-toplevel`            -> Path.name  (pi-style harnesses)
5. host-canonical governed repo ($HOME/hermes-cortex|.hermes-cortex, .git present) -> name
6. otherwise -> repo is UNKNOWN -> **return NO tasks** (never all repos)
```
Step 5 mirrors the existing tested fleet behaviour (`loop-gov-mcp._derive_slug`
Priority 1) so Hermes/cron callers whose cwd is HOME keep working instead of silently
digesting nothing; step 6 is the operator's fail-closed rule. Flagged for the reviewer:
step 5 is a deliberate deviation from a literal reading of "unknown -> none" (it keeps
~/hermes-cortex rows + NULL-tagged rows visible for cron/CLI callers); it is surfaced to
the operator in the delivery, not hidden.

## Changes

**A. `ops/scripts/cortex_lib/session_repo.py` (new, shared; added to the deploy map)** —
`resolve_query_repo(explicit=None, repo_path=None, repo_slug=None) -> ResolvedRepo|None`
implementing ladder steps 1-6, exposing `.slug` and `.source`
(`explicit|injected|env|cwd|canonical`). One implementation, imported by the task engine;
`loop-gov-mcp`'s helpers are NOT modified in this cycle (see "Deliberately out of scope").

**B. `ops/scripts/manage/task-db.py`** — repo scoping on every task QUERY:
```python
def cmd_pending(repo=None, repo_path=None, repo_slug=None, explain=True):
    r = resolve_query_repo(repo, repo_path, repo_slug)
    if r is None:                      # operator rule: unknown repo -> NO tasks
        print("[]")
        if explain:
            print("task_pending: repo unknown (no --repo, no injected repo, no "
                  "CORTEX_SESSION_REPO, cwd is not a git repo) - returning no tasks "
                  "rather than every repo's tasks.", file=sys.stderr)
        return
    raw = psql(build_query(PENDING_SQL, [r.slug, r.slug]))
```
```sql
-- PENDING_SQL / SELECT_SQL (replaces the plain `t.repo = ?` clause)
AND (CAST(? AS text) IS NULL OR t.repo = ? OR t.repo IS NULL)
```
`cmd_list`, `cmd_list_board`, `cmd_list_claimable`, `cmd_list_assigned` take the same
`(repo, repo_path, repo_slug)` trio and the same fail-closed branch; `--repo` CLI flag
added to `pending`, `list --board`, `list --claimable`, `list --assigned`. New parameters
are optional/keyword so existing callers and tests keep working.

**C. `mcp-servers/task-mcp.py`** — `repo` (string, optional) added to the inputSchema of
`task_pending`, `task_board`, `task_list_claimable`, `task_list_handed_out`
(`task_list` already has it); handlers pass `args["repo"]` and also forward
enforcer/pi-injected `repo_path` / `repo_slug` keys when present. Descriptions state the
contract: scoped to the session's repo; `repo` omitted -> resolved from injected
identity/CORTEX_SESSION_REPO/cwd; unresolvable -> `[]` (never all repos).

**D. `plugins/governance-enforcer/__init__.py`** — extend the existing injection (L1087)
so `mcp__tasks__*` calls also carry `repo_path`/`repo_slug` when the session's repo was
observed (`_session_repo_path`/`_session_repo_slug`, both already implemented). Without
this the Hermes side has no per-session repo at all (measurement 5). Same "never
invented" rule as governance: no observed repo -> no injection -> the engine's ladder
decides. Verified by observation, not by a deploy banner (deploy != load).

**E. Tests (TDD; RED captured before GREEN)** — `tests/test_task_db_unit.py`: resolver
ladder precedence (explicit > injected > env > cwd > canonical > None), fail-closed
returns `[]` and issues NO psql call, SQL carries `OR t.repo IS NULL`; new
`tests/test_task_query_repo_scope.py` driving the REAL MCP server over stdio with
repo-tagged fixture rows and a `repo=` argument (asserting a foreign repo's rows are
absent and NULL-repo rows present); an enforcer test asserting `mcp__tasks__` calls
receive `repo_path` while an unobserved-repo session does not.

**F. Docs** — `docs/design/task-workflow.md` (repo scoping + the ladder table),
`docs/troubleshooting.md` (session repo identity: the task-query lever),
`skills/devops/task-persistence` + `skills/devops/task-queue-workflow` (one line each:
queries are repo-scoped; pass `repo=`).

**G. Evidence + deploy** — `docs/evidence/task-query-repo-scope-2026-10-14/{plan.md,red.txt,green.txt,scope-transcript.txt}`
committed IN this cycle; register the new cortex_lib entry, deploy
(`cortex-update.sh`), verify the DEPLOYED copies load, then push.

## Deliberately out of scope (stated, not silently dropped)

- `loop-gov-mcp.py` repo-identity helpers left as-is: refactoring 6.4k lines of
  governance code to share the helper is invasive and its current behaviour is already
  tested (`tests/test_non_hermes_repo_identity.py`). The new shared helper MIRRORS it and
  a test pins the shared semantics.
- Pi harness `<session_identity>` prompt block (Titus's steps 2-3): the in-repo pi
  extension (`ops/install/harnesses/pi/extensions/cortex-context.ts`, `before_agent_start`
  -> `systemPrompt`) is the right home; proposed as a SEPARATE follow-up cycle. Titus's
  own machine config is a cross-repo handoff (report + fix prompt), never a commit into a
  repo we do not own.

## Acceptance criteria (from begin_change)

AC-1 repo param + `repo = ? OR repo IS NULL` on all five query tools · AC-2 unresolvable
repo -> ZERO tasks · AC-3 explicit arg wins, every path unit-tested with RED shown ·
AC-4 deployed == repo + committed evidence · AC-5 harness fix delivered to Titus as a
handoff prompt.
