# Hermes Cortex — Improvement Patches

This directory contains patches and additions that address audit findings.
Each patch targets a specific file and can be applied independently.

## Patch Index

| # | Patch | Fixes | Severity |
|---|-------|-------|----------|
| 1 | `fix-sync-daemon--all.patch.md` | gbrain sync daemon uses `--all` which silently fails on the built-in `default` source | P0 |
| 2 | `fix-heartbeat-divergence.patch.md` | heartbeat.py in install.sh embedded version is outdated vs repo version (missing memory sync check) | P1 |
| 3 | `fix-memory-to-brain-divergence.patch.md` | memory-to-brain.py in install.sh embedded version outdated vs repo version | P1 |
| 4 | `fix-nginx-log-path.patch.md` | nginx config hardcodes `/usr/local/var/log/nginx/` — fails on Apple Silicon | P2 |
| 5 | `fix-auto-update-path.patch.md` | auto-update.sh hardcodes `~/hermes-cortex/` path | P2 |
| 6 | `fix-langfuse-port-docs.patch.md` | Skill docs reference port 3001, actual port is 3000 | P2 |
| 7 | `fix-code-corpus-stats.patch.md` | Skill says "29 snippets across 6 languages" — actual: 800+ files across 20+ languages | P2 |
| 8 | `add-offline-code-prep-to-installer.patch.md` | Installer never runs prep-code.sh — offline code index is never built | P2 |

## New Files

| File | Purpose |
|------|---------|
| `scripts/seed-project-brain.sh` | Post-install tool: seed a project's brain dir from its repo docs |
| `installer-integration.md` | How to integrate the new fixes into install.sh |

## Applying

```bash
# Apply a single patch
cd ~/hermes-cortex
cat patches/fix-sync-daemon--all.patch.md

# Each patch includes exact before/after blocks for patch tool
```

## How to verify each fix

See `scripts/cortex-audit.sh` (created by fix 9 in the installer integration doc)
for a comprehensive health check that catches all these issues.
