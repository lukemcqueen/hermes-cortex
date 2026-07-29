---
name: pii-scrubbing
category: security
description: >-
  Systematically scrub Personally Identifiable Information (PII) from a
  codebase — inventory real domains, hostnames, credentials, and email
  addresses across all files; patch them to placeholders; create .example
  templates for gitignored configs; rewrite git history to remove PII from
  past commits; and verify the result is clean.
tags:
  - pii
  - security
  - git-filter-repo
  - history-rewrite
  - credentials
  - secrets
---

# PII Scrubbing — Systematic Codebase Cleanup

## Trigger

Use this skill when:
- Asked to "remove PII from the repo" or "scrub real URLs/hostnames/credentials"
- Preparing a repo for open-source publication
- A security review finds real domains, passwords, or emails in code/docs
- Asked to create `.example` templates for config files with secrets
- Asked to remove PII from git history

## Workflow

### Phase 1: Inventory

Search the repo systematically for PII patterns. Run ALL of these searches:

| Pattern | What it catches |
|---------|-----------------|
| `grep -r 'realdomain.com' .` | Real infrastructure domains |
| `grep -r 'customer-host.com' .` | Real server hostnames |
| `grep -r 'user:pass@' .` | Credentials embedded in URLs |
| `grep -rE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' .` | Email addresses |
| `grep -r 'sk-[a-zA-Z0-9]{20,}' .` | API keys |
| `grep -rE '\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b' .` | IP addresses (check each — 127.x.x.x is safe) |
| `grep -r 'password|secret|key|token|cred' -i` | Credential references |
| `grep -rE ':1[0-9]{4}[0-9]*' .` | Port numbers (check if they're custom infrastructure) |
| `find . -name '*cred*' -o -name '*secret*' -o -name '*token*' -o -name '*.pwd' 2>/dev/null` | Credential files in working tree |

**Gitignore audit for credential files:** Every credential file found in the working tree must be gitignored. For each one:

```bash
git check-ignore <filename>
# Returns the path if gitignored (safe), nothing if NOT gitignored (CRITICAL)
```

Also verify the `.gitignore` patterns that catch them. Common patterns: `*cred*`, `*secret*`, `*token*`, `*.pem`, `*.key`. Run `grep -n 'cred\|secret\|token\|pem\|key' .gitignore` to confirm coverage. If a credential file isn't covered by any existing pattern, add one.

**PII categories to flag** (any one of these is actionable):

| Category | Examples | Treatment |
|----------|----------|-----------|
| Infrastructure domain | `bus.example.org`, `customer-app.com` | Replace with `your-domain.com` |
| Production hostname | `mweb-stage.customer.or.kr`, `api.customer.org` | Replace with `your-customer-host.com` |
| Agent hostname | `gisu-host`, `joseph-host` | Replace with `your-agent-host` |
| Real credentials | `user:pass`, `sk-abc...`, `T1tus!nbox_2026` | Replace with `your-credential-placeholder` |
| Real email addresses | `admin@customer.org`, `audit@customer.org` | Replace with `admin@client-domain.com` |
| Real file paths with user | `/home/luke`, `/Users/luke` | Replace with `/path/to/app` or `$HOME` |
| Client project names | `koscap-royalty`, `client-app` | Evaluate: is this identifying? If yes, use `client-project` |
| Company/organization names | `KOSCAP`, `AcmeCorp` | Replace with `ExampleCorp` or generic `ClientName` |
| Real person names in paths | `joseph/`, `luke/` | Rename to generic descriptor (`operator/`, `user/`). Scan directory listing, not just file contents |
| Real person names in content | `Luke`, `Joseph` (not biblical/historical figures) | Replace with `the user`, `the operator`, or a role descriptor |
| Multiple TLD variants (same base domain) | `client.org`, `client.or.kr`, `client.com` | Search for the base word across all TLDs, not just the one you found first |
| API endpoint URLs | `https://works.customer.org/api/...` | Replace with `https://api.client-domain.com/...` |

### Phase 2: Patch Working Tree

For each file with PII, determine the right treatment:

**A) Scripts with hardcoded default URLs:**
```python
# Before
URL = os.environ.get("SOME_VAR", "https://realdomain.com:13004")

# After
URL = os.environ.get("SOME_VAR", "https://your-domain.com:13004")
```
Pattern: change the fallback default to `your-domain.com`. The env var override still works for actual deployments.

**B) Config templates:**
```ini
# Before
MOSES_INBOX_URL="https://realdomain.com:13004"

# After
MOSES_INBOX_URL="${DOMAIN_URL:-https://your-domain.com:13004}"
```
Or replace directly with placebo values and document that the user must set their actual values.

**C) Example curl commands in docs/code:**
```
# Before
curl https://realdomain.com:13004/api/send

# After
curl https://your-domain.com:13004/api/send
```

**D) Credentials in example code:**
```
# Before
curl -sk -u "user:password123"

# After
curl -sk -u "user:your-password"
```

**E) Email addresses in skill references:**
```
# Before
admin@koscap.or.kr

# After
admin@client-domain.com
```

### Phase 3: Create .example Templates for Gitignored Files

For any config file that contains real secrets and is gitignored:

1. Create `filename.example` with placeholder values
2. Ensure the real file is in `.gitignore`
3. Add `!*.example` exception to `.gitignore` if `.example` extension is generally gitignored
4. Commit both the `.gitignore` fix and the `.example` file

### Phase 3b: Template + Setup Script Pattern (for programmatic configs)

For JSON configs or structured data that need programmatic generation (not manual editing), use a three-file pattern instead of `.example`:

| File | Location | Purpose |
|------|----------|---------|
| **Template** | `src/name.template.json` (repo) | Placeholder values like `{{CORTEX_DOMAIN}}` |
| **Setup script** | `ops/scripts/setup-name.sh` (repo) | Reads env vars or prompts, substitutes placeholders, writes real file outside repo |
| **Real config** | `~/.hermes/state/name.json` (outside repo) | Actual URLs/credentials, never committed |
| **Consumer code** | Python/sh scripts | Reads private path first, falls back to template if not found |

**Structure in the repo:**
```
Repo (public):
  src/agent-registry.template.json           ← {{PLACEHOLDER}} values only
  ops/scripts/setup-agent-registry.sh         ← creates real file at ~/.hermes/state/

Filesystem (gitignored / outside repo):
  ~/.hermes/state/agent-registry.json        ← real URLs, NEVER committed

Consumer code pattern:
  # 1. Check ~/.hermes/state/ first
  # 2. Fall back to src/*.template.json if not found
  # 3. This lets new installs run with defaults, production uses real config
```

**When to use this pattern:**
- Config file is JSON or other structured format (not plain key=value)
- Values need validation beyond "is it non-empty"
- Multiple URL/credential pairs need filling (e.g. agent registry with 5+ agents)
- Same setup process runs on multiple machines

**When to use `.example` pattern instead:**
- Simple key=value configs (`.env`, `.ini`)
- Files the user will manually edit once
- Self-explanatory values that don't need validation

**Proven in Hermes Cortex:**
- `models.env` — env vars with `CORTEX_DOMAIN` override
- `hermes-inbox.conf` — created by setup with `CORTEX_INBOX_*` vars
- `agent-registry.json` — multi-agent registry created by `setup-agent-registry.sh`

**Non-interactive deployment:**
```bash
# Set env vars, then run the script — no prompts
CORTEX_DOMAIN=myhost.com CORTEX_HEALTH_PORT=13007 \
  ESTHER_DOMAIN=otherhost.com ESTHER_HEALTH_PORT=13007 \
  bash ops/scripts/setup-agent-registry.sh
```

**For `.env` files specifically:**
- Audit `docker-compose*.yml` for all `${VAR:?...}` and `${VAR:-...}` references
- Collect required and optional variables
- Create `deploy/.env.example` with:
  - Comment header explaining purpose and where to put the file
  - Quick-seed commands (e.g., `openssl rand -hex 32` for generating secrets) — embed these in the example so users can copy-paste them
  - Required vars listed first with empty values (the user MUST fill these)
  - Optional vars commented out with defaults documented
  - Hermes integration vars as a separate commented section if they go in a different file (`~/.hermes/.env`)
- Ensure `!.env.example` exception is in `.gitignore` AFTER `.env.*`:
  ```gitignore
  .env
  .env.local
  .env.*
  !.env.example  # ← the negation must come AFTER .env.*
  ```
- See: `deploy/.env.example` in hermes-cortex for a worked example

**For service-specific config files** (e.g., `ops/scripts/inbox.conf.example`):
- Follow the same pattern: real values → placeholders, document what the user should replace

### Phase 4: Rewrite Git History

Use `git-filter-repo` to scrub PII from ALL past commits:

1. **Install git-filter-repo** (if needed):
   ```bash
   pip3 install git-filter-repo
   ```

2. **Create replacements file** (`/tmp/pii-replacements.txt`):
   ```
   literal:realdomain.org==>your-domain.com
   literal:realdomain.com==>your-domain.com
   literal:customer.host.name==>your-customer-host
   literal:RealPassword123!==>your-password-placeholder
   ```

3. **Clone to a temp directory** (run filter-repo on a clone, not the working repo):
   ```bash
   cd /tmp
   rm -rf repo-clean 2>/dev/null
   git clone /path/to/working-repo repo-clean
   cd repo-clean
   ```

4. **Run filter-repo**:
   ```bash
   git-filter-repo --replace-text /tmp/pii-replacements.txt --force
   ```

5. **Verify** — search for every pattern:
   ```bash
   git grep -i "realdomain\|password123\|other-pattern" .
   # Should return EXIT 1 (no matches)
   ```

6. **Handle branch protection** (GitHub):
   - If `main` is protected: push to `main-sanitized` first, then ask the user to temporarily disable branch protection
   - Then force-push the cleaned history:
     ```bash
     git remote add origin https://github.com/user/repo.git
     git push --force --all origin
     ```

### Phase 4b: Cover Commit Messages (Separate Pass)

⚠️ **`--replace-text` only covers file contents and filenames — it does NOT touch commit messages.** Commit messages need a dedicated `--replace-message` pass.

After `--replace-text` completes, run a second filter-repo pass with the same replacements file:

```bash
cd /tmp/repo-clean
git filter-repo --force --refs HEAD --replace-message /tmp/pii-replacements.txt
```

This rewrites the history again, applying the same literal replacements to commit subjects and bodies. Without this, commit messages like `fix: add Gisu to mirror chain for KOSCAP images` still leak the real project name.

**When to use:** Always. Unless you've verified there's no PII in any commit message (via `git log --oneline --grep`), assume there is.

### Phase 4c: File Renaming via `--filename-callback`

When obfuscating a project name that appears in filenames (e.g. `koscap-development-patterns.md` → `acme-development-patterns.md`), use `--filename-callback`.

The callback receives **bytes**, not str — decode/encode accordingly:

```bash
git filter-repo --force --refs HEAD \
  --replace-text /tmp/replacements.txt \
  --filename-callback 'return filename.replace(b"koscap", b"acme").replace(b"KOSCAP", b"ACME").replace(b"Koscap", b"Acme")'
```

After renaming, update the replacement rules file to include the case variants:

```
KOSCAP==>ACME
Koscap==>Acme
koscap==>acme
```

### Phase 4d: Case Variants

A project name can appear in three case forms:
- **UPPERCASE**: `KOSCAP` — in titles, headings, CISAC codes
- **Titlecase**: `Koscap` — in running text ("Koscap-royalty monorepo")
- **lowercase**: `koscap` — in URLs, paths, repo names (`koscap-works`, `koscap-royalty`)

`--replace-text` does **case-sensitive exact match** — `koscap==>acme` will NOT match `KOSCAP` or `Koscap`. Add ALL variants to the replacements file:

```
KOSCAP==>ACME
Koscap==>Acme
koscap==>acme
```

Same for `--filename-callback` — each variant needs its own `.replace()` call.

### Phase 5: Verify — Check Both Content AND Commit Messages

Comprehensive check after all changes:

| Check | How | Expected |
|-------|-----|----------|
| No PII in file contents | `git grep -i "realdomain\|original-pattern" .` | Exit 1 (no matches) |
| No PII in filenames | `find . -iname "*oldproject*"` | Empty |
| No PII in commit messages | `git log HEAD --oneline --grep="oldproject\|other-pattern"` | Empty |
| No PII in past commits | `git-filter-repo` output shows 0 matches | Clean run |
| Real configs gitignored | `git check-ignore path/to/config.json` | Exit 0 (ignored) |
| Example templates tracked | `git ls-files` includes `.example` files | Listed |

**Verification gotcha:** After cloning from a local repo that's already been rewritten, `git log --all --grep=` shows false positives from `refs/remotes/origin/main` (the stale remote tracking ref). Always verify against `HEAD` explicitly: `git log HEAD --oneline --grep=...` — not `--all`.

## Ordering Rules in Replacements File

Place more specific patterns FIRST in the replacements file, more general patterns LAST. Filter-repo applies rules sequentially — a vague match can consume a URL before the specific domain rule fires.

**Wrong ordering:**
```
koscap==>acme                              # ← fires first on "koscap.or.kr" → "acme.or.kr" ❌
koscap.or.kr==>client-domain.com           # ← never reached
```

**Correct ordering:**
```
koscap.or.kr==>client-domain.com           # ← fires first, catches full domain ✅
mweb-stage.koscap.or.kr==>your-gisu-host   # ← even more specific should come first
koscap==>acme                              # ← now safe: only matches non-domain uses
```

## Pitfalls

- **Don't run `git-filter-repo` on the working repo directly** — it removes remotes and you lose the origin. Always clone to tmp first.
- **Don't forget `.example` gitignore exceptions** — if `.gitignore` has `.env.*`, `.env.example` will be ignored too. Add `!.env.example` AFTER the pattern.
- **Don't stop at the working tree** — PII in past commits is still visible via `git blame` and accessible to anyone who clones history. Always use `git-filter-repo` for a full scrub.
- **Don't miss the second domain variant** — if the user has `realdomain.com` and `realdomain.org`, search for BOTH. Users often have one domain for infrastructure and another for email/SSL.
- **Don't miss commit messages** — `--replace-text` is for file contents only. Commit messages need a separate `--replace-message` pass. This is the #1 oversight — without it, the commit log still leaks.
- **Don't use `--all` in verification** — `git log --all --grep=` includes stale remote tracking refs that predate the filter. Use `git log HEAD --grep=` to verify the actual branch being pushed.
- **Don't forget filename callbacks return bytes** — `--filename-callback` in filter-repo receives `bytes`, not `str`. Use `filename.replace(b"old", b"new")` not `filename.replace("old", "new")`.
- **Don't forget case variants** — `koscap` is three different strings (`koscap`, `Koscap`, `KOSCAP`). Add all to the replacements file.
- **Don't order replacements wrong** — put specific full-domain patterns before generic project-name patterns. A `koscap==>acme` rule that fires before `koscap.or.kr==>client-domain.com` produces `acme.or.kr` instead of `client-domain.com`.
- **Don't force-push protected branches** — check with `git push --dry-run --force origin main` first, or push to an unprotected branch and ask for protection to be temporarily lifted.
- **Don't leave real passwords in example code** — even if the example looks generic, a real password like `T1tus!nbox_2026` is a production credential. Replace with `your-inbox-password` or similar.
- **Shell `echo` statements with escaped quotes** — shell scripts that print config vars via `echo "    VAR=\"value\""` are fragile under `patch` tool's escape-drift. The `\"` sequence can cause the patch tool to double-escape backslashes. Fix: read the exact line with `read_file`, then use the literal file content (including escaped quotes) as both old and new strings, or bypass `patch` and use `write_file` for the entire script section.
- **Don't stop after one TLD** — if you found `client.org`, also search for `client.com`, `client.or.kr`, `client.co.kr`, etc. Users often have different TLDs for different services (infrastructure vs email vs SSL certs). After fixing one, search for just the base word (e.g. `koscap`) to catch all variants.
- **Don't treat `127.0.0.1` or `localhost` as PII** — these are internal addresses and are safe to leave in public code.
- **`--refs HEAD` prevents re-processing backup refs** — after a prior filter-repo run, `refs/original/*` backup refs exist. Without `--refs HEAD`, the new pass will process them again and potentially create duplicate processing issues. Always pass `--refs HEAD`.

- **Clone from just-rewritten repo may fail checkout** — after `git filter-repo` rewrites history in a local repo, cloning from it can give `fatal: this operation must be run in a work tree`. The clone succeeds (objects transferred) but checkout fails. Fix with `git restore --source=HEAD :/` after clone. This happens because filter-repo invalidates the worktree index. If even `git restore` fails, re-clone from the remote after force-push instead.

- **Post-rewrite re-clone loses gitignored local files** — after force-pushing rewritten history and `rm -rf`/re-cloning the working repo, any gitignored files (agent-registry.json, .env, etc.) are gone. Always back up gitignored configs before destroying and re-cloning the working tree.
- **Don't assume credential files are safe just because they exist in the working tree.** A file like `agent-creds.md` may be caught by a glob pattern (`*cred*`), but verify with `git check-ignore <file>`. If it returns nothing, add a `.gitignore` pattern immediately. A credential file sitting un-ignored in the working tree is one accidental `git add -A` away from being committed.
- **Don't treat the repo's own GitHub URL as PII** — `github.com/user/repo` is the repo's public identity. Scrubbing the username from clone URLs, badge URLs, and script URLs breaks the repo for everyone. Distinguish: the repo's public address stays; personal infrastructure domains go.
- **Don't forget `.env.example` is tracked in git** — unlike `.env` (which is gitignored), `.env.example` is tracked and can contain real domains/URLs. Search it explicitly: it's the most common place for a real URL to lurk after you've scrubbed the main codebase. Same for any `.example`, `.template`, or `.sample` file.

## References

- `deploy/.env.example` — reference template for Langfuse docker-compose env vars
- `src/agent-registry.json.example` — reference template for agent registry with placeholder URLs
- `ops/scripts/inbox.conf.example` — reference template for inbox config
- `skills/software-development/public-contribution/SKILL.md` — PII→placeholder mapping table for contributions
