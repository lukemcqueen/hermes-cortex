# Fleet Migration + Verification-Ledger DDL — 2026-08-05 (Esther)

Companion to SKILL.md's "Migration to Dedicated mycortex-postgres" section and
`references/gbrain-reference-audit-2026-08-05.md`. Captures the two techniques
that fell out AFTER the main migration landed.

## 1. Fleet rollout: `migrate-gbrain-postgres-to-mycortex.sh`

`ops/scripts/manage/migrate-gbrain-postgres-to-mycortex.sh` (registered in
cortex-update.sh) is the repeatable per-host migration. Design rules worth
preserving in any similar fleet migration:

- **Idempotent re-run**: detects "new container healthy AND pages > 0" →
  prints "already migrated" and exits 0 BEFORE doing anything. This is what
  lets every fleet host run the same script safely (Esther's host verified
  exit-0 on re-run).
- **Non-destructive by default**: old container is STOPPED, never removed;
  dump kept in `~/.hermes-cortex/backups/gbrain-migration-<ts>.dump`.
  Rollback = `docker start gbrain-postgres` + revert the .env lines.
- **`--dry-run` and `--yes` flags** — dry-run prints the plan and exits; the
  interactive confirm can be skipped for unattended fleet EXEC.
- **Embed the re-apply SQL, don't reference schema files.** The roles/RLS/
  grants re-apply block is embedded in the script (not a path dependency on
  the repo schema dir) so the script is one-shot standalone on any host.
- **Password chain**: the new `MYCORTEX_PG_PASSWORD` reuses the OLD secret
  value (`GBRAIN_PG_PASSWORD` or `CORTEX_BUS_PG_PASS`) rather than generating
  a fresh one — verified by comparing hashes, never printed. This keeps the
  bus's `CORTEX_BUS_PG_PASS` working unchanged through the flip.
- **Restore errors are expected**: `pg_restore --no-owner --no-privileges`
  fails on role-dependent statements (policies reference missing roles) —
  grep them out, verify row counts, then re-apply roles/policies/grants
  separately. The restore is NOT failed by those errors.

## 2. Latent gap surfaced: `bus.command_verifications` DDL never installed

**Symptom:** every `hc send` prints
`⚠️ Verification recording failed (send still succeeded): ERROR: function
bus.record_dispatch(...) does not exist` — but the message DOES land
(msg_id returned).

**Root cause:** `hc.py` and `local-orch-fleet-command-verifier.py` call
`bus.record_dispatch()` / `bus.verify_command()`, but
`core/cortex_bus/schema/command-verifications.sql` was **never applied to any
live bus DB**. Bus schema files (queue.sql, auth.sql, todos.sql,
command-verifications.sql) are applied MANUALLY at bus setup — none are
registered in cortex-update.sh or install.sh. The migration to a fresh
container surfaced it because the new DB was born without the whole bus
schema layer; the old DB had it only because setup predated the file.

**Fix:** apply the idempotent DDL directly:
`docker exec -i mycortex-postgres psql -U mycortex -d mycortex -v ON_ERROR_STOP=1 -f core/cortex_bus/schema/command-verifications.sql`
→ creates `bus.command_verifications` + 4 functions
(record_dispatch / verify_command / get_pending_verifications /
cleanup_verifications). Verified: `hc send` then records cleanly.

**Lesson for similar migrations:** when a fresh DB container replaces an old
one, don't assume schema-layer DDL that "must have been applied" actually
exists in the repo's deploy path. Grep the repo for the function name; if it
only exists in a schema file that nothing registers/applies, install it
explicitly. The fleet migration script now does this automatically (step 4b).

## 3. Dashboard unit consolidation (unrelated but same session)

`hermes-cortex-dashboard.service` crash-looped ("Address already in use") for
weeks because an OLD duplicate unit `cortex-dashboard.service` (different
name, same server.py) had been running since Jul 23 and owned port 8901.
The doctor's crash-loop check only names the unit in auto-restart, not the
port owner. Fix: identify the real owner via
`cat /proc/<pid>/cgroup` (shows the unit), stop+disable+remove the stale
duplicate, `daemon-reload`, start the canonical unit. Then `reset-failed`
both names so systemd forgets the failed state.

## 4. `hc send` self-test gate: HC_AGENT default is "moses"

`hc.py`'s `load_config()` reads `HC_AGENT` from env or `~/.hermes-cortex/hc.env`,
falling back to `DEFAULT_AGENT = "moses"`. On ANY non-moses host (esther,
joseph, ...), a plain `hc send <self> <subject> <body>` is **REFUSED** with
"requires --self-tested" even when sending to yourself — the gate compares
`agent != my_name`, and my_name resolved to "moses" because the env var was
unset. Fix: `export HC_AGENT=esther` (or put `HC_AGENT=esther` in hc.env)
before self-testing. Then the self-send passes without the flag, and you can
dispatch fleet messages with `--self-tested`.

Also note: the `--self-tested` flag is a genuine gate, not a formality —
prove the identical flow on your own inbox first (send → verify pending →
confirm handler pickup), then re-issue for fleet agents.
