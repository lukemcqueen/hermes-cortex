---
language: markdown
tags: [documentation, changelog, versioning, semver]
title: Changelog Template (Keep a Changelog)
description: Keep a Changelog format with semver, categorized changes (Added/Changed/Deprecated/Removed/Fixed/Security), and an Unreleased section
source: pattern
---

# Changelog Template

This follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The `Unreleased` section is always present at the top. When releasing, rename it to the version number and create a fresh `Unreleased` section.

## Change Categories

| Category      | Description                                        |
|---------------|----------------------------------------------------|
| **Added**     | New features, endpoints, modules                   |
| **Changed**   | Changes to existing functionality or behaviour     |
| **Deprecated**| Features marked for removal in a future release    |
| **Removed**   | Features removed in this release                   |
| **Fixed**     | Bug fixes                                          |
| **Security**  | Vulnerability fixes, dependency upgrades for CVEs  |

---

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- JSON export endpoint `GET /api/v1/export` with streaming support (#142)
- New `--format` CLI flag for output in CSV, JSON, or YAML
- Rate-limit headers (`X-RateLimit-Remaining`, `X-RateLimit-Reset`) on all API responses

### Changed
- Upgraded base image from Debian Bullseye to Bookworm
- Pagination default changed from 10 to 25 items per page
- Logger now uses structured JSON output instead of plain text

### Fixed
- `POST /api/v1/users` returning 500 on duplicate email (#138)
- Memory leak in the WebSocket reconnection handler
- Incorrect file permissions on Unix socket creation

### Security
- Updated `cryptography` dependency to 42.0.0 (CVE-2024-XXXX)
- Removed server version from error response bodies

## [1.2.0] — 2026-06-15

### Added
- Support for WebSocket connections (`/ws`)
- Health-check endpoint at `GET /health`
- Graceful shutdown with SIGTERM handling

### Changed
- Minimum Python version raised from 3.9 to 3.10
- Configuration file format migrated from INI to TOML

### Deprecated
- The legacy sync client (`/v1/legacy` endpoint) — will be removed in 2.0.0

### Fixed
- Off-by-one error in pagination when `page=1` returned wrong offset (#127)

## [1.1.0] — 2026-04-01

### Added
- User avatar upload support
- Rate limiting with configurable thresholds

### Changed
- Database migration to use `TIMESTAMPTZ` instead of `TIMESTAMP`

### Fixed
- Crash on empty request body in `POST /api/v1/items`

## [1.0.0] — 2026-01-10

### Added
- Initial public release
- User CRUD API (`/api/v1/users`)
- Authentication with JWT tokens
- PostgreSQL-backed storage
- CLI tool for batch operations
```

```markdown
<!-- Template footer — copy this for each version block -->
## [MAJOR.MINOR.PATCH] — YYYY-MM-DD

### Added
### Changed
### Deprecated
### Removed
### Fixed
### Security
```
```

## Best Practices

- **Always keep an `[Unreleased]` section** — it accumulates changes until the next release
- **Date every release** in ISO 8601 format (`YYYY-MM-DD`)
- **One category per change** — don't list a fix as "Added"
- **Reference issues/PRs** with `(#123)` at the end of each entry
- **Describe the change, not the problem** — "Added export endpoint" not "Users couldn't export data"
- **Link to commits or diffs** for significant changes (optional but helpful)