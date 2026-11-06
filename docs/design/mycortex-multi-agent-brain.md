# Mycortex Multi-Agent Brain — one shared tree, per-profile subpaths (PLAN)

> Status: PLAN (not implemented) · 2026-11-06 · operator directive: *"Each
> agent should be writing to the same brain folder" + "support multiple agents
> on one server"* · model chosen: **1** — `~/brain` is THE shared folder;
> each profile owns `~/brain/<profile>/`; visibility partitioned per profile.

## Goal

All agents on a server write into ONE brain tree (`~/brain`), and several
profiles can run on one host with each seeing only its own brain content.
Today the brain is per-profile sources (`~/brain/<profile>` registered as an
isolated source per profile). Model 1 keeps the per-profile subpaths but makes
the shared root the single source of truth and partitions visibility by page
owner, so adding a profile never requires a new source, and one host can serve
N profiles.

## Current model (what changes)

- Filesystem: `~/brain/<profile>/{dreams,bible,lessons,...}` — already shared-root.
- Registration: `mycortex sources add <profile> ~/brain/<profile> --mode local`
  (one source PER profile), granted to `mycortex_reader_<profile>`; RLS
  `is_source_visible(source_id, CURRENT_USER)` fails closed.
- RLS is per-SOURCE: a profile with a grant on source S sees ALL of S. That is
  exactly why per-profile sources exist today — partition by source.
- DB layer already supports many profiles on one host (per-profile reader roles).

## Model 1 design

### Filesystem — unchanged
Keep `~/brain/<profile>/...`. All write paths (dream weekly/monthly/nightly,
bible, lessons, notes) keep writing to their profile subpath. No content moves.

### Source model — one `brain` source, per-PAGE owner
- New single source `brain` → `~/brain` (replaces the per-profile sources).
- Pages inside it get an **owner** derived as follows: a top-level file at the
  brain root with no path separator is ownerless (NULL, shared); content under
  a top-level directory takes that directory as owner (`~/brain/<profile>/...`
  → owner `<profile>`); the top-level directory name `shared` is **reserved**
  as the shared namespace and its contents are ownerless (NULL) too. `shared`
  must be special-cased because first-segment derivation alone would otherwise
  name it owner `shared`, breaking the shared-visibility contract.
- **Schema change (mycortex migration v006):** add `pages.owner` (text,
  nullable). Backfill from relpath first segment. Extend RLS so a reader sees
  a page in a non-federated source iff it holds a `source_grants` row for the
  source AND (`page.owner` IS NULL OR `page.owner = profile_of(current_user)`).
  A federated source stays visible to all (PII-gated) regardless of owner.
- Grants: `mycortex sources add brain ~/brain --mode local` auto-grants the
  shared reader floor and each profile's `source_grants` row covers only its
  own owner pages (the RLS now reads owner, so one source-level grant per
  profile is fine — visibility is narrowed to that profile's owner pages).

This keeps everything that made per-profile sources safe (fail-closed RLS,
profile resolution via `AGENT_NAME`/`HERMES_PROFILE`/`hostname` — never
`~/.hermes/profiles/*`) while collapsing N sources into one.

### CLI / registration changes
- `mycortex sources add brain ~/brain --mode local` replaces per-profile adds.
- `install-crons.sh` / `install-profile-reader-role.sh` provision one `brain`
  source and grant each present profile. The `source_grants` row is still
  REQUIRED for RLS (the owner column only narrows visibility WITHIN a granted
  source — it does not grant access); a profile created after the initial
  provisioning gets its `brain` source grant on its first install
  (`install-profile-reader-role.sh` must grant the single `brain` source, not
  a per-profile one). Acceptance case: a profile added post-provisioning sees
  its own owner pages and ZERO of another profile's.
- Migration: existing per-profile sources (`~/brain/<profile>`) are ingested
  into the single `brain` source. Owner is set **directly from the OLD SOURCE
  PROFILE name** (each old source == one profile) and each page's relpath is
  rewritten to `<profile>/<old_relpath>` (old relpaths start `dreams/`, `bible/`…,
  so first-segment backfill alone would wrongly name owner `dreams`). Old
  isolated sources archived (hard) once no reader depends on them. A migration
  test must assert migrated pages have owner equal to their old profile, not
  `dreams`/`bible`/etc., plus a page-count no-loss compare.

### Dream / note writes
- Prompts already write `~/brain/<profile>/dreams/...` — no change needed for
  the write path; the content becomes pages in the `brain` source with owner
  `<profile>`.
- Collision rule: per-profile INDEX files stay (`~/brain/<profile>/dreams/INDEX.md`)
  — two profiles never append the same file, because subpaths differ.

### PII / enforcement compatibility
- The enforcer's brain exemption (`_is_sanctioned_brain_write`) is `$HOME/brain`-
  anchored and covers any `~/brain/...` subpath — no change. The PII gate's
  public-surname allowance (2026-11-06) also applies to any `~/brain` write.
- The mycortex **PII federation gate** (federating a source requires a PII scan)
  is unaffected: the shared `brain` source is isolated (not federated), so it
  never enters the public query surface.

### Multi-agent-per-server (the second directive)
- DB: already true (per-profile reader roles on one host). Model 1 makes the
  FILESYSTEM + source model match: one host runs N profiles, each writes
  `~/brain/<profile>/`, each indexes into the single `brain` source, each sees
  only its owner pages. The daytime sync cron runs per host (it walks the whole
  `~/brain`), and the 30-second isolation test (another profile sees ZERO of
  your pages) is the acceptance gate.

## Changeset (what implementing means)

1. `ops/services/mycortex/schema/v006__page-owner.sql` — owner column + backfill +
   updated RLS policy + owner-aware `is_source_visible` (or a parallel predicate).
2. `ops/services/mycortex/sync` — derive owner from relpath.
3. `mycortex sources add brain` registration path + per-profile grants.
4. One-shot additive migration of existing per-profile sources into `brain`.
5. `install-crons.sh` / `install-profile-reader-role.sh` — single brain source
   provisioning.
6. Tests: `tests/test-mycortex-schema.sh` (owner RLS cases, isolation test per
   profile, backfill idempotency), a golden isolation case, migration re-run no-op.
7. Deploy registration (`cortex-update.sh`) + docs (this file + multi-tenancy doc).

## Verification (what "done" looks like)

- Two profiles on one host: A's search ranks A's pages; B sees ZERO of A's pages.
- Root/shared (ownerless) pages visible to all profiles on the host.
- `mycortex doctor --json` clean; `agent-mycortex-sync` runs once per host.
- Existing per-profile sources migrated with no page loss (count compare).

## History

- 2026-08-06: per-profile sources + reader roles (this replaces that granularity
  with one shared source + per-page owner RLS).
- 2026-11-06: PLAN written for the multi-agent shared-brain directive.