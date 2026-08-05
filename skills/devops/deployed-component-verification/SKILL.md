---
name: deployed-component-verification
version: 1.1.0
category: devops
description: "Verify deployed components match their repo source — detect stale copies, validate symlinks, and ensure the fleet runs fresh code after git pulls."
author: Hermes Cortex
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
    return "STALE (content differs — run cortex-update.sh)"
```

## The Copy Deployment Lifecycle

When a component is deployed as a copy, updates require an explicit lifecycle
to handle immutability. This is handled by `cortex-update.sh`'s
`deploy_governance_plugin()` function:

```
1. Check if deployed file has chattr +i
2. If immutable → sudo hermes-plugin-lock unlock --cortex-update  (sanctioned token; removes +i)
3. Copy updated files from repo
4. chmod 444 on __init__.py
5. If sudoers configured → sudo hermes-plugin-lock lock  (re-applies +i)
```
> **Since 2026-07-31** `unlock`/`update` are gated: they require the
> `--cortex-update` token (cortex-update.sh) or an orchestrator Unix account
> (`--orchestrator`). Plain `sudo hermes-plugin-lock unlock` is REFUSED + audit-logged.

### Blanket Lock at End of Deploy

For the full enforcement chain, a **blanket lock** runs at the END of
`cortex-update.sh main()` after ALL files are deployed. This ensures
every enforcement file is locked atomically, not just the ones the
plugin deployer handled:

```bash
# Step 1: Lock via sudo hermes-plugin-lock (NOPASSWD — covers 5 core files)
if command -v hermes-plugin-lock &>/dev/null; then
  sudo hermes-plugin-lock lock
fi
# Step 2: Lock new paths with chmod 444 (if chattr +i needs sudo)
for _target in "$POST_MERGE" "$MCP_SERVER" "$LOCK_HELPER"; do
  if [[ -f "$_target" ]]; then
    chmod 444 "$_target" 2>/dev/null || true
  fi
done
```

This pattern handles the bootstrap problem: old files get chattr +i via
the old helper, new files get chmod 444 until the helper is updated.

### Deployment Pitfall: Self-Lock Loop

When the helper binary lists ITSELF as a target (for self-protection),
every deploy must unlock the helper before overwriting it. Two mechanisms:

1. **check_each_mapped_file()** does a blanket `sudo hermes-plugin-lock unlock --cortex-update`
   at the start of the copy loop.
2. **deploy_system_scripts()** has special handling for `hermes-plugin-lock`:
   it tries `sudo -n "$dest" update --cortex-update` first (self-update), then falls back
   to `sudo cp` if the self-update isn't available.

Without this, the helper locks itself on deploy N, and deploy N+1 can't
overwrite it — `cp` fails with "Operation not permitted" even via sudo.

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

**Canonical example:** `/usr/local/sbin/hermes-plugin-lock` (or deployed to
`~/.hermes-cortex/scripts/hermes-plugin-lock` for user-writable paths):

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

### Real-World: Multi-Target Restricted Helper

A production lock helper typically manages MULTIPLE critical files — not
just the enforcer plugin. The real `/usr/local/sbin/hermes-plugin-lock`
on this system has 8 targets:

```bash
TARGETS=(
  "${REAL_HOME}/.hermes/plugins/governance-enforcer/__init__.py"
  "${REAL_HOME}/.hermes-cortex/scripts/pre-commit-score"
  "${REAL_HOME}/.hermes-cortex/scripts/pre-push-pull"
  "${REAL_HOME}/.hermes-cortex/scripts/post-commit-audit"
  "${REAL_HOME}/.hermes-cortex/scripts/post-push-audit"
  "${REAL_HOME}/.hermes-cortex/hooks/post-merge"
  "${REAL_HOME}/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py"
  "${REAL_HOME}/.hermes-cortex/scripts/hermes-plugin-lock"    # self-protection
)
```

Each target gets `chattr +i` (Linux) or `chflags uchg` (macOS) atomically.
The helper also supports a `--self-update` command: when cortex-update.sh
has a new version, the helper reads from the repo source and overwrites
itself.

### Deploying the Helper: Bootstrap Problem

The helper is the ONLY NOPASSWD sudo entry on the system (by design — see
sudoers below). This creates a bootstrap problem: how do you update the
helper binary if `sudo cp` requires a password?

Three approaches, in order of preference:

1. **Register in MAP** (best) — Deploy the helper to `~/.hermes-cortex/scripts/`
   via `cortex-update.sh`'s `register()` call. This path is user-writable,
   so no sudo needed for the copy. The blanket lock at end of deploy then
   applies `sudo hermes-plugin-lock lock` which covers all targets.
2. **Self-update command** — If the helper is already at `/usr/local/sbin/`,
   its `update` command reads from the repo source (`$REAL_HOME/hermes-cortex/...`)
   and overwrites itself. Requires the update command to NOT use `local`
   keyword (which breaks with `set -e` in bash case statements outside functions).
3. **Direct deploy** — If the user has interactive sudo access, `sudo cp repo/src /usr/local/sbin/hermes-plugin-lock` works for one-time bootstrap.

### chattr +i Requires Root (CAP_LINUX_IMMUTABLE)

On Linux, `chattr +i` on ext4 requires the `CAP_LINUX_IMMUTABLE`
capability, which is only available to root — even when the file
is owned by the calling user:

```bash
# ❌ FAILS even on user-owned file if called as non-root
chattr +i ~/myfile.txt
# → "chattr: Operation not permitted while setting flags on ..."

# ✅ WORKS when called from a root-owned process (e.g., via sudo helper)
sudo hermes-plugin-lock lock
```

This means the restricted helper MUST be called via `sudo` (with NOPASSWD)
for `chattr +i` to work. Running the same script directly (without sudo)
will fail on the `chattr +i` calls, even though the file is user-owned
and the script has permission to read/write it normally.

**Fallback for files that cannot get chattr +i:** `chmod 444` (read-only
for owner). This is weaker than chattr +i (root can still override), but
stronger than the default 755. The doctor checks for chattr +i at FAIL
level, so missing immutability is always visible.

Sudoers entry (one-time setup by the human):

```
moses ALL=(root) NOPASSWD: /usr/local/sbin/hermes-plugin-lock
```

The agent can then call `sudo hermes-plugin-lock lock` — it can ONLY lock
that one file, on that one path, with no argument injection possible.

## Decision Table: Symlink vs Copy

| Factor | Symlink | Copy |
|--------|---------|------|
| Freshness after `git pull` | Auto-fresh | Stale (needs a deploy) |
| Freshness after deploy | Auto-fresh | Fresh (re-copied) |
| Supports `chattr +i`? | ❌ Locks repo file | ✅ Locks only deployed copy |
| Deployment complexity | Simple (`ln -sf`) | Lifecycle required (unlock→copy→relock) |
| Doctor checks | PASS → FAIL if immutable flag missing (since Jul 2026) | PASS + SHA256 + perms + immutability |
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
  handled by `cortex-update.sh`.
- **User-installed plugins** — SYMLINK. No immutability needed, and
  symlinks keep them fresh without explicit re-deploy.
- **Hooks** (`pre-commit`, `pre-push`, `post-commit`) — COPY. These are
  enforcement entry points and should be immutable.

## Running Code ≠ Deployed File — the Gateway Memory Trap

The doctor's staleness checks compare files on DISK (repo vs deployed copy).
They do NOT prove the RUNNING process executes the new code. The Hermes
gateway loads plugins (including the governance enforcer) into memory at
STARTUP. A gateway that started before a deploy keeps running the OLD
enforcer logic even when the deployed file hash matches the repo.

**Confirmed 2026-07-31:** after deploying the P1-A enforcer fix
(sticky-lock + atomic lock writes), write tools were still blocked with
"8/8 skills loaded ✅" — the gateway (started 11:33) was running the
pre-fix enforcer loaded at boot, while the on-disk file (deployed 14:04)
had the fix. The doctor reported "enforcer deployed==repo hash MATCH"
because it checks disk, not memory. The gateway cannot self-restart
(pattern-blocked from inside); schedule it detached:
`systemd-run --user --on-active=3s --unit=hermes-gw-restart hermes gateway restart`.

**Rule:** after ANY enforcer/hook/plugin change that affects governance,
restart the gateway before testing the new behavior. "Hash match" proves
deployment, not activation.

### DOGFOOD Compare: use `git show HEAD:`, never the dirty working tree

The pre-commit DOGFOOD gate must compare COMMITTED HEAD vs deployed, not
the working tree vs deployed. A dirty working tree:
- Triggers false blocks that cortex-update.sh can't resolve (it deploys
  from origin, not local edits) — HEAD==deployed but tree dirty.
- Allows an uncommitted edit to be pushed into the deployed enforcer by
  the auto-deploy path (dirty-tree injection).

Orchestrator-authoring exception (host detected via `_detect_orch` AND staged
enforcer change) auto-deploys the working tree — the orchestrator is the
sanctioned author. Everyone else with HEAD≠deployed gets the hard block.
(AGENT_ID is obsolete; the hook only uses it to log claimed-identity
impersonation attempts.)

### Update-from-working-tree is root code execution

`hermes-plugin-lock update` reads its source from the repo working tree
(user-writable). Without a committed-source guard, ANY agent can edit the
helper copy, then `sudo hermes-plugin-lock update --cortex-update` (the
token is forgeable) to install their modified code as root. Guard:
`git diff --quiet HEAD -- ops/install/deploy/nginx/hermes-plugin-lock` —
refuse with exit 1 + audit entry when uncommitted changes exist.

## Components Requiring Staleness Checks

Most components deployed by `cortex-update.sh` `register()` are freshly copied
on every deploy and need no staleness check. The exceptions are
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
                "Run: cortex-update.sh (auto-converts)")
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
                    "deployed copy differs from repo — run: cortex-update.sh")
```

## When to Create a Staleness Check

When adding a doctor check or health monitor for a component that:

1. Is deployed to `~/.hermes/` or `~/.hermes-cortex/`
2. Is NOT registered in `cortex-update.sh` (i.e., manually installed or symlinked)
3. If the component IS registered in `cortex-update.sh` and copied fresh on
   every deploy — no staleness check needed

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

### NEVER mutate live sudoers from an installer — verify read-only, fail closed

**Luke directive 2026-08-05:** "the one that exists SHOULD NOT BE WRITTEN
OVER." `/etc/sudoers.d/hermes` is the single live policy file; its owner is
`deploy-sudoers.sh` (backup → visudo validate → restore-on-failure). A deploy
script for a DIFFERENT artifact must not rm/sed/append/chmod it.

Anti-patterns seen in the old `deploy-fix-blocked-ips.sh`:
- `rm -f /etc/sudoers.d/hermes-security` — dead code under the single-file
  policy (2026-07-31); the split file does not exist
- `sed -i` sweep of EVERY `/etc/sudoers.d/*` + `/etc/sudoers` deleting lines
  matching an old path — blind rewrite of live sudoers
- append to `/etc/sudoers.d/hermes` + `chmod 0440` — wrote to the file
  owned by deploy-sudoers.sh

Correct shape (committed `b33a9fad`): install the binary (unlock old
immutable copy → `install -o root -g root -m 755` → `chattr +i`), then
**verify read-only** that the NOPASSWD entry exists:
`grep -qF "/usr/local/sbin/fix-blocked-ips.py" /etc/sudoers.d/hermes`; if
missing, exit 1 and direct the operator to `deploy-sudoers.sh`.

### sudo env_reset breaks $HOME-based path resolution in root-owned copies — pass paths via argv

**Symptom (2026-08-05):** `nginx-threat-pipeline` committed+pushed new
blocked IPs every run but the deploy step failed silently for 5 days: repo
`blocked_ips.add` had 18,353 lines, live `/etc/nginx/blocked_ips.conf` had
17,287 deny rules (~1,066 IPs never applied). Log: `✗ Source not found:
/usr/local/sbin/ops/install/deploy/nginx/blocked_ips.add`.

Root cause chain:
1. P1-A hardening moved the NOPASSWD target to a root-owned immutable copy
   at `/usr/local/sbin/fix-blocked-ips.py` (install-only, `chattr +i`).
2. The script's `repo_dir()` walks up from script location for `.git` —
   none above `/usr/local/sbin` → falls back to `$HOME/hermes-cortex`.
3. **sudo's `env_reset` default sets HOME to the TARGET user's home**
   (`/root` when target is root) — `/root/hermes-cortex` doesn't exist →
   returns script_dir → source path is wrong → exit 1.
4. sudo **blocks env overrides entirely**: `sudo -n HOME=/home/moses cmd`
   and `sudo -n CORTEX_REPO=... cmd` both fail with `sorry, you are not
   allowed to set the following environment variables`.

**Fix — argv is the ONLY channel sudo allows:**
```bash
sudo -n "$FIX_SCRIPT" --repo "${CORTEX_REPO}"   # wrapper
def repo_dir(repo_arg=None):                     # script
    for c in (repo_arg, os.environ.get("CORTEX_REPO")):
        if c and os.path.isdir(os.path.join(c, ".git")):
            return c
    ...  # then walk-up, then $HOME fallback
```

**Verify the LIVE artifact, not the pipeline log** — a pipeline reporting
"Committed + Pushed" while the deploy step fails leaves repo ahead of the
running service, and the doctor's `Deploy sync` check does NOT cover
`/usr/local/sbin` copies:
```bash
wc -l ops/install/deploy/nginx/blocked_ips.add   # repo source
grep -c "^deny" /etc/nginx/blocked_ips.conf       # live — mismatch = silent gap
```

**Why only the orchestrator host hit it:** only hosts that installed the
P1-A root-owned copy run the script from `/usr/local/sbin`; hosts using the
repo copy work because the walk-up from inside the repo finds `.git`.

**Why copy, not symlink:** a symlink `/usr/local/sbin/foo.py →
~/hermes-cortex/ops/...` re-opens the root-ACE hole P1-A closed — the repo
copy is user-writable, so an agent could edit it and sudo would execute
arbitrary code as root. The immutable root-owned copy is the point.

**Deploy ≠ refresh:** `cortex-update.sh` does NOT own `/usr/local/sbin`.
After pushing changes to a script with a root-owned immutable copy, the
operator must re-run the dedicated installer (`sudo bash
.../deploy-fix-blocked-ips.sh`) — password-gated by design, agents cannot.

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
1. Check `chattr +i` via `lsattr` — if set → `sudo hermes-plugin-lock unlock --cortex-update`
2. Copy updated files from repo
3. `chmod 444` on `__init__.py`
4. `sudo hermes-plugin-lock lock`

On **macOS**:
1. Check `chflags uchg` via `ls -lO` — if set → `sudo hermes-plugin-lock unlock --cortex-update`
2. Copy updated files from repo  
3. `chmod 444` on `__init__.py`
4. `sudo hermes-plugin-lock lock`

The helper script must handle both platforms transparently.

## Related

- `cortex-update.sh` `deploy_governance_plugin()` — the canonical deploy lifecycle
- `/usr/local/sbin/hermes-plugin-lock` — the restricted sudo helper
- `hermes-cortex-deployment` — full deployment lifecycle for Cortex agents
- `sudoers-audit` — sudoers rule audit and debugging

---

## SOURCE Header Format — Deploy and Doctor Strip Must Agree (2026-08-02)

`cortex-update.sh`'s `copy_file()` adds a SOURCE header to every deployed `.sh`/`.py`.
Since 2026-08-02 the header sits **BELOW the shebang** (a header above it breaks direct
`./script.py` execution — the kernel only honors a shebang at line 1). Deployed layout:

```
#!/usr/bin/env python3
# SOURCE: <repo-path>
# Do NOT edit this file — edit the source above and run: bash cortex-update.sh
(blank)
```

The doctor strips this header in **THREE places** in `ops/scripts/manage/cortex_doctor/checks.py`
(~lines 656, 842, and the `_content_md5()` helper). All three must handle BOTH layouts:
- **New (shebang-first):** keep `lines[0]` (the shebang), drop `lines[1:4]` (SOURCE + Do NOT edit + blank)
- **Legacy (header-first):** drop `lines[0:3]`

**Coordinated-change rule:** when changing the header format in cortex-update.sh, update all
three strip sites in the SAME commit and verify with a one-liner asserting
`strip(new_layout) == strip(legacy_layout) == repo_source_bytes`. Changing only one side makes
every deployed `.sh`/`.py` falsely flag as checksum-mismatched in the doctor. Raw `sha256sum`
comparison against repo will ALWAYS differ for deployed copies (they carry the header) — always
strip via `_content_md5()` first.

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

After every deploy, `cortex-update.sh` now auto-runs
`clean_stale_deploys()`:

1. Builds destinations from MAP entries (same as doctor check)
2. Scans `~/.hermes-cortex/scripts/` for stale files
3. Deletes orphans (respects `--dry-run` for preview)

```bash
bash cortex-update.sh --dry-run  # preview
bash cortex-update.sh            # apply
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
