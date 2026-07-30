--- Full content (truncated) ---
---
name: cwr-export-debug
version: 1.0.0
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
- But the **UI dropdown*
... [truncated]
--- End skill ---