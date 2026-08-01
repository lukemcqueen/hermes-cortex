---
name: cwr-export-debug
category: software-development
description: Debug why CWR exports produce zero songs — trace the full export pipeline from UI → controller → job → engine → batch exporter, checking each layer for silent drop points.
---

# CWR Export Debug — Zero Songs Pipeline

## Export Flow

```
UI (export_cwr view)
  → SongsController#export_cwr
    → ExportCwrWorkerJob.perform_later (Sidekiq)
      → Cwr::ExportEngine#export_with_engine
        ├── :legacy  → CwrHelper#export_cwr  (inline processing, uses validated_cisnet_song)
        └── :service → Cwr::BatchExporter#run (new engine, own validate_song)
```

## Key Insight: Dual-Engine Architecture

The export has **two independent engines** with different validation rules. Zero output can happen in one but not the other.

### Controller Sets Default (line 1451)
```ruby
:export_engine => params[:export_engine]&.to_sym || :legacy,
```
- If the UI sends no `export_engine` param → `:legacy` is used
- But the **UI dropdown** defaults to `'service'` (view line 33: `selected: 'service'`)
- So clicking "Export" without changing the engine → **service engine**

### Engine Selection Priority
1. `params[:export_engine]` from UI (if sent)
2. Fallback in controller: `:legacy`
3. Job's re-built options_hash passes through whatever the controller set
4. `ExportEngine#select_export_engine` validates against `EXPORT_ENGINES = %i[legacy service compare shadow]`

## Engine-Specific Gates

### Service Engine (Cwr::BatchExporter#run)

**Song query** in `ExportCwrWorkerJob#perform` (line 128-131):
```ruby
Song.where(id: 100..Float::INFINITY, is_intl: false)
    .and(Song.where.not(iswc: [nil, '']))   # ← 74% of songs may be missing ISWCs
    .order(value: :desc).limit(item_end)
```

Then per-song `validate_song` checks (BatchExporter line 233-):
- ISWC present, format (`/\\A[TZ]\\d{10}\\z/`), and **mod10 checksum**
- At least one `SongCreatorShare`
- At least one publisher with `soc_code` (perf=0 share)
- At least one writer with `member_id NOT IN [nil, 99]` (perf=0 share)
- V014/V015 duplicate checks

**If ALL 126K songs with ISWCs pass these checks** (they do in this DB), the issue is likely the ISWC filter in the job query dropping 357K songs before the exporter sees them.

### Legacy Engine (CwrHelper#export_cwr, line 3353)

**Per-song check uses `validated_cisnet_song`**, which requires ALL of:
```ruby
def validated_cisnet_song(id_or_code)
  s = Song.find_by(id: id_or_code)
  if in_cisnet(s.id) &&                                     # 1. Song exists in CIS-Net DB
     MwiIswcSync.search(s.code).first&.status == 'SENT' &&  # 2. ISWC sync = SENT
     run_checks_for_cisnet_update(s.id, ...).blank? &&       # 3. No CIS-Net update errors
     ((is_pub_scs_song_bool && has_fully_converted_pub_scs(s.id)) || !is_pub_scs_song_bool)
    return true
  end
  false  # ← every song that fails returns false (silently skipped)
end
```

**CIS-Net sync status** (`tbliswcsync` in postgres02):
| Status | Count | Passes? |
|--------|-------|---------|
| SENT | 143,611 | ✅ |
| REJECTED | 226,725 | ❌ |
| UPDATED | 60,626 | ❌ |

Songs with REJECTED or UPDATED status are silently skipped by the legacy engine.

## Multi-Database Architecture

The app uses **two Postgres instances** — queries must target the right one:

| Database | Container | Tables | Purpose |
|----------|-----------|--------|---------|
| `mwi_development` (or `mwi`) | `mweb-postgres01-1` | `songs`, `societies`, `song_creator_shares`, `publishers`, `cwr_export_song_records` | Rails app data |
| `mwi` (CIS-Net) | `mwi-postgres02-1` | `tbliswcsync`, `tblworkinfo`, `tblshare`, ... | CIS-Net legacy DB |

**Enum integer mappings needed for SQL queries:**
```ruby
# SongCreatorShare rights_type
perf: 0, mech: 1, broad: 2, webcast: 3, digital: 4, no_rights: 99

# Society agreement_type (integer, not string in DB)
0 = none, 1 = reciprocal, 2 = unilateral_outbound, 4 = ??
```

## Diagnostic Checklist

### Foundation checks (same DB)
```sql
-- Songs with ISWCs (passes job filter)
SELECT count(*) FROM songs WHERE is_intl = false AND iswc IS NOT NULL AND iswc != '';

-- Songs missing ISWCs
SELECT count(*) FROM songs WHERE is_intl = false AND (iswc IS NULL OR iswc = '');

-- Societies with outbound agreements
SELECT soc_code, name FROM societies WHERE agreement_type IN (1, 2) ORDER BY name;

-- CwrExportSongRecord coverage
SELECT soc_code, count(*) FROM cwr_export_song_records GROUP BY soc_code ORDER BY soc_code;
```

### Validation depth check
```sql
-- Songs passing BatchExporter validation (ISWC + perf share + publisher soc + writer)
SELECT count(*) FROM songs s
WHERE s.is_intl = false AND s.iswc IS NOT NULL AND s.iswc != ''
AND EXISTS (
  SELECT 1 FROM song_creator_shares scs
  JOIN publishers p ON p.id = scs.publisher_id
  WHERE scs.song_id = s.id AND scs.rights_type = 0  -- perf
  AND p.soc_code IS NOT NULL AND p.soc_code != 0
  AND scs.member_id IS NOT NULL AND scs.member_id != 99
);
```

### CIS-Net sync check (separate DB)
```sql
-- CIS-Net sync status distribution
SELECT status, count(*) FROM tbliswcsync GROUP BY status ORDER BY status;
```

### Running via `docker exec`
```bash
# Rails DB
docker exec mweb-postgres01-1 psql -U mwi -d mwi -c "SELECT count(*) FROM songs ..."
# CIS-Net DB
docker exec mwi-postgres02-1 psql -U mwi -d mwi -c "SELECT status, count(*) FROM tbliswcsync GROUP BY status;"
```

### Sidekiq job log
Check Rails log for `[BatchExporter]` lines:
```bash
docker logs mweb-worker-1 2>&1 | grep '\[BatchExporter\]' | tail -50
```
Look for:
- `DiffQuery: N new, M changed, ...` — is the song count right?
- `SCAN COMPLETE: X scanned, Y valid` — what validation pass rate?
- `SKIP SUMMARY` — what skip reasons dominate?

## Reference File

See `references/2026-07-13-diagnostics.md` for the exact queries, container identities, and key counts from the 2026-07-13 diagnostic session.

## Critical: CIS-Net Validator Gate Blocks Both Engines

The `@validator` injection in `Cwr::ExportEngine#export_service` (export_engine.rb:46) is the **most common cause of zero-song output**:

```ruby
validator = method(:validated_cisnet_song) if respond_to?(:validated_cisnet_song)
```

Since `ExportCwrWorkerJob` includes `SongsHelper`, the validator is **always injected**, regardless of which engine is selected. In `BatchExporter#validate_song` (line 341-349):

```ruby
if errs.empty? && @validator
  result = @validator.call(song.id)
  if result == false
    errs << 'CIS-Net validation failed'    # ← song exists, but checks fail
  elsif result.nil?
    errs << 'song not found in CIS-Net'    # ← song not in CIS-Net at all
  end
end
```

### The `validated_cisnet_song` Chain (songs_helper.rb:6061)

```ruby
def validated_cisnet_song(id_or_code)
  s = Song.find_by(id: id_or_code)
  return nil unless s.present?
  if in_cisnet(s.id) &&                                      # SOAP call to data broker
     MwiIswcSync.search(s.code).first&.status == 'SENT' &&   # tbliswcsync status check
     run_checks_for_cisnet_update(s.id, ...).blank? &&        # ~200-line multi-check method
     ((is_pub_scs_song_bool && has_fully_converted_pub_scs(s.id)) || !is_pub_scs_song_bool)
    return true
  end
  false  # ← silently blocks the song
end
```

Four conditions, all must pass:
1. `in_cisnet` — SOAP call to CIS-Net data broker (tomcat). If down, returns nil.
2. `MwiIswcSync` status === 'SENT' — song's ISWC must have been accepted.
3. `run_checks_for_cisnet_update` — ~15 sequential checks (shares, IPNs, names, share structure). Any failure blocks.
4. pub_scs conversion — only applies if `is_pub_scs_song?` is true (shares have parent/child/zero_child types). Most songs are normal shares, so this passes via `!is_pub_scs_song_bool`.

### Testing a Specific Song

For songs that have `tbliswcsync.status = 'SENT'` and pass checks 1, 2, and 4, the blocker is **always `run_checks_for_cisnet_update`**. To pinpoint which check fails, you'd need to run it in the Rails console context (all helpers included):

```ruby
include SongsHelper
include SongCreatorSharesHelper
# ... all helpers that ExportCwrWorkerJob includes
run_checks_for_cisnet_update(song.id, {break_on_first_error: true})
```

If `rails runner` is broken due to Docker network conflicts (container sees the wrong postgres01), debug by running SQL queries directly against both databases to manually verify each check condition.

## Pool-Size Logic (Fix: item_end / valid_song_max)

The `ExportCwrWorkerJob` has a pool-sizing section (lines 73-85) that can silently limit exports:

**OLD behavior (bug):** When `valid_song_max` was unset (0) but `item_end` was set, the code promoted `item_end` to `valid_song_max`, creating an unintended hard cap. Setting `item_end=40000` in the UI would limit the export to 40K validated songs.

**FIX:** `item_end` now stays as pool size only; `valid_song_max` stays 0 (unset) → BatchExporter clamps to `@stats[:total]`, exporting everything in the pool.

```
# Current correct behavior:
item_end = pool size (how many songs to scan)
valid_song_max = export target (max validated songs to find) — 0 = use full pool

# Only expand pool when valid_song_max was explicitly set (>0)
if valid_song_max > 0 && valid_song_max >= item_end
  item_end = (valid_song_max + item_start) * CWR_VALID_SONG_MAX_MULTIPLIER
end
```

**Diagnostic:** Check seq counters to see how many batches were allocated:
```bash
docker exec mweb-web-1 bundle exec rails runner "
CwrExportSeqCounter.unscoped.where(year: 2026).find_each { |c| puts \"soc #{c.soc_code}: next_seq=#{c.next_seq} (allocated #{c.next_seq - 1})\" }
"
```
Fewer batches than expected with low `next_seq` values suggests the pool-size limit was hit.

## Reading BatchExporter Logs

The `[BatchExporter]` prefix marks all log lines. Key lines to watch:

```
DiffQuery: 132325 new, 0 changed, 0 exc, 0 unchanged skipped
 → Total songs in the diff. force_full_resend=true → all are "new".

SCAN COMPLETE: 132325 scanned, 36338 valid (27.5%), 85987 skipped
 → Validation pass rate. 27% is typical when many songs lack publisher/writer data.

FINAL SKIP SUMMARY (85987 total): CIS-Net validation failed: 12819, ...
 → The cumulative skip reasons. Top categories with counts.

V023 summary: 5585 songs with arranger on ORI (e.g. M0003759455 (WINTERSWEET))
 → Single summary line (not per-song) — informational only.

BatchExporter DONE — Exported: 36338, skipped: 85987, diff: 132325 new/...
 → Final result summary.
```

## Error Files

Three types of error files are produced:

| File | Pattern | import_type | How uploaded |
|------|---------|-------------|--------------|
| Line-level error | `CW*.V21_ERROR` | `export_cwr_error` | Individually via upload_to_blob_storage |
| Validation error | `CW*_VALIDATION_ERROR.txt` | `export_cwr_error` | Individually via upload_to_blob_storage |
| Society zip | `CW*.zip` | `export_cwr` | Uploaded as zip, individual .V21 files deleted after zipping |

**UI visibility:** The export_cwr page filters by `import_type`. Error files use `'export_cwr_error'` while zips use `'export_cwr'`. Both must be in the query for error files to appear in the download list.

**`build_return_hash` bug (fixed):** The `error_files` key was only returning line-level `_ERROR` files from `@error_lines`, omitting `_VALIDATION_ERROR.txt` files. Fix: also collect from `@files_created` matching `/_VALIDATION_ERROR/i`.

## Per-Batch Audit Logging

Each batch writes an audit entry (`User.find(1).audits.create`) with:
```
action: 'CWR_BATCH'
comment: "CWR batch N: M songs; CIS-Net validation failed: X songs (e.g. CODE); ..."
```

Uses `@last_audited_skip_count` tracker to only process NEW errors since last audit (O(n) per batch, not O(n²)).

## CIS Character Validation for Korean Works

Per CWR 2.1 spec, these record types carry native/Korean text and are excluded from ASCII validation:
- NPN (§5.6) — Native Publisher Name
- NWN (§5.10) — Native Writer Name
- NAT (§5.14) — Native Alternate Title
- NPR (§5.17) — Native Performer Name (WAS MISSING, added)

Defined as `NON_ROMAN_RECORDS` and now explicitly wired into `validate_cis_characters` with an early `next if` skip.

**NWR Work Title** is NOT a Korean-text field per spec — Korean titles should use NAT records. If Korean text appears in NWR Work Title, that's a data quality issue to fix at the source (create NAT record), not in the CWR export.

**Lowercase/control char checks** are genuine errors regardless of language — these are never valid in any CWR field.

## ActiveStorage Download Issues

The download link uses `import_file.url` which generates a URL through `ActiveStorage::Blobs::ProxyController`. The signed_id is a Rails `MessageVerifier` token containing the blob ID.

**Common issues:**
- **Safari "network connection lost"**: Often a timeout when downloading large files through the proxy. Fix: increase nginx `send_timeout` (default 30s) or switch to `rails_storage_redirect`.
- **404 on zip files**: Signed_id must be the FULL value (98 chars for this project). Hermes terminal output truncates with `...` — always verify with base64-encode/decode or write to file.
- **No `.txt` vs `.zip` difference**: Both go through the same controller. If `.txt` works but `.zip` doesn't, check for nginx rules or browser-specific behavior.

```bash
# Get full signed_id without truncation
docker exec mweb-web-1 bundle exec rails runner "
puts Base64.strict_encode64(ActiveStorage::Blob.find(2369).signed_id)
"
# Then on host: echo '<base64>' | base64 -d
```

## Diagnostic Queries for Validation Pass Rate

```sql
-- Songs passing ALL three BatchExporter checks (ISWC + writer + publisher)
SELECT count(*) FROM songs s
WHERE s.is_intl = false AND s.iswc IS NOT NULL AND s.iswc != ''
AND EXISTS (SELECT 1 FROM song_creator_shares scs WHERE scs.song_id = s.id)  -- has shares
AND EXISTS (SELECT 1 FROM song_creator_shares scs
            JOIN publishers p ON p.id = scs.publisher_id
            WHERE scs.song_id = s.id AND scs.rights_type = 0
            AND p.soc_code IS NOT NULL AND p.soc_code != 0)  -- publisher with soc
AND EXISTS (SELECT 1 FROM song_creator_shares scs
            WHERE scs.song_id = s.id AND scs.rights_type = 0
            AND scs.member_id IS NOT NULL AND scs.member_id != 99);  -- writer member
```

## Pitfalls: The `mweb-` prefix containers (running 10+ hours) have the real data. Fresh `docker compose up` creates new `koscap-mwi-` containers with empty databases.
- **`docker exec rails runner`** may fail if `mwi_development` database doesn't exist on the postgres01 container — the web container's config expects `mwi_development` but the Docker setup may use `mwi`.
- **Sidekiq runs async** — the job doesn't block. Zero output can mean the job is still running, has crashed, or completed with zero songs. Check Sidekiq dashboard (`/sidekiq`) or worker logs.
- **Default export engine mismatch**: UI defaults to `'service'` but controller defaults to `:legacy` if param is absent. If the form is ever rendered without the engine dropdown, the export silently switches engines.
- **`validated_cisnet_song` vs `validate_song` confusion**: The BatchExporter has its own `validate_song` (ISWC format, shares, publisher soc, writer member) which runs FIRST. Then the injected `@validator` (validated_cisnet_song) runs AFTER on songs that passed local validation. A song can pass `validate_song` but still be blocked by `validated_cisnet_song`.
- **`run_checks_for_cisnet_update` is opaque**: A ~200-line method (songs_helper.rb:1903) with ~15 sequential checks, many querying both the Rails DB and the CIS-Net SOAP API. With `break_on_first_error: true`, it stops at the first failure and returns an error string. The error message format is `"N. check_description"`.
