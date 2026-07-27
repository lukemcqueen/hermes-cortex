# Session: Hardcoded Paths in hermes-cortex

Date: 2026-06-22
Scope: `~/hermes-cortex` repo — 27 files patched

## Scan Patterns Used

```bash
# All patterns run in parallel in one turn:
grep -rn '/home/moses' .
grep -rn '/home/luke' .
grep -rn '~/hermes-cortex' .
grep -rn '~/hermes-cortex-private' .
grep -rn '/home/' .
grep -rn '/usr/local/etc/nginx' .
grep -rn '/usr/local/bin/docker' .
grep -rn '/opt/homebrew' .
grep -rn '/opt/' .
grep -rn '/root/' .
grep -rn '/usr/' .
```

## Files Fixed

### Critical — Scripts (3 files)

| File | Old Pattern | New Pattern |
|------|-----------|-------------|
| `deploy/nginx/hermes-security-apply` | `CORTEX_REPO="${HOME}/hermes-cortex"` + macOS-only nginx paths | `SCRIPT_DIR` derivation + `case $(uname -s)` OS dispatch |
| `deploy/nginx/nginx/hermes-security-apply` | `SRC="~/hermes-cortex/..."` | `SCRIPT_DIR` + `$SRC` from `$SCRIPT_DIR/..` |
| `src/dashboard/server.py` | `docker_bin = "/usr/local/bin/docker"` (×2) | `_docker_bin()` via `shutil.which("docker")` |

### Documentation & Skills (16 files, ~25 patches)

| Area | Pattern replaced | Pattern used |
|------|----------------|-------------|
| SKILL.md files | `~/hermes-cortex` | `${CORTEX_REPO:-$HOME/hermes-cortex}` |
| SKILL.md files | `~/hermes-cortex-private` | `${CORTEX_REPO:-$HOME/hermes-cortex}-private` |
| README/docs | Bare path examples | `${CORTEX_REPO:-$HOME/hermes-cortex}` |
| SECURITY.md | `/usr/local/etc/nginx/.htpasswd` | `${NGINX_HTPASSWD:-...}` with OS note |
| generate-inbox-wrappers.py help | `/usr/local/etc/nginx/.htpasswd` | `${NGINX_HTPASSWD:-...}` |

## Key Tool Patterns

### patch — items to get right

- **Escape-drift:** When the old_string in patch contains escaped quotes
  (`\"`) but the file doesn't, the patch fails with "escape-drift detected."
  Always read the exact line from `read_file` first and copy verbatim.
- **Read before edit:** Always `read_file` the section before calling `patch`
  to get exact whitespace and quote characters.
- **replace_all=true** for duplicating same old_string across multiple
  locations (e.g. the two hardcoded `logpath = /usr/local/var/log/nginx`
  in the fail2ban jail templates).

### search_files — scope filtering

- Use `target='content'` (default) + `file_glob='*'` to search inside files.
  The `matches_format: "path-grouped"` output shows each file with
  its line-specific matches.
- Use `target='files'` with `pattern='<glob>'` to discover files first.

## Exclusions (correctly skipped)

- Dockerfile `target=/root/.local/share/pnpm` — container-internal paths
- Shebangs `#!/usr/bin/env bash` — standard and portable
- `/etc/letsencrypt/live`, `/etc/ssl/certs` — standard OS paths
- `.plist` files — macOS launchd system files
- Offline code corpus snippets — reference examples, not functional code
- `/opt/homebrew/...` in nginx config comments — documenting the deployment
  substitution, not hardcoded logic