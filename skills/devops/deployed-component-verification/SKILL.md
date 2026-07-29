---
name: deployed-component-verification
version: 1.1.0
category: devops
description: "Verify deployed components match their repo source — detect stale copies, validate symlinks, and ensure the fleet runs fresh code after git pulls."
author: Moses
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [deployment, verification, stale-detection, doctor, governance, immutability]
    related_skills: [change-checklist, survey-before-action, auto-remediation-ecosystem, system-remediation, hermes-cortex-deployment]
---

# Deployed Component Verification

## Problem

A component deployed to `~/.hermes/plugins/`, `~/.hermes-cortex/scripts/`,
or `~/.hermes/mcp-servers/` can be either a **symlink** to the repo source
or a **copy**. After `git pull`, repo source is updated — but copies are not.
An agent running with a stale copy silently runs old code.

## Two Approaches — Context Matters

Which approach is correct depends on whether the component needs
**immutability** (`chattr +i`) for security hardening.

### Symlink — simpler, always fresh, no immutability

A symlink shares an inode with the repo source. After `git pull`, the
deployed component is automatically fresh — no copy needed.

**Use when:** The component does NOT require `chattr +i` immutability.

```python
deployed = Path.home() / ".hermes" / "plugins" / "governance-enforcer"
if deployed.is_symlink():
    target = os.readlink(str(deployed))
    if "hermes-cortex/plugins" in target:
        return "FRESH (symlink)"
    else:
        return "CHECK_TARGET (wrong symlink target)"
```

### Copy — required for immutability, needs lifecycle management

A `chattr +i` on a symlink target ALSO locks the repo's tracked file,
because they share an inode. `git pull` would fail when trying to update
the repo file. Therefore, to secure a component with `chattr +i`, it MUST
be deployed as a standalone copy.

**Use when:** The component needs `chattr +i` immutability (governance
enforcer plugin, critical enforcement hooks).

```python
import hashlib

deployed_file = deployed / "__init__.py"
repo_file = repo_root / "plugins" / "governance-enforcer" / "__init__.py"

if hashlib.sha256(deployed_file.read_bytes()).hexdigest() == \
   hashlib.sha256(repo_file.read_bytes()).hexdigest():
    return "FRESH (content matches)"
else:
    return "STALE (content differs — run cortex-update.sh --force-all)"
```

## The Copy Deployment Lifecycle

When a component is deployed as a copy, updates require an explicit lifecycle
to handle immutability. This is handled by `cortex-update.sh`'s
`deploy_governance_plugin()` function:

```
1. Check if deployed file has chattr +i
2. If immutable → sudo hermes-plugin-lock unlock  (removes +i)
3. Copy updated files from repo
4. chmod 444 on __init__.py
5. If sudoers configured → sudo hermes-plugin-lock lock  (re-applies +i)
```

If the sudoers entry for `hermes-plugin-lock` is not set up, steps 2 and 5
fail gracefully with a warning telling the user what to do.

### Restricted Helper Pattern

For any agent operation that requires `sudo`, DO NOT give the agent raw
`sudo chattr` access. Instead:

1. Write a **restricted helper script** to `/usr/local/sbin/` that:
   - Hardcodes the exact path it can operate on
   - Only accepts a fixed set of arguments (e.g., `lock`, `unlock`, `status`)
   - Has no argument injection surface
2. Add a NOPASSWD sudoers entry for ONLY that script path

**Canonical example:** `/usr/local/sbin/hermes-plugin-lock`:

```bash
#!/usr/bin/env bash
set -euo pipefail
REAL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo "$USER")}"
REAL_HOME="$(getent passwd "$REAL_USER" 2>/dev/null | cut -d: -f6)"
TARGET="${REAL_HOME}/.hermes/plugins/governance-enforcer/__init__.py"

[[ -f "$TARGET" ]] || { echo "ERROR: Not found"; exit 1; }

case "${1:-help}" in
  lock)    chattr +i "$TARGET"; echo "LOCKED" ;;
  unlock)  chattr -i "$TARGET"; echo "UNLOCKED" ;;
  status)  lsattr "$TARGET" ;;
  *)       echo "Usage: $0 {lock|unlock|status}" ;;
esac
```

Sudoers entry (one-time setup by the human):

```
moses ALL=(root) NOPASSWD: /usr/local/sbin/hermes-plugin-lock
```

The agent can then call `sudo hermes-plugin-lock lock` — it can ONLY lock
that one file, on that one path, with no argument injection possible.

## Decision Table: Symlink vs Copy

| Factor | Symlink | Copy |
|--------|---------|------|
| Freshness after `git pull` | Auto-fresh | Stale (needs `--force-all`) |
| Freshness after `--force-all` | Auto-fresh | Fresh (re-copied) |
| Supports `chattr +i`? | ❌ Locks repo file | ✅ Locks only deployed copy |
| Deployment complexity | Simple (`ln -sf`) | Lifecycle required (unlock→copy→relock) |
| Doctor checks | PASS (or WARN since Jul 2026) | PASS + SHA256 + perms + immutability |
| Sudo needed | No | Yes (for chattr, via restricted helper) |

### Doctor Behavior (current as of Jul 2026)

When the doctor finds a symlink, it now emits a WARN suggesting conversion
to copy (for chattr +i hardening). When it finds a copy, it verifies:
- Content matches repo (SHA256)
- Perms are 0o444
- chattr +i is set

### When to Choose What

- **Governance enforcer plugin** — COPY. Needs chattr +i to prevent agents
  from modifying their own enforcement rules. The deployment lifecycle is
  handled by `cortex-update.sh --force-all`.
- **User-installed plugins** — SYMLINK. No immutability needed, and
  symlinks keep them fresh without explicit re-deploy.
- **Hooks** (`pre-commit`, `pre-push`, `post-commit`) — COPY. These are
  enforcement entry points and should be immutable.

## Components Requiring Staleness Checks

Most components deployed by `cortex-update.sh` `register()` are freshly copied
on every `--force-all` and need no staleness check. The exceptions are
**manually symlinked** components:

| Component | Deploy Path | Repo Source |
|-----------|-------------|-------------|
| Governance enforcer plugin | `~/.hermes/plugins/governance-enforcer/` | `plugins/governance-enforcer/` |
| Any manually linked Hermes plugin | `~/.hermes/plugins/*/` | `plugins/*/` |
| MCP server scripts (if manually copied) | `~/.hermes/mcp-servers/` | `mcp-servers/` |

## Integration: Doctor Check Pattern

The canonical implementation is in `cortex-doctor.py` `check_governance()`:

```python
plugin_dir = HERMES_HOME / "plugins" / "governance-enforcer"
plugin_src = CORTEX_REPO / "plugins" / "governance-enforcer"

if plugin_dir.exists() and (plugin_dir / "__init__.py").exists():
    if plugin_dir.is_symlink():
        # WARN — suggest conversion to copy for hardening
        target = os.readlink(str(plugin_dir))
        res.add("Plugin symlink", "WARN",
                f"symlinked to {target} — convert to copy for chattr +i",
                "Run: cortex-update.sh --force-all (auto-converts)")
    else:
        # Copy mode — SHA256 comparison, perms, immutability
        deployed_hash = hashlib.sha256(
            (plugin_dir / "__init__.py").read_bytes()
        ).hexdigest()
        repo_hash = hashlib.sha256(
            (plugin_src / "__init__.py").read_bytes()
        ).hexdigest()
        if deployed_hash == repo_hash:
            res.add("Plugin content", "PASS", "copy matches repo source")
        else:
            res.add("Plugin content", "FAIL",
                    "deployed copy differs from repo — run: cortex-update.sh --force-all")
```

## When to Create a Staleness Check

When adding a doctor check or health monitor for a component that:

1. Is deployed to `~/.hermes/` or `~/.hermes-cortex/`
2. Is NOT registered in `cortex-update.sh` (i.e., manually installed or symlinked)
3. If the component IS registered in `cortex-update.sh` and copied fresh on
   every `--force-all` — no staleness check needed

## Cross-Platform Considerations

The restricted helper pattern and immutability lifecycle must work on ALL
platforms agents run on. Currently two platforms are supported:

| Aspect | Linux | macOS (Darwin) |
|--------|-------|----------------|
| Immutability command | `chattr +i` / `chattr -i` | `chflags uchg` / `chflags -N` (user), `chflags schg` (root) |
| Check immutable flag | `lsattr <file>` | `ls -lO <file>` (look for `uchg` or `schg` in flags column) |
| Helper path | `/usr/local/sbin/hermes-plugin-lock` | `/usr/local/sbin/hermes-plugin-lock` (same path) |
| Sudoers directory | `/etc/sudoers.d/` | `/etc/sudoers.d/` (macOS supports this) |
| Sudoers file name | `/etc/sudoers.d/hermes` | `/etc/sudoers.d/hermes` (same name) |
| `sudo -n` support | Yes | Yes (macOS supports `-n` flag) |

### Building a Cross-Platform Helper Script

The helper script must detect the OS and use the right immutability command:

```bash
#!/usr/bin/env bash
set -euo pipefail
REAL_USER="${SUDO_USER:-$(logname 2>/dev/null || echo "$USER")}"
REAL_HOME="$(getent passwd "$REAL_USER" 2>/dev/null | cut -d: -f6)"
TARGET="${REAL_HOME}/.hermes/plugins/governance-enforcer/__init__.py"

[[ -f "$TARGET" ]] || { echo "ERROR: Not found at $TARGET"; exit 1; }

_os=$(uname -s)

case "${1:-help}" in
  lock)
    if [[ "$_os" == "Darwin" ]]; then
      chflags uchg "$TARGET"
    else
      chattr +i "$TARGET"
    fi
    echo "LOCKED"
    ;;
  unlock)
    if [[ "$_os" == "Darwin" ]]; then
      chflags -N "$TARGET"   # -N removes all user flags (uchg, nouchg, etc.)
    else
      chattr -i "$TARGET"
    fi
    echo "UNLOCKED"
    ;;
  status)
    if [[ "$_os" == "Darwin" ]]; then
      ls -lO "$TARGET" | awk '{for(i=1;i<=NF;i++) if($i ~ /chg$/) print $i}'
    else
      lsattr "$TARGET"
    fi
    ;;
  *) echo "Usage: $0 {lock|unlock|status}" ;;
esac
```

Sudoers entry (same across platforms — macOS `/etc/sudoers.d/` supports the
same syntax):

```
moses ALL=(root) NOPASSWD: /usr/local/sbin/hermes-plugin-lock
```

### Sudoers File Naming Convention

Always name the sudoers file `hermes` (under `/etc/sudoers.d/hermes`), NOT
`hermes-plugin-lock`. The file can contain multiple rules for different
helpers. Using a single `hermes` file avoids:
- Cluttering `/etc/sudoers.d/` with one-file-per-helper
- Confusion when cortex-update.sh's deploy warning references a different name
- Having to remember which filename each agent used

On this system, the file at `/etc/sudoers.d/hermes` contains all Hermes-related
sudoers entries (plugin lock helper, nginx management, apt cleanup, etc.).

### Doctor Check Pattern for Verifying a Restricted Helper

When adding a doctor check for a deployed restricted helper, follow this pattern:

```python
def _check_helper(res, path, label, sudo_test_cmd):
    """
    Generic helper-verification check.
    
    Args:
        res: Results collector (from results.py)
        path: Path to the helper binary (Path object)
        label: Display label for the check
        sudo_test_cmd: List of args for sudo -n functional test
                       (e.g. ["sudo", "-n", "/usr/local/sbin/hermes-plugin-lock", "status"])
    """
    # 1. Binary exists
    if not path.exists():
        res.add(label, "FAIL",
                f"{path.name} not found at {path.parent}",
                f"Run: sudo cortex-update.sh or deploy manually")
        return
    # 2. Binary is executable
    if not os.access(str(path), os.X_OK):
        res.add(label, "FAIL",
                f"{path.name} exists but is not executable",
                f"Fix: sudo chmod 755 {path}")
        return
    # 3. Functional test via sudo -n (proves sudoers entry + helper work)
    import subprocess
    try:
        result = subprocess.run(
            sudo_test_cmd,
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            res.add(label, "PASS",
                    f"helper + sudoers OK ({result.stdout.strip()[:60]})")
        else:
            res.add(label, "FAIL",
                    f"sudo -n {path.name} status exited {result.returncode}: "
                    f"{result.stderr.strip()[:60]}",
                    "Check sudoers entry for the helper path")
    except (subprocess.TimeoutExpired, OSError) as e:
        res.add(label, "FAIL",
                f"sudo -n {path.name} status failed: {e}",
                "Check sudoers entry and helper binary")
```

**Key design decisions:**
- **NO separate sudoers file scan** — `/etc/sudoers.d/` files are `r--r-----`
  owned by root and NOT world-readable. Reading them as the moses user
  always fails with PermissionError. The `sudo -n` functional test IS the
  proof that the sudoers entry exists.
- **FAIL, not WARN** — A missing helper is a hard failure, not advisory.
  If the helper is missing, the immutability lifecycle is broken and
  `cortex-update.sh`'s lock/unlock fails silently.
- **One check, three states** — binary missing (FAIL), binary present but
  sudo-n fails (FAIL), everything works (PASS). No partial states.

### When to Add a Doctor Helper Check

Add a check like `_check_plugin_lock_helper()` when:
- A restricted helper script is deployed to `/usr/local/sbin/`
- The helper requires a sudoers NOPASSWD entry to function
- A component's lifecycle depends on the helper working (lock/unlock cycles)
- Multiple agents in the fleet need to independently verify their setup

### Copy Deployment Lifecycle — Platform Detail

On **Linux**:
1. Check `chattr +i` via `lsattr` — if set → `sudo hermes-plugin-lock unlock`
2. Copy updated files from repo
3. `chmod 444` on `__init__.py`
4. `sudo hermes-plugin-lock lock`

On **macOS**:
1. Check `chflags uchg` via `ls -lO` — if set → `sudo hermes-plugin-lock unlock`
2. Copy updated files from repo  
3. `chmod 444` on `__init__.py`
4. `sudo hermes-plugin-lock lock`

The helper script must handle both platforms transparently.

## Related

- `cortex-update.sh` `deploy_governance_plugin()` — the canonical deploy lifecycle
- `/usr/local/sbin/hermes-plugin-lock` — the restricted sudo helper
- `hermes-cortex-deployment` — full deployment lifecycle for Cortex agents
- `agent-health-monitor` — cross-agent component verification
- `sudoers-audit` — sudoers rule audit and debugging

---

## Stale Deploy Detection

Beyond individual component freshness, the **deploy directory** as a whole
can accumulate orphaned files when `register()` entries are removed from
`cortex-update.sh` without cleaning up the deployed copy.

### The Pattern

`cortex-update.sh` has a `MAP` array built by `register()` calls. On deploy,
it iterates MAP and copies each source to its destination. If a `register()`
line is removed, the deployed file stays on disk — an orphan.

### Detection: `check_stale_deploys()` in the doctor

The doctor now includes a `check_stale_deploys()` function that:

1. Reads `cortex-update.sh` and parses all active `register()` calls
2. Resolves variable references (`${CORTEX_DEPLOY_HOME}`, `${HOME}`)
3. Builds a set of expected destinations
4. Scans `~/.hermes-cortex/scripts/` for `.py` and `.sh` files
5. Flags any file NOT in the expected destinations as **stale**
6. Also flags files that are symlinks (should be copies) and source files
   that don't exist

Implementation sketch:

```python
import re
from pathlib import Path

content = Path("cortex-update.sh").read_text()
deploy_home = Path.home() / ".hermes-cortex"
destinations = set()

for line in content.splitlines():
    line = line.strip()
    if not line.startswith("register ") or line.startswith("#"):
        continue
    m = re.match(r'register\s+"([^"]+)"\s+"([^"]+)"', line)
    if m:
        dest_str = m.group(2)
        dest_str = dest_str.replace("${CORTEX_DEPLOY_HOME}", str(deploy_home))
        dest_str = dest_str.replace("${HOME}", str(Path.home()))
        destinations.add(Path(dest_str))

for f in (deploy_home / "scripts").rglob("*"):
    if f.suffix in (".py", ".sh") and f not in destinations:
        print(f"STALE: {f}")
```

### Auto-Cleanup: `cortex-update.sh --clean-stale`

After every `--force-all` deploy, `cortex-update.sh` now auto-runs
`clean_stale_deploys()`:

1. Builds destinations from MAP entries (same as doctor check)
2. Scans `~/.hermes-cortex/scripts/` for stale files
3. Deletes orphans (respects `--dry-run` for preview)

```bash
bash cortex-update.sh --force-all --dry-run  # preview
bash cortex-update.sh --force-all            # apply
```

### Scripts Directory vs Other Deploy Paths

The `scripts/` directory under `CORTEX_DEPLOY_HOME` is the primary target
for stale detection because:
- It contains only files deployed via `register()`
- It has no mixed-content (other files from other sources)
- It's the largest deploy surface (~200 files)

Other deploy paths (`dashboard/`, `bus/`, `offline/`) have mixed content,
so stale detection there is not implemented — but the same pattern would
apply if needed.
