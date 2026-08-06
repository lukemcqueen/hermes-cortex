# Mycortex Multi-Tenancy — Per-Profile Reader Roles

> Status: implemented 2026-08-06 · Luke directive: *"imagine 100 employees of
> a company sharing one brain. We want what's best for the longterm, not just
> convenient short term."*

## What changed and why

The mycortex RLS policy keys on `CURRENT_USER`:

```sql
USING (mycortex.is_source_visible(source_id, (CURRENT_USER)::text))
```

So the schema was **already multi-tenant-ready**: a reader sees a page iff its
source is federated OR the connecting role holds a `source_grants` row.
Previously the CLI connected as ONE shared `mycortex_reader` role for every
profile — so an isolated source granted to `mycortex_reader` was visible to
*every* profile that connected as that role. Correct for single-tenant,
a cross-tenant leak the moment profile #2 lands.

**The fix (2026-08-06): per-profile reader roles.** Each profile connects as
`mycortex_reader_<profile>`:

| Role | Purpose |
|---|---|
| `mycortex_reader` | Base capability floor — schema grants (SELECT pages/chunks, EXECUTE functions). NO personal source grants. |
| `mycortex_reader_<profile>` | Per-tenant reader — `LOGIN INHERIT mycortex_reader` (inherits schema grants) + the profile's own `source_grants`. |

Two orthogonal axes, both enforced by the existing schema:
- **What you may touch** (schema) → role membership inherits `mycortex_reader`'s grants
- **What you may see** (data) → RLS `CURRENT_USER` + per-profile `source_grants`

Tenant #100 needs **zero policy changes** — create the role, grant its sources,
RLS isolates it automatically.

## What agents must do (migration, per-host)

**Nothing manual — `cortex-update.sh` does it all.** The deploy runs
`install-profile-reader-role.sh` which, in one idempotent pass:

1. Creates `mycortex_reader_<profile>` (LOGIN INHERIT mycortex_reader) if missing
2. **Auto-migrates legacy grants**: any `source_grants` row where
   `role_name = 'mycortex_reader'` on a non-federated source is moved to the
   profile role — so a host's OWN pre-existing isolated sources stay visible
   after the CLI starts connecting as the profile role (without this, the
   host's own pages would vanish from search: profile role has no grant → RLS
   shows zero rows)

Idempotent: after the first run no `mycortex_reader` grant rows remain, so the
UPDATE is a no-op on every later deploy.

### Verification only (no manual steps)

```bash
# 1. Confirm the profile role exists (deploy creates it):
sg docker -c "docker exec -i mycortex-postgres psql -U mycortex -d mycortex -t -A \
  -c \"SELECT rolname FROM pg_roles WHERE rolname LIKE 'mycortex_reader_%'\""

# 2. Verify NO personal source is granted to the shared reader:
sg docker -c "docker exec -i mycortex-postgres psql -U mycortex_admin -d mycortex -t -A \
  -c \"SELECT g.role_name, s.name FROM mycortex.source_grants g \
      JOIN mycortex.sources s ON s.id = g.source_id ORDER BY 1\""
# → should show ONLY mycortex_reader_<profile> rows for isolated sources

# 3. Verify search still works as YOUR profile (dreams/pages visible):
AGENT_NAME=<your-profile> mycortex search "test query" --limit 3

# 4. Verify isolation: a DIFFERENT profile sees ZERO of your rows:
AGENT_NAME=<other-profile> mycortex search "<your unique term>" --limit 3
# → (no results) for your isolated source
```

> **Manual fallback** (only if a host predates the auto-migration and needs it
> now): `UPDATE mycortex.source_grants SET role_name = 'mycortex_reader_<profile>'
> WHERE role_name = 'mycortex_reader' AND source_id IN (SELECT id FROM
> mycortex.sources WHERE NOT archived AND NOT is_federated);`

## How the pieces work

### Role creation — `install-profile-reader-role.sh`

- Creates `mycortex_reader_<profile>` (LOGIN INHERIT) + `GRANT mycortex_reader TO ...`
- **Auto-migrates legacy shared-reader grants** on non-federated sources to the
  profile role (idempotent — no-op once migrated)
- Runs as the `mycortex` superuser in-container (`mycortex_admin` has no
  CREATEROLE — verified `f/f`)
- **Profile resolution order** (identical in the CLI): `HERMES_PROFILE` env →
  `AGENT_NAME` env → `hostname`. ⚠️ NEVER scan `~/.hermes/profiles/*/`
  alphabetically — the first entry is NOT the active profile (observed
  2026-08-06: `personal` dir exists but the session is `default`/esther).
- SQL is piped via heredoc+stdin, never `-c "$SQL"` through nested
  double-quoted `sg docker -c` — `$$` re-expands to the shell PID at
  interpolation (observed: `DO 2640698` syntax error).

### CLI — `reader_role()`

`search` and `list` connect as `mycortex_reader_<profile>` (resolved per
above). `stats`/`doctor`/`sources add` keep using `mycortex_admin` (audit /
registration role — needs full visibility by design).

### Registration — `sources add`

Auto-grants ISOLATED (non-federated) sources to the profile role — never the
shared `mycortex_reader`. Federated sources need no grant (visible to all
readers, PII-gated).

## Why this is safe by construction

- **RLS fail-closed:** an un-granted profile sees ZERO rows, even on shared disk
- **Isolated ≠ broken:** `mycortex search` returning `[]` for an isolated
  source is the design working — fix visibility via grants, never by
  weakening RLS
- **30-second tenant-isolation test** (per new tenant): register → sync →
  search as reader (expect ZERO rows) → grant → search again (expect rows)
- **The shared `mycortex_reader` never holds personal-source grants** — it is
  the capability floor, not a data grant

## Verification (what "done" looks like)

| Check | Command | Expected |
|---|---|---|
| Profile role exists | `psql -c "SELECT rolname FROM pg_roles WHERE rolname LIKE 'mycortex_reader_%'"` | `mycortex_reader_<profile>` present |
| No shared-reader grants | grants query (step 3 above) | no `mycortex_reader` rows for isolated sources |
| Your search works | `AGENT_NAME=<profile> mycortex search "x"` | your pages rank |
| Cross-profile isolation | `AGENT_NAME=<other> mycortex search "<your term>"` | zero hits on your source |

## History

- 2026-08-06: per-profile reader roles implemented (`2ccacf06`→`0de5eb07`);
  initial stopgap (shared-reader grant + doc note) replaced after Luke
  challenged it as convenient-but-not-elegant.
- See also: `docs/design/mycortex-dream-layer.md` §Multi-Tenancy & Profile
  Separation (dream-layer tenant rules).
