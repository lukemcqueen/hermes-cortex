# Dream→Todo Bridge + Todo-Storage Architecture — 2026-08-06 Session Trace

Full detail behind the SKILL.md bullets. Date: 2026-08-06 (Esther).

## 1. Dream→todo bridge (implemented, commit `379a6e39`)

Kustos proposed `docs/design/mycortex-dream-todo-bridge.md` ("both would be
useful" — Luke). The proposal assumed `bus.todos` existed ("verified
2026-08-06"). It did NOT — verified absent three ways:

1. Old `gbrain-postgres` container (Exited, not removed): started a temp
   container on its `langfuse_gbrain-postgres-data` volume (`docker run
   --rm -d -v <vol>:/var/lib/postgresql/data <image>`, no `-p` publish to
   avoid the 15432 port conflict; wait ~7s for "database system is ready";
   query; `docker rm -f`). Bus schema had messages/queues/archives/
   permissions/tokens/audit_log — **no todos**.
2. Migration dump `~/.hermes-cortex/backups/gbrain-migration-*.dump` —
   `strings | grep -i todo` → nothing.
3. Current `mycortex-postgres` — no `bus.todos`, no `bus.todo_upsert`.

**Root cause of the silent no-op:** `todo-db.py` fed SQL via stdin
(`subprocess.run(..., input=query)`). stdin-mode psql returns **rc=0 even
when the query fails** — the `if result.returncode != 0` guard never fired,
so `add` printed "✅ Todo added" while the row vanished. Compounded by
`sg docker -c` returning sg's own rc (0) regardless of the inner failure.

**The fix (three parts, all in `379a6e39`):**
1. `todo-db.py psql()` → `-c` mode: `_build_query_cmd()` appends
   `["-c", full_query]` for direct docker exec, or embeds
   `... -c <repr(query)>` INSIDE the sg command string (sg's `-c` takes one
   string — appending `-c query` as separate argv passes it to sg itself).
   Direct `docker exec` preferred when the user is in the docker group
   (`docker exec <container> true` probe; `id -nG | grep docker`).
2. `todo-db.py --apply-schema` — applies `core/cortex_bus/schema/todos.sql`
   idempotently (CREATE TABLE IF NOT EXISTS + CREATE OR REPLACE FUNCTION),
   platform-aware: docker exec on Linux, direct psql via mycortex.conf on
   macOS. cortex-update.sh runs it every update, **WARN not exit** — a fleet
   update must not be hostage to a peripheral DB; the idempotent schema
   retries next update.
3. `dream-todo-bridge.py` (`ops/scripts/manage/`) — Option A: knowledge-gap
   → `learn <topic>` todo (monthly, cap 4, priority 1); Option B: actionable
   insight → todo (all tiers, cap 2, priority 1-2, `[from dream YYYY-MM-DD]`
   traceability). **Caps/dedup/tenant-scoping enforced in CODE, not prompt
   prose** — the LLM judges actionability, the script guarantees the rules.

Verified end-to-end with a live nightly run (13:44): dream written back,
INDEX appended, 2 insights triaged, both SKIPped by the bridge's dedup
(covered by pending todos) — the guardrail proved itself. Full AC table
10/10 in the design doc.

## 2. Worker exclusion flaw — `bus` schema is orchestrator-only (Luke directive)

**"normal agents don't have a bus... todos need to NOT be depending on the
bus, unless this is intentional."** (Luke, 2026-08-06)

- Workers run `mycortex-postgres` (doctor `check_todo_db` runs on every
  host) but NEVER receive the `bus` schema — `setup-cortex-bus.sh` is
  `register_orch` (orchestrator-only deploy).
- So `bus.todos` silently does not exist for workers → no todos. The
  "fleet-visible, all agents see each other's todos" claim in
  `todo-persistence` skill was **gbrain-era truth** (ONE shared Postgres);
  post-2026-08-05 migration Postgres is PER-HOST, so the claim was already
  false — workers just never had the table to notice.

**Design direction (elicit/party in progress):** dedicated `todos` schema on
per-host mycortex-postgres, applied by cortex-update.sh on every host,
`todo-db.py` + consumers referencing `todos.*` only. Rule of thumb going
forward: `todos.*` = fleet-wide, `bus.*` = orchestrators only.

## 3. The `sg docker -c` + stdin-psql error-swallowing class

Anything that shells out to psql through `sg docker -c` with stdin mode can
silently report success for failed queries. Reusable verification recipe:

```bash
# does stdin-mode swallow the error? (expect rc=0 even on failure)
echo "SELECT * FROM bus.nonexistent;" | sg docker -c "docker exec -i mycortex-postgres psql -U mycortex -d mycortex -t -A"
echo "rc=$?"   # 0 — swallowed!

# -c mode propagates (expect rc=1)
sg docker -c "docker exec -i mycortex-postgres psql -U mycortex -d mycortex -t -A -c 'SELECT * FROM bus.nonexistent;'"
echo "rc=$?"   # 1 — propagates
```

Never pipe rc through `head` when testing — head's rc masks psql's. See the
`psql-automation` skill for the full playbook (promoted to repo as
`skills/devops/psql-automation/`, commit `f1e05d1d`).

## 4. Sibling-file path-hardcoding bug (lessons.py)

`session_mine.py` was fixed (9426e4c4) to write `~/brain/lessons/` but
`lessons.py` — the module `offline_knowledge` imports for stats/search —
still hardcoded `~/brain/kustos/lessons/` (introduced by an agent committing
under the shared `/home/luke` identity, 934db52b). Offline search read a
stale 241-file dir while 631 live lessons sat in the shared dir. Fixed
`c5510aa9`. **Lesson:** when a path bug is fixed in ONE of two sibling
files, grep for the sibling — `git log -S '<bad-string>'` finds every file
that ever contained it.

## 5. Install-script prompt escaping (cost 5 failed patches)

`create_cron "name" "schedule" "" "<prompt>"` prompt args are double-quoted
bash strings. Inside them, a single `\"` TERMINATES the bash string early —
the next angle-bracket placeholder (`<verb>`, `<profile>`) hits the shell
and `bash -n` fails `syntax error near unexpected token '<'`. The file
convention is `\\\"` (two backslashes + quote). Match the existing
convention exactly (check a known-good line with `sed -n 'Np' | cat -A`),
run `bash -n` after every edit, and if the patch tool's escaping fights you,
do a targeted Python line-edit:
`lines[i].replace('--content "..."', '--content \\\\\"...\\\\\"')`, verify
with repr, then `bash -n`.
