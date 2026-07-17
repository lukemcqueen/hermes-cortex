--- Full content (truncated) ---
---
name: cwr-file-processing
description: >-
  CISAC CWR (Common Works Registration) file processing for music copyright
  societies. Covers export generation (Rails + Python), ACK response handling,
  validation (structural + custom rules + field-level), share calculations,
  pub_share conversion, and ACK file analysis. Dual-stack: koscap-mwi
  (Rails/PostgreSQL) and koscap-works (Python/FastAPI/Next.js).
trigger: >-
  When the task involves CWR export, CWR import, ACK file analysis,
  share validation, pub_share conversion, or CWR format validation.
  Load this skill before editing any CWR-related code in either
  koscap-mwi (Rails) or koscap-works (Python) projects.
domain: music copyright, CISAC CWR 2.1, collective rights management
---

# CWR File Processing

## Key Architecture

### Legacy Export (14K-line helper, still available)
- **Export**: `app/helpers/cwr_helper.rb` — `export_cwr()` generates CWR files with batch/file/upload logic
- **Validation**: `verify_cwr_file()` in t
... [truncated]
--- End skill ---