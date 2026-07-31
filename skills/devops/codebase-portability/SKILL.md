---
name: codebase-portability
version: 1.0.0
category: devops
description: >-
  Systematically find and fix hardcoded absolute paths across scripts, docs,
  and configs. Ensures codebases work regardless of clone location or OS.
  Covers BASH_SOURCE-based path derivation, OS-aware case dispatch,
  shutil.which for Python, and ${VAR:-default} fallback patterns for docs.
trigger: >-
  User asks to fix hardcoded paths, remove absolute path assumptions, make
  scripts portable, fix install-location assumptions, prevent path breakage
  when cloning, or 'no hardcoded paths'. Also applicable when migrating a
  codebase between machines or noticing a script has $HOME assumptions.
---

# Codebase Portability — Hardcoded Path Audit

Remove absolute path assumptions from scripts, configs, and documentation
so the codebase works regardless of where it's cloned or which OS runs it.

---

## Scan Phase

Run **multiple independent pattern scans** in parallel to find all
hardcoded paths before making any changes:

```bash
# Personal home directories (worst — breaks on any other user)
grep -rn '/home/luke' . 2>/dev/null
grep -rn '/home/moses' . 2>/dev/null
grep -rn '/Users/' . 2>/dev/null

# ~/repo-name assumptions (breaks if cloned elsewhere)
grep -rn '~/hermes-cortex' . 2>/dev/null
grep -rn '~/hermes-cortex-private' . 2>/dev/null

# Hardcoded binary paths (breaks if OS/pkg-manager differs)
grep -rn '/usr/local/bin/docker' . 2>/dev/null
grep -rn '/usr/local/bin/brew' . 2>/dev/null
grep -rn '/opt/homebrew/bin/' . 2>/dev/null

# macOS-only nginx/fail2ban paths (ignores Linux)
grep -rn '/usr/local/etc/nginx' . 2>/dev/null
grep -rn '/usr/local/etc/fail2ban' . 2>/dev/null
grep -rn '/usr/local/var/log/nginx' . 2>/dev/null

# Other common absolute paths
grep -rn '/home/' . 2>/dev/null
grep -rn '/opt/' . 2>/dev/null  # but NOT Dockerfile --mount target=/root/
grep -rn '/root/' . 2>/dev/null
```

**Exclude noise:** shebangs (`#!/usr/bin/env`), Docker build cache mounts
(`target=/root/`), standard OS paths (`/etc/ssl`, `/etc/letsencrypt`),
offline code corpus examples (reference snippets, not functional code),
`.plist` files (macOS launchd, system-specific).

## Categorize Findings

Sort into tiers before fixing:

| Tier | Type | Examples | Action |
|------|------|----------|--------|
| **1 — Critical** | Executable scripts with absolute paths | `~/...`, `/usr/local/bin/docker` | Fix immediately — blocks other users |
| **2 — Portability** | OS-specific paths in scripts | macOS-only nginx paths | Add OS-aware dispatch |
| **3 — Docs/Skills** | Instructional `~/repo/` paths | `cd ~/hermes-cortex` in SKILL.md | Use `$CORTEX_REPO` fallback pattern |
| **4 — Stale** | Docs describing only one OS | macOS-only setup instructions | Add Linux notes or platform table |

## Fix Patterns

### Pattern A: Script-relative repo path (Shell)

Replace `~/repo-name` or absolute `/home/user/repo-name` with auto-derived
path from `BASH_SOURCE`:

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"  # walk up to repo root
```

For scripts deeper in the tree, adjust the `..` count. Verify:

```bash
grep -n 'CORTEX_REPO\|SCRIPT_DIR\|SRC' path/to/script.sh
```

### Pattern B: OS-aware path dispatch (Shell)

Replace single-OS hardcoded paths with `case $(uname -s)`:

```bash
case "$(uname -s)" in
  Darwin)
    if [[ "$(uname -m)" == "arm64" ]]; then
      NGINX_DIR="/opt/homebrew/etc/nginx"
    else
      NGINX_DIR="/usr/local/etc/nginx"
    fi
    ;;
  Linux)
    NGINX_DIR="/etc/nginx"
    ;;
esac
```

Then use `$NGINX_DIR` throughout.

### Pattern C: Python binary discovery

Replace hardcoded `/usr/local/bin/docker` with `shutil.which`:

```python
import os, shutil

def _docker_bin() -> str:
    """Locate docker binary, falling back to PATH."""
    env = os.environ.get("DOCKER_BIN")
    if env:
        return env
    found = shutil.which("docker")
    return found or "docker"
```

### Pattern C2: Python OS-aware binary + config directory discovery

`shutil.which` finds binaries on PATH, but config trees (nginx, fail2ban,
postgres) live at OS-specific paths that `which` can't discover. For tools
like nginx where both the binary path AND the config directory vary by OS,
probe candidate paths directly:

```python
import os, sys

def _detect_nginx_paths() -> tuple[str, str]:
    """Detect nginx binary and config directory, platform-aware.

    Returns (nginx_bin, config_dir).
    Linux:       /usr/sbin/nginx, /etc/nginx
    macOS arm64: /opt/homebrew/bin/nginx, /opt/homebrew/etc/nginx
    macOS x86_64: /usr/local/bin/nginx, /usr/local/etc/nginx
    """
    candidates_bin = [
        "/usr/sbin/nginx",
        "/usr/local/bin/nginx",
        "/opt/homebrew/bin/nginx",
    ]
    nginx_bin = next(
        (p for p in candidates_bin if os.path.isfile(p)),
        "/usr/sbin/nginx",  # fallback
    )

    if sys.platform == "darwin":
        if os.uname().machine == "arm64":
            conf_dir = "/opt/homebrew/etc/nginx"
        else:
            conf_dir = "/usr/local/etc/nginx"
    else:
        conf_dir = "/etc/nginx"

    return nginx_bin, conf_dir
```

**When to use this vs Pattern C:** Use `shutil.which` when PATH resolution is
sufficient (most user-facing commands). Use candidate probing + OS dispatch
when the script also needs to find the tool's configuration tree, which
lives outside PATH's scope. Both are correct — they solve different problems.

**Same idiom for fail2ban, postgres, etc.** Adjust the candidate path lists
for the tool's known OS-specific install locations.

### Pattern D: Doc/skill path references

Replace bare `~/repo-name` with env-var fallback pattern:

```markdown
cd "${CORTEX_REPO:-$HOME/hermes-cortex}"
```

This works unset (defaults to `~/hermes-cortex`) or with `CORTEX_REPO` override.

For private repos with no env var convention:

```markdown
cd "${CORTEX_REPO:-$HOME/hermes-cortex}-private"
```

### Pattern E: macOS-only config paths

Replace `htpasswd /usr/local/etc/nginx/.htpasswd` with:

```markdown
htpasswd "${NGINX_HTPASSWD:-/usr/local/etc/nginx/.htpasswd}"
```

Also add OS-dependent note:

```markdown
Linux: `/etc/nginx/.htpasswd`, macOS: `/usr/local/etc/nginx/.htpasswd`
```

### Pattern G: Stale pathlib path references after repo restructure

When a repo restructures directory layout (e.g., `src/` → `ops/`, or
`deploy/` → `infra/`), pathlib-based relative paths in Python files
become stale in a way that grep for the full string `old/dir/` misses,
because pathlib splits them across string literals.

**Example stale pattern:**

```python
MCP_SERVERS_DIR = CORTEX_REPO / "src" / "mcp-servers"     # old
CORTEX_SCRIPTS = CORTEX_REPO / "src" / "scripts"           # old
```

**Scan — use terminal grep, not search_files tool:**

`search_files` (ripgrep) struggles with the `"pattern"` syntax needed
to match pathlib string literals. Use terminal grep instead:

```bash
# Find all pathlib-based stale refs to old dir names
grep -rn '"src"' . 2>/dev/null | grep -v '.git/' | grep -v '__pycache__'
grep -rn '"deploy"' . 2>/dev/null | grep -v '.git/'

# Also check docstrings and string formatting (non-pathlib refs)
grep -rn 'old-dir/' . 2>/dev/null | grep -v '.git/'
grep -rn 'old_dir/' . 2>/dev/null | grep -v '.git/'
```

**Mapping table — determine old→new mapping:**

| Old prefix | New prefix | Example |
|------------|-----------|---------|
| `ops/scripts/` | `ops/scripts/` | Python scripts |
| `src/mcp-servers/` | `ops/services/` | MCP server code |
| `src/offline/` | `ops/offline/` | Offline utilities |
| `src/web-cache/` | `ops/web-cache/` | Web cache modules |
|| `src/a2a/` | `ops/services/a2a/` (now deprecated, merged into agent-bus) | Agent card templates |

**Fix using patch tool with exact quotes:**

Pathlib paths are built from separate `"part"` string literals, so
the patch must match the whole `"old_part" / "next_part"` chain:

```python
# Before — two pathlib parts
CORTEX_SCRIPTS = CORTEX_REPO / "src" / "scripts"

# After — two parts, new names
CORTEX_SCRIPTS = CORTEX_REPO / "ops" / "scripts"
```

**Don't forget strings in docstrings, comments, and `add_issue` calls:**

These are plain text (not pathlib), so a broader search is needed:

```bash
grep -rn 'src/' . 2>/dev/null | grep -v '.git/' | grep -i 'scripts\|offline\|mcp\|a2a\|web-cache'
```

**Don't touch legitimate search paths:**

Repo-discovery candidates like `HOME / "src" / "repo-name"` are
**locating the repo root**, not referencing internal paths. Skip these:

```python
# ✅ LEGITIMATE — repo discovery, not stale internal reference
for candidate in [HOME / "hermes-cortex", HOME / "src" / "hermes-cortex"]:
```

**Verify with compile check:**

```bash
python3 -c "import py_compile; py_compile.compile('path/to/file.py', doraise=True)" && echo "OK"
```

After all fixes, a final sweep should show ZERO remaining stale
references:

```bash
# After all patches, confirm zero matches (should return only legit discovery paths)
grep -rn '"src"' path/to/scripts/*.py | grep -v 'discovery\|search\|candidate'
```

**Concrete reference:** `references/cortex-path-migration-july2026.md` in this
skill directory has the full transcript and file-by-file map from the
July 2026 `src/` → `ops/` migration.

### Pattern G2: sys.path.insert stale directory references after restructure

When a repo renames a top-level directory (e.g., `runtime/` → `core/`),
Python scripts that inject the old path via `sys.path.insert(0, ".../old-dir")`
will silently fail on import.

This is the same class of problem as Pattern G (pathlib stales after
restructure) but in a different Python construct — a plain string literal
in a function call, not pathlib path parts.

**Scan — search_files works fine for string literals (unlike pathlib):**

```text
search_files(pattern='sys.path.insert.*runtime')
search_files(pattern='sys.path.insert.*old-dir')
search_files(pattern='sys.path.insert.*src.*scripts')
```

Then verify the actual imported modules still exist at the new location:

```bash
# Check that the module the script tries to import actually exists
# under the new path, not the old one
find ~/hermes-cortex/core -name 'sla_watchdog.py' 2>/dev/null
```

**Fix — update the path string in sys.path.insert:**

```python
# Before
sys.path.insert(0, "~/hermes-cortex/runtime")
from agent_bus.workflow.sla_watchdog import main

# After
sys.path.insert(0, "~/hermes-cortex/core")
from agent_bus.workflow.sla_watchdog import main
```

**Two copies to patch (always):**

| Where | Why |
|-------|-----|
| Repo source (`hermes-cortex/ops/scripts/...`) | Upstream — survives next `cortex-update.sh` |
| Deployed copy (`~/.hermes-cortex/scripts/...`) | Runtime — runs right now |

The repo source comes first (upstream before one-off). If the deployed
copy and repo share the same inode (hard-linked), the first edit already
covers both — verify with `stat -c '%i' <path1> <path2>`.

**Required post-fix steps for cron scripts:**

After patching the deployed copy, the cron scheduler's internal
`last_status` is not updated by a bare Python run. Run the script
through the scheduler:

```text
cronjob(action='run', job_id='<job-id>')
```

Then confirm `last_status` changed from `"error"` to `"ok"`.

**Also check sibling scripts with the same pattern:**

Before declaring done, run the scan pattern broadly to find every
script with `sys.path.insert` pointing at any former directory name.
If the repo restructure renamed multiple dirs, check for each one:

```text
search_files(pattern='hermes-cortex/runtime')
search_files(pattern='hermes-cortex/src.*scripts')
```

A batch of 3+ scripts with the same stale prefix means the scan was
too narrow — widen it.

### Pattern F: Cross-platform service management via boolean dispatch helpers

When a script needs to start/stop/check **services** (not just find files), the
pattern used in `gbrain-wrapper.sh` encapsulates OS dispatch in helper functions
rather than scattering `if/then/elif` throughout the business logic:

```bash
# ── OS detection — set booleans once ──
IS_MAC=false; IS_LINUX=false
case "$(uname -s)" in
  Darwin) IS_MAC=true  ;;
  Linux)  IS_LINUX=true ;;
  *)      echo "⚠ Unknown OS: $(uname -s)" >&2; IS_LINUX=true ;;
esac

# ── Service names (adjust per platform) ──
SERVICE_NAME="gbrain-autopilot"
if $IS_MAC; then
  SERVICE_NAME="com.gbrain.autopilot"
fi

# ── Helper functions — OS dispatch encapsulated once ──

_service_is_active() {
  local name="$1"
  if $IS_LINUX; then
    systemctl --user is-active --quiet "$name" 2>/dev/null
  elif $IS_MAC; then
    local out
    out=$(launchctl list "$name" 2>/dev/null) || return 1
    echo "$out" | grep -q '"PID"' && return 0 || return 1
  fi
}

_service_stop() {
  local name="$1"
  if $IS_LINUX; then
    systemctl --user stop "$name" 2>/dev/null || true
  elif $IS_MAC; then
    launchctl bootout gui/$(id -u)/"$name" 2>/dev/null || true
  fi
}

_service_start() {
  local name="$1"
  if $IS_LINUX; then
    systemctl --user start "$name" 2>/dev/null || \
      echo "⚠ Could not start $name — systemd service not installed"
  elif $IS_MAC; then
    launchctl bootstrap gui/$(id -u)/"$name" 2>/dev/null || \
      launchctl kickstart gui/$(id -u)/"$name" 2>/dev/null || \
      echo "⚠ Could not start $name — launchd plist not installed"
  fi
}

# ── Business logic — clean, no OS branches ──
if _service_is_active "$SERVICE_NAME"; then
    _service_stop "$SERVICE_NAME"
    for i in $(seq 1 10); do
        ! _service_is_active "$SERVICE_NAME" && break
        sleep 1
    done
fi

# ... run the command that needs exclusive access ...

# On EXIT trap, restart:
if ! _service_is_active "$SERVICE_NAME"; then
    _service_start "$SERVICE_NAME"
fi
```

**When to use this vs Pattern B:** Pattern B (variable assignment via `case`)
is right when you only need to **evaluate** paths once (e.g., `NGINX_DIR`).
Pattern F (helper functions) is right when you need to **call** service
management repeatedly (start/stop/check) and don't want OS branches scattered
through the main logic.

**Concrete reference:** `ops/scripts/manage/gbrain-wrapper.sh` in the
hermes-cortex repo uses this exact pattern — 3 helpers, clean business logic,
no platform branches outside the helpers.

### Pattern H: Cross-file terminology rename

Rename a concept, service name, or API across docs and config files (not just
paths). The workflow is the same cross-file pipeline as the other patterns,
adapted for content changes.

**When to use:** The user asks to rename a system, tool, or concept across
documentation (e.g., "Agent Inbox → Agent Bus").

**Workflow — Search, Read, Categorize, Plan, Patch, Verify:**

```text
Search (find all occurrences, all case/separator variants)
  ↓
Read affected files (get full context around each match)
  ↓
Categorize (change / keep-as-legacy / skip-entirely / excluded-by-rules)
  ↓
Plan (what exact text each match becomes, where to add legacy notes)
  ↓
Patch (batch independent files, one-at-a-time for complex edits)
  ↓
Verify (comprehensive re-search, confirm zero unexpected refs remain)
```

**Step 1 — Search.** Find all occurrences using multiple search patterns for
different case/separator variants (they are independent, batch them):

```text
search_files(target='content', pattern='agent inbox')
search_files(target='content', pattern='Agent Inbox')
search_files(target='content', pattern='agent-inbox')
```

Also check camelCase / PascalCase / SCREAMING_SNAKE if the term is composable.

**Step 2 — Read and categorize.** For each file, decide each match's fate:

| Category | Meaning | Example |
|----------|---------|---------|
| **Change** | Replace with new term, add legacy note on first mention | Descriptions of the current system |
| **Legacy** | Keep old name but mark "(previously OldName)" | First mention in a doc about the new system |
| **Historical** | Keep as-is — intentional record of what existed | Migration docs, changelogs, research notes |
| **Excluded** | Do not touch per user instructions | orch-bus-setup.md, systemd units, cron names |
| **Name-only** | Keep filename/command/script name unchanged | Cron names like agent-inbox-workday |

**Step 3 — Plan.** For each "Change" and "Legacy" match, decide the exact
replacement. The patch tool requires verbatim old_string/new_string:

```markdown
# Heading replacement:
# Agent Inbox Architecture -> Agent Bus Architecture (previously Agent Inbox)

# Body text on first mention:
# via the agent inbox -> via the Agent Bus (previously Agent Inbox)
```

**Substep — Check for substring collision.** If the old term is a prefix or
substring of terms that must be preserved (e.g., rename `orch-bus-` to
`bus-` but `orch-bus-workflow-*` stays), explicitly list the preserved
patterns. Verify each preserved term would NOT be caught by a blanket
`replace_all` on the old term. A single scan of the full match set against
the preserved list — done once — prevents half the files from needing rework.

**Substep — Cross-check replacement consistency.** When the spec maps
multiple old→new pairs (e.g., `orch-bus-watch.sh` → `bus-watch.sh` and
`orch-bus-recover-timeouts` → `bus-recover-timeouts`), sanity-check that
no derived pair looks like a double-prefix error (`bus-bus-watch.sh`).
If one pair is inconsistent with the rest of the pattern, it's likely a
spec typo — use the majority pattern.

**Step 4 — Patch in batches.** Independent files can be patched concurrently.
Use `replace_all=true` when **every** occurrence of the old string in that
file should change identically. Do NOT use `replace_all` in a file where
some matches are protected (e.g., a file containing both changeable
`orch-bus-audit-watchdog` and protected `orch-bus-workflow-dispatcher`
references). For mixed files, patch each unchangeable occurrence with a
targeted `old_string` that includes enough surrounding context to be
unique, then apply `replace_all` for the remaining bulk matches, OR handle
every occurrence individually with targeted patches.

Do NOT batch patches to the same file — concurrent patches to the same file
race on the inode. When batching across files, batch the independent ones.

**Step 5 — Verify.** After all patches, re-run all search patterns. Confirm:

- Every remaining reference is in an intentionally-kept category
- The old term is never used to describe the current system
- No excluded file was accidentally modified
- Zero unplanned references remain

**Reference file:** references/terminology-rename-agent-inbox-to-bus.md in
this skill's directory has the full worked example — 17 files, 60+ patches.

## Verification

After each fix, confirm with targeted grep that the old pattern is gone:

```bash
grep -c '/home/luke' path/to/script.sh          # should be 0
grep -c 'CORTEX_REPO\|SCRIPT_DIR' path/to/script.sh  # should be >0
grep -c '_docker_bin' path/to/python.py          # should be >0
```

### Shell scripts: always run `bash -n` after bulk edits

The `patch` tool's fuzzy matching can corrupt complex quoting inside heredocs
(especially grep `-oP` patterns with embedded single-quote sequences inside
bash `-c` strings). Always run a bulk syntax check after editing `.sh` files:

```bash
for f in path/to/scripts/*.sh; do
  echo -n "$f: "
  bash -n "$f" 2>&1 && echo "OK" || echo "FAILED"
done
```

This catches:
  - Indentation breaks from misaligned patch context
  - Corrupted grep/sed quoting inside heredocs
  - Broken continuation lines (`\` at end of line)

### Hard-linked script dirs

On Hermes deployments, `~/.hermes/scripts/` and `~/.hermes-cortex/scripts/` may
share the same inode (hard-linked copies). Editing one modifies both
automatically — no need to patch separately. Verify with:

```bash
stat -c '%i' ~/.hermes/scripts/some-script.sh ~/.hermes-cortex/scripts/some-script.sh
# Same inode → same file
```

### Final sweep: verify zero stale refs remain

After all patches, use `search_files(output_mode='count')` to confirm zero
matches for each stale prefix:

```bash
grep -rc 'old-src-dir/' target-dir/ 2>/dev/null | grep -v ':0$'
grep -rc 'old-deploy-dir/' target-dir/ 2>/dev/null | grep -v ':0$'
```

## Reference files

| File | Covers |
|------|--------|
| `references/systemd-percent-h-specifier.md` | systemd `%h` vs `%u` specifier nuances |
| `references/macos-memory-service-detection.md` | macOS-specific memory + service detection |
| `references/hermes-cortex-path-audit.md` | Full path audit of the hermes-cortex repo |
| `references/gbrain-wrapper-crossplatform.md` | Concrete Pattern F example — gbrain-wrapper.sh |
| `references/gh-cli-headless-install.md` | Install gh CLI without sudo + OAuth device-code flow |
| `references/cortex-path-migration-july2026.md` | Stale pathlib path migration after `src/` → `ops/` restructure (Pattern G) |
| `references/stale-syspath-post-runtime-restructure.md` | Stale `sys.path.insert` after `runtime/` → `core/` restructure (Pattern G2) |
| `references/terminology-rename-agent-inbox-to-bus.md` | Full worked example — 17-file terminology rename (Pattern H) |
| `references/python-import-cwd-debugging.md` | Debugging Python imports that fail from one CWD but not another (sys.path + __file__ resolution diagnosis) |

## Pitfalls

- **Dockerfiles/container paths** (`target=/root/.npm`) are internal and do
  NOT need fixing — they're inside the container, not the host.
- **Offline code corpus** snippets are educational examples, not functional
  code. Skip them.
- **`.plist` files** are macOS launchd system files. Their paths are correct
  for their target platform.
- **Shebangs** (`#!/usr/bin/env bash`) are standard and portable. Do not
  change them.
- **`/etc/nginx` on Linux** is a standard OS path, not project-specific.
  OS-aware dispatch is the right fix, not removing it.
- **Don't touch the table structure** when updating tables in docs — replace
  only the content, not the pipe/dash separator rows.
- **Escape-drift warning:** When using `patch` tool, read the exact line
  from the file and paste it verbatim — escaping quotes differently
  (`\\\"` vs `\"`) causes the patch to fail.
- **`search_files` misses pathlib literal patterns:** The `search_files` tool
  (ripgrep backend) returns 0 results for patterns like `"src"` because of
  quote-escaping. For pathlib-based path searches (`"old_dir" / "subdir"`),
  **always use terminal `grep -rn`** with the exact quote syntax instead.
  `search_files` works fine for continuous-string paths like `ops/scripts/`.
- **Governance lock must span the entire batch:** Multi-file patches on the
  same repo may encounter a stale governance lock from a prior session.
  Call `check_lock()` before starting. If the lock belongs to a different
  task_id, force-acquire with `begin_change(..., force=True)`. Score and
  release the cycle only once — after ALL patches are done and verified,
  not mid-batch. Scoring mid-batch releases the lock and blocks subsequent
  writes.