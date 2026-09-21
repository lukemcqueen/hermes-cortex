# gbrain Reference Audit — 2026-08-05 (Esther)

Classified survey for the "fully on mycortex / decouple postgres" task.
`FUNCTIONAL` = executes against gbrain at runtime → must change during
decouple. `STALE` = historical doc/log/skill text → leave as-is (it IS the
record). `ALREADY-STUBBED` = code path already points at mycortex, name only
remains.

## Live runtime state (Esther host, 2026-08-05)

- **mycortex is fully functional**: schema_version=3, 6 RLS policies, doctor
  green; sources `default` (git, 28 pages) + `hermes-cortex` (local, 1644
  pages), both federated; crons `agent-mycortex-sync` (*/15) +
  `agent-mycortex-retention` (daily 06:00) live. **No gbrain crons remain**
  (jobs.json grep = 0).
- **gbrain binary still installed** (`~/.local/bin/gbrain` → `~/.bun/bin/gbrain`,
  bun global, kept for rollback until 30-day purge window closes).
- **systemd user units** `gbrain-autopilot` + `gbrain-sync` exist but FAILED +
  disabled (decommission half-state, intentionally left).
- **`~/.gbrain/` dir exists** — config.json has `database_url:
  postgresql://gbrain:***@127.0.0.1:15432/gbrain` (macOS CLI fallback reads it).
- **Container** `gbrain-postgres` (pgvector/pgvector:0.8.0-pg17, up 12 days
  healthy, :15432→5432, `unless-stopped`) — see SKILL.md Postgres Decoupling
  section. Superuser role `gbrain` (rolsuper=t); mycortex roles
  admin/ingest/reader. DB `gbrain` holds schemas `bus` (23 msgs),
  `mycortex` (1726 pages / 29298 chunks), `public` (61 `gbrain_legacy_*`
  tombstoned tables). Total 183 MB.
- **Bus server** = `cortex-bus.service` (systemd user, uvicorn
  cortex_bus.server:app :8903) connects as `gbrain`/`gbrain` via
  `CORTEX_BUS_PG_*` from `~/hermes-cortex/.env` (PORT=15432, DB=gbrain,
  USER=gbrain). The ONLY live `gbrain|gbrain` backend is the bus.

## FUNCTIONAL gbrain references (fix during decouple)

| Location | What it does |
|---|---|
| `ops/scripts/manage/mycortex` (CLI) | `DB_DEFAULT = "gbrain"`; Linux psql via `docker exec gbrain-postgres psql -U <role> -d <db>`; macOS fallback reads `~/.gbrain/config.json` |
| `ops/services/mycortex/migrate.py` | `DEFAULT_DB = "gbrain"`, `docker exec gbrain-postgres`, url default `postgresql://gbrain:@127.0.0.1:15432/...` |
| `core/cortex_bus/queue.py` | bus PG defaults: `db="gbrain"`, `user` fallback `POSTGRES_USER` or `gbrain` |
| `~/hermes-cortex/.env` | `CORTEX_BUS_PG_DB=gbrain`, `CORTEX_BUS_PG_USER=gbrain`, `CORTEX_BUS_PG_PASS=gbrain_pg_pass` |
| `.env.example` | `CORTEX_BUS_PG_*` (only comment refs gbrain embedding model) |
| `ops/scripts/hc/hc.py` | `docker exec gbrain-postgres psql -U gbrain -d gbrain` |
| `ops/scripts/orch-bus/orch-bus-recover-timeouts.sh`, `ops/scripts/hc/recover-bus-timeouts.sh` | same exec pattern |
| `ops/scripts/manage/todo-db.py` | `GBRAIN_CONFIG=~/.gbrain/config.json`, url default `postgresql://gbrain:@127.0.0.1:15432/gbrain`, docker exec |
| `ops/scripts/agent/cortex-agent-manager.py` | `docker exec gbrain-postgres psql -U gbrain -d gbrain` |
| `ops/scripts/agent/install-worker.sh` | `docker exec gbrain-postgres psql -U gbrain -d gbrain` |
| `ops/scripts/agent/agent-diagnostic.py` | docker exec gbrain-postgres |
| `ops/scripts/agent/commands.py` | `available_services: ["cortex-bus", "gbrain", ...]`, service list `gbrain-sync` |
| `ops/scripts/bus/workflow-inspector.py` | defaults `PG_DB="gbrain"`, `PG_USER="gbrain"` |
| `ops/scripts/orch-bus/orch-bus-test.py` | docstring `CORTEX_BUS_PG_USER=gbrain` |
| `ops/scripts/health/health-vector-push.sh` | `pgrep -f gbrain` gates `SVC_OK` (metric [1]) + `V_GBRAIN` (metric [6]) |
| `ops/scripts/health/health-vector.py` | metric name `gbrain_sources_ok` (dir-existence check — rename only) |
| `ops/scripts/health/heartbeat.py` | `check_gbrain_sources()` (internally calls mycortex doctor — rename only); gbrain-autopilot service half-state check (decommission-aware) |
| `ops/scripts/health/agent-service-recovery.py` | `_fix_gbrain_stale_lock` + `_fix_gbrain_orphan_process` (runs every 5 min — dead decommission code) |
| `ops/scripts/health/agent-remediation-sensor.py` | gbrain autopilot half-state probes (decommission-aware) |
| `ops/scripts/health/cron-auto-remediate.sh` | `fix-gbrain` mode: `gbrain doctor --fast`, checks `~/.gbrain`, `gbrain-postgres` container |
| `ops/scripts/health/agent-system-alert-watchdog.py`, `agent-model-health-watchdog.py` | label/comment refs only (embeddings = mycortex too) |
| `ops/scripts/manage/cortex_doctor/checks.py` | gbrain daemon check (decommission-aware PASS/WARN — keep); remediation hints ~3119/3129 still say `docker exec gbrain-postgres psql -U gbrain -d gbrain` |
| `ops/offline/offline_knowledge.py` | `gbrain_search()` cascade: `bun gbrain query` — **live functional path** |
| `ops/scripts/cortex-update.sh` | still `register()`s dead `gbrain-wrapper.sh`, `gbrain-doctor-summary.py`, `install-gbrain-sync.sh`; `update_gbrain_binary()` no-op stub |
| `ops/install/install.sh` | installs gbrain binary (`bun install -g garrytan/gbrain`), `gbrain init --url`, gbrain sources/sync — **new hosts still get gbrain** |
| `ops/scripts/install/bootstrap-brain.sh`, `seed-project-brain.sh`, `cortex-profile.sh` | `$GBRAIN_CMD` sources add/sync |
| `dashboard/server.py` | `_find_pid(["gbrain autopilot", ...])` |

## STALE references (leave — historical record)

- `docs/gbrain-postgres-migration.md` (57), `docs/gbrain-v2-taxonomy.md`,
  `docs/gbrain-stale-lock-detection.md`, `docs/knowledge-isolation-architecture.md`,
  `docs/seeding-brain-content.md`, `docs/elicit/2026-08-01_mycortex-*.md`,
  `docs/design/mycortex-DESIGN.md` (S-012 gating language), `docs/agent-memory-pointer-pattern.md`
- `tests/fixtures/gbrain-baseline.json`, `tests/golden-queries.json`,
  `tests/test-mycortex-schema.sh` (hermeticity guard), `tests/test-bus-schema.sh`
- `skills/devops/gbrain-maintenance/` + its references (decommission target;
  mycortex skill is the replacement)
- `~/.hermes/logs/*`, `sessions/request_dump_*.json`, `cron/output/*`,
  `state-snapshots/`, `state/scripts-unique-backup-20260802/`, `state/remediate-seen.txt`,
  `data/loop-events/*.jsonl` — runtime artifacts, not source

## Decouple target (agreed with Luke 2026-08-05) — ✅ DONE same day

hermes-cortex-owned compose file, container `mycortex-postgres`, db `mycortex`,
role `mycortex` (superuser), volume `mycortex-postgres-data`, port 15432
unchanged. Migrate all 3 schemas (bus + mycortex + public legacy) via
pg_dump/restore; update every FUNCTIONAL reference above; keep old container
as rollback through the S-012 window (flip 2026-08-02 → purge eligible
~2026-09-01); then remove old container + volume + `~/.gbrain` + gbrain binary.

**Status: COMPLETED 2026-08-05 (commit 332d1e3e, 34 files).** Migration
verification numbers: pages 1726, chunks 29298, sources 2, RLS policies 6,
roles 4 (mycortex + admin/ingest/reader), extensions vector/pg_trgm/pgcrypto,
schema_version 3. Bus `/health` = `{"status":"ok","backend":"pgmq","queues":19}`
connecting as mycortex/mycortex. Old `gbrain-postgres` container left stopped
as rollback; gbrain systemd units removed + `reset-failed`; dead gbrain
scripts deleted from repo and deployed dirs. Remaining S-012 items: drop
`gbrain_legacy_*` tables + remove old container/volume/`~/.gbrain`/binary
after the purge window.

## Ordering notes

- Pause `agent-mycortex-sync` before the flip; resume after restore + verify.
- Stop bus → dump → restore → update env → start bus. Verify with
  `pg_stat_activity` (bus must connect as `mycortex`/`mycortex`), `mycortex
  doctor`, a real search, and one forced `cronjob action=run` sync.
- Do NOT drop the `public` gbrain_legacy_* tables — S-012 gates purge at 30
  days; moving them to the new DB is allowed (moving ≠ dropping).
