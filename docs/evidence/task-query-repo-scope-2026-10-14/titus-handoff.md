# Handoff to Titus — repo scoping: server side landed, harness side is yours

Cycle 12593 (`task-query-repo-scope`), revision `aa293f41`. Your bug report is
fixed where it was caused; the harness half (your steps 2 and 3) is the part we do
not own, so here is the exact contract plus what is already done for you.

## 1. What is fixed (shared, nothing for you to install)

`mcp__tasks__task_pending`, `task_list`, `task_board`, `task_list_claimable` and
`task_list_handed_out` are repo-scoped in the SHARED server
(`mcp-servers/task-mcp.py` + engine `ops/scripts/manage/task-db.py`):

- they take an optional `repo` parameter;
- the SQL is `repo = ? OR repo IS NULL` — your repo's rows plus untagged legacy
  rows, and NEVER another named repo's rows (`steadfaste-s1-model` can no longer
  appear in a `steadfaste` session);
- when `repo` is omitted the server resolves the session's repo itself, in this
  order: the identity the governance-enforcer injected for the session →
  `CORTEX_SESSION_REPO` → the git repo at the MCP child's working directory;
- **if none of those resolve, the query returns ZERO tasks** (operator rule
  2026-10-14) — never "all repos". `task_pending` prints `[]` and the reason goes
  to stderr; the fleet-wide view is now the EXPLICIT `repo="ALL"`.

So the recurring bug is gone for any harness whose MCP child runs inside the
session's project, and for Hermes (where the enforcer now stamps
`repo_path`/`repo_slug` onto `mcp__tasks__*` calls — the tasks server is one
shared child per host, so its cwd can never identify a session).

## 2. What is yours (pi side)

**a) If your pi spawns the task MCP child in the project directory** — nothing to
do: step 3 of the ladder resolves the repo from that cwd. Confirm with:

```bash
# from a session in ~/projects/steadfaste
python3 ~/.hermes-cortex/scripts/task-db.py pending --repo steadfaste | head -5
python3 ~/.hermes-cortex/scripts/task-db.py list --status pending          # cwd-resolved
```

**b) If pi launches MCP servers from a fixed/foreign cwd** (a gateway-spawned pi,
a shared daemon), pin the identity in the MCP `env` block — this is the documented
lever, not a new one:

```json
{"mcpServers": {"tasks": {"command": "python3",
   "args": ["/home/<you>/.hermes-cortex/scripts/task-mcp.py"],
   "env": {"CORTEX_SESSION_REPO": "/absolute/path/to/steadfaste"}}}}
```

`CORTEX_SESSION_REPO` accepts an absolute path (its basename becomes the slug) or
a bare repo name. With neither the cwd nor that variable resolvable, task queries
in that session will correctly return NOTHING — that is the fail-closed rule, not
a broken install.

**c) The `<session_identity>` prompt block (your step 3).** The right home is the
in-repo pi extension, `ops/install/harnesses/pi/extensions/cortex-context.ts`:
`before_agent_start` already returns `{systemPrompt}` (there is NO
`ctx.addSystemPrompt()` — calling one silently does nothing), so the block is a
pure addition there. That file is ours, and it is a SEPARATE follow-up cycle here
(the plan for cycle 12593 declared it out of scope rather than folding it in) —
if you want it sooner, take it as your own change against that file, or ask and
we will open the cycle named for it.

## 3. How the fix is proven (re-run it yourself)

```bash
python3 ~/hermes-cortex/tests/run_task_query_repo_scope_repro.py
```
It seeds a scratch Postgres (`tasks_repo_scope_test`, live rows untouched) with
one row in your repo, one in `steadfaste-s1-model` and one untagged, then drives
the REAL MCP server over stdio. It runs the PRE-FIX engine (pinned revision
`55887b47`) side by side and ASSERTS it leaks, so the comparison cannot silently
stop discriminating. Expected tail: `20 passed, 0 failed`. Full transcript:
`tests/artifacts/task-query-repo-scope-repro.txt`.

## 4. Where the details live

- `docs/design/task-workflow.md` §"Repo scoping of task QUERIES" — the ladder table.
- `docs/troubleshooting.md` §"Task queries show me nothing" — the empty-answer
  diagnosis path.
- `skills/devops/task-persistence`, `skills/devops/task-queue-workflow` — one
  paragraph each.
