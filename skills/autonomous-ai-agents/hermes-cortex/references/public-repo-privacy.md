# Public Repo Domain Privacy Pattern

**Date:** 2026-06-04
**Issue:** Personal domain names (`example.com`) were hardcoded in public repo files, exposing personal infrastructure details.

## Pattern

**Use `example.com` as a placeholder** in all public repo files:
- Docker Compose comments
- nginx configs
- HTML/JavaScript links
- Test assertions
- Documentation

**Files to check:**
```bash
# Search for personal domains
grep -r "your-domain\.com\|personal-domain\." .

# Common locations:
# - docker-compose.*.yml (comments)
# - nginx/*.conf (server_name, ssl_certificate paths)
# - dashboard/static/*.html (links)
# - scripts/test-*.py (test assertions)
# - install.sh (info messages)
```

## Replacement Workflow

### 1. Find all occurrences
```bash
grep -rn "personal-domain\.com" .
```

### 2. Replace in working tree
Use `patch` tool or `sed`:
```bash
# sed approach (macOS requires -i '')
sed -i '' 's/personal-domain\.com/example.com/g' file1 file2 ...

# Or use patch tool for targeted replacements
```

### 3. Rewrite git history
Use `git-filter-repo` to remove from ALL commits:

```bash
# Install
pip3 install git-filter-repo

# Create replacement file
echo "personal-domain.com==>example.com" > .git-filter-repo-replacements.txt

# Rewrite history (FORCE required after initial clone)
git filter-repo --replace-text .git-filter-repo-replacements.txt --force

# Verify no occurrences remain
grep -rn "personal-domain\.com" .  # Should return nothing

# Re-add remote (git-filter-repo removes it)
git remote add origin https://github.com/user/repo.git

# Force push (rewrites public history)
git push --force origin main
```

**WARNING:** Force pushing rewrites public history. Anyone who cloned the repo will need to re-clone or run:
```bash
git fetch --all
git reset --hard origin/main
```

## Files Updated in hermes-cortex

| File | Occurrences |
|------|-------------|
| `docker-compose.langfuse.yml` | 1 (comment) |
| `nginx/hermes-services.conf` | 5 (server_name, ssl paths) |
| `install.sh` | 1 (info message) |
| `dashboard/static/index.html` | 2 (links) |
| `scripts/test-dashboard.py` | 1 (test assertion) |

**Total:** 10 occurrences replaced

## Post-Cleanup Verification

```bash
# Verify no personal domains remain
grep -rn "fleet-operator\.com" .  # Should return 0 results

# Verify example.com is used instead
grep -rn "example\.com" .  # Should show all replacements

# Check git history is clean
git log --all -p | grep "fleet-operator\.com"  # Should return nothing
```

## Alternative: Skip History Rewrite

If the repo is new and history rewrite is too disruptive:

1. Replace in working tree only
2. Commit with message: `chore: replace personal-domain.com with example.com`
3. Document in README that old commits contain personal domain (will be overwritten on next clone)

**Trade-off:** Old commits still contain personal domain, but current state is clean. Less disruptive for existing contributors.

## Related Patterns

- **Secrets management:** Never commit real API keys, passwords, or credentials to public repos. Use `.env.example` with placeholder values.
- **Two-repo architecture:** Keep personal config in private repo (`hermes-cortex-private`), public installer in public repo (`hermes-cortex`).
- **SSL cert paths:** Use placeholder paths in public configs (`/usr/local/etc/nginx/ssl/example.com/`), real paths in private repo.
