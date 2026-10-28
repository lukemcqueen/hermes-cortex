# The doctor must not apply DDL — health check vs. migration authority (plan, rev 1)

Backlog row **`72b2c69b-ae8a-4be6-88c3-cd65bf4bf87d`** (priority 2, personal,
owner esther). Cycle **#13935**, task id `doctor-apply-schema-leak`, session
`cron_1954deb5ad76_20261028_202110`. Author: **esther** (orchestrator).
Status: **plan — submitted to the governed reviewer BEFORE any code is written**
(operator standing rule, 2026-10-14).

The row was found by the 2026-10-27 build cycle (#13866) and deliberately left
unfixed there, because *"changing an enforcement/health check under the same
cycle as a schema change is exactly what `enforcement-change-safety` warns
against."* This is that separate cycle.

## 1. What the row asks for

Quoted from the row's FIX DIRECTION:

> decide whether the doctor should (a) read the version without applying (a
> SELECT on `tasks.schema_version`, WARN/FAIL when it needs raising) or (b)
> apply only the DEPLOYED copy's migrations against the default database; and
> make `cmd_apply_schema`'s candidate order prefer the deployed tree over the
> repo working tree.

This plan takes **(a) for the doctor** (a health check reports; it does not
mutate) **and fixes the candidate order** so the legacy `--apply-schema` path is
also safe for every other caller.

## 2. Measured starting state (raw probe output, this cycle)

Transcript produced by `docs/evidence/doctor-ddl-leak/probe-doctor-apply-schema.sh`
(run by this cycle; read-only — it applies nothing).

| Fact | Measured |
|---|---|
| The doctor runs `--apply-schema` as a **health check** | `~/.hermes-cortex/scripts/cortex_doctor/checks.py:5357`: `ver_out = run_bg([sys.executable, str(task_script), "--apply-schema"], …)`. The doctor runs on every `agent-message-handler` tick (~5 min). |
| `cmd_apply_schema` resolves `migrate.py` by candidate list | `ops/scripts/manage/task-db.py:1563-1569` |
| Candidate 1 is **`Path(os.environ.get("CORTEX_REPO", ""))/…`** | With `CORTEX_REPO` unset (measured: `CORTEX_REPO env = None`) that expression is the **relative** path `ops/services/tasks/migrate.py`. The probe reported `1. exists=True` only because its **cwd** was the repo. So the resolved migration authority depends on the *caller's working directory* — a second defect in the same function, independent of the repo-vs-deployed question. |
| Candidate 2 is the repo working tree | `exists=True  /home/esther/hermes-cortex/ops/services/tasks/migrate.py` — picked whenever candidate 1 misses (the doctor's own cwd). |
| Candidate 4 is the DEPLOYED tree | `exists=True  /home/esther/.hermes-cortex/services/tasks/migrate.py` — **last**, so it is never reached while a repo tree exists. |
| `cortex-update.sh` applies the DEPLOYED copy | `cortex-update.sh:3298`: `local tasks_migrate="${CORTEX_DEPLOY_HOME}/services/tasks/migrate.py"`. The deploy path and the doctor path resolve to *different* files. |
| The register map IS the deploy (stated contract) | `cortex-update.sh:446`: *"The register map IS the deploy. migrate.py discovers migrations by FILE — the repo applying cleanly proves nothing about any other host."* |
| Currently latent on this host, not active | live `tasks.schema_version` = **16**; deployed schema dir also reaches **v016**; `task_upsert` count = **1**, 21 args (`p_plan` last). The 10-27 deploy repaired the *state*; the code path that caused it is unchanged, so a **new uncommitted** migration file would still reach the live `mycortex` DB within ~5 minutes. |

Harm, stated plainly: an unattended health check, running every 5 minutes,
makes a host's **repo working tree** authoritative for production DDL and
bypasses the register-map contract — an unreviewed, uncommitted migration is
applied with no review, no commit and no deploy.

## 3. Design

### 3.1 The doctor reads the version; it does not apply it

`check_task_lifecycle_v2` (deployed `checks.py:5341`) currently does:

```
ver_out = run_bg([sys.executable, str(task_script), "--apply-schema"], timeout=120)
m = _re.search(r"version (\d+)", ver_out or ""); ver = int(m.group(1)) if m else 0
```

`--apply-schema` is the only thing standing between the check and the version
read. The function **already** loads `task-db.py` as a module and reads the DB
through its `psql()` seam for the RLS probe (`:5373-5391`). So the version read
becomes the same read-only seam — no new dependency, no new query language:

```
# load the module FIRST (moved above the version block)
ver_out = tdb.psql("SELECT COALESCE(MAX(version), 0) FROM tasks.schema_version;")
```

- FAIL if `ver < 5`, with the **same message and remedy** as today (the
  threshold and the wording are unchanged — this is a rewrite of *how* the
  number is obtained, not of the policy).
- `SystemExit` from `psql()` (schema v<5, table missing) is caught and mapped to
  the same FAIL, mirroring the existing `except SystemExit:` blocks below it.
- If the module cannot be loaded at all, FAIL (`cannot load task-db.py module
  for probe`) — today that path already exists for the RLS check; the version
  check simply joins it.

**New, and the "(a) WARN/FAIL when it needs raising" half of the row:** compare
the live version against the **deployed** schema dir's highest migration number
(`CORTEX_HOME/services/tasks/schema/vNNN__*.sql`). If the deployed tree is ahead
of the live DB, the check reports **WARN** with the exact remedy —
`bash cortex-update.sh` — instead of silently applying the difference. If the
deployed schema dir is absent, the comparison is skipped (no claim).

Why this is stronger than today, not weaker: today the check *heals* the
database using whichever tree the CWD happened to point at, and reports PASS
afterwards — including when it just applied an unreviewed file. After the
change, the check reports the divergence and names the deploy path that is
allowed to close it.

### 3.2 `cmd_apply_schema` resolves the DEPLOYED tree first

`ops/scripts/manage/task-db.py:1561-1569` becomes:

```
deploy_home = Path(os.environ.get("CORTEX_DEPLOY_HOME") or (Path.home() / ".hermes-cortex"))
repo_home   = Path(os.environ.get("CORTEX_REPO") or (Path.home() / "hermes-cortex"))
candidates = [
    deploy_home / "services/tasks/migrate.py",                 # deployed (reg-map target)
    deploy_home / "scripts/ops/services/tasks/migrate.py",     # deployed (legacy shape)
    repo_home / "ops/services/tasks/migrate.py",               # repo tree — LAST, fallback only
]
```

Two fixes in that list, both measured in §2:

1. **Order:** the deployed copy is what `cortex-update.sh:3298` runs and what the
   register map maintains; the repo tree is only a fallback for a host with
   nothing deployed.
2. **The relative-path defect:** `or (Path.home() / "hermes-cortex")` replaces
   the `""` default, so an unset `CORTEX_REPO` can no longer resolve candidate 1
   against the caller's cwd. The same `or` default is applied to
   `CORTEX_DEPLOY_HOME`.

No behaviour is removed: a host with no deployed copy still resolves its repo
tree, exactly as today.

### 3.3 Scope boundary (stated, not implied)

This changes **the resolution of DDL**, not the DDL itself. No migration file,
schema object, function, grant or RLS policy is touched. `--apply-schema` keeps
its contract ("apply the deployed tree's migrations"); it stops being able to
apply an *undeployed* tree.

## 4. Verification that will be shown (REAL, this cycle)

- **RED then GREEN** for `tests/test_doctor_no_ddl_schema_probe.py`:
  - the doctor source contains no `--apply-schema` call, asserted the way
    `tests/test_task_queue_evidence.py:65` already asserts it for
    `task-queue-evidence.py` (`assert '"--apply-schema"' not in src`);
  - `cmd_apply_schema`'s candidate list resolves the **deployed** path first,
    with `CORTEX_REPO` both **unset** and set to the repo;
  - the unset case yields an **absolute** path (the relative-path defect).
  RED = both assertions against the pre-change files (they fail: the call site
  exists and the deployed copy is last).
- **The live read-only probe, on this host:** the new version read returns
  `16` and the check reports PASS; run against the deployed `checks.py`.
- **The doctor still runs green end-to-end:** `cortex-doctor.py` exits with no
  new FAIL, and the `Task Lifecycle v2 schema` line is read from the transcript
  (not retyped).
- **No mutation:** `tasks.schema_version` and `pg_proc` counted for
  `task_upsert` before and after the doctor run — unchanged.
- `python3 -m py_compile` on both changed files, and the existing
  `tests/test_task_db_unit.py` + `tests/test_task_db_v4.py` suites still pass.
- Deployed via `cortex-update.sh` and the **DEPLOYED** copies diffed against the
  repo source (ignoring the `# SOURCE:` header), because a green run on the repo
  copy proves nothing about the deployed one.

## 5. Rejected options

| Option | Why not |
|---|---|
| Leave the doctor applying, but point it at the deployed copy (option b alone) | A *check* would still mutate production DDL on a 5-minute tick, with the DDL authority decided by which tree happens to be deployed. The doctor's own contract is to report, not to heal — and `--apply-schema` MUTATES is already documented one file over (`task-queue-evidence.py:116`). |
| Delete the version check from the doctor | It is the assertion that a host silently degraded to v1 semantics is noticed. Kept, with the read changed. |
| Compare against the repo tree's max version instead of the deployed one | The repo tree is exactly the authority this row removes; comparing against it would re-import the defect as a warning. |
| Make the doctor call `migrate.py --dry-run` | It prints what it would apply but still resolves `migrate.py` by the same broken candidate order — it moves the defect, not fixes it. |
| `CREATE OR REPLACE` / reach into the migration files | Nothing in the schema is wrong. The defect is *who is allowed to pick the runner*. |
| Raise `V5_MIN_SCHEMA` in the CLI to refuse `--apply-schema` outright | Would break the legitimate deploy path (`cortex-update.sh` applies via `migrate.py`, not via this CLI) and any installer that relies on `--apply-schema` as the documented DDL entry point. Out of scope; not needed. |

## 6. Out of scope (reported, not silently dropped)

- **Every other caller of `--apply-schema`** (`task-queue-evidence.py`,
  installers, `./run` scripts) inherits the fixed candidate order but is not
  otherwise audited here — the row scoped this to the doctor and the resolver.
- **The 5-minute doctor cadence** is unchanged.
- **The 2026-10-27 migration-file race** (v016 reaching production before it was
  committed) is historical state; this change makes it non-repeatable, and no
  retroactive claim is made about it.
