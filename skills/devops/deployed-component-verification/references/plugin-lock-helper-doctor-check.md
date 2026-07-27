# Plugin Lock Helper Doctor Check — July 27, 2026

## Context

The `hermes-plugin-lock` restricted helper script is deployed to
`/usr/local/sbin/hermes-plugin-lock` by `cortex-update.sh`'s
`deploy_system_scripts()` function. It enables the governance enforcer
plugin's immutability lifecycle (lock/unlock via `chattr +i` on Linux,
`chflags uchg` on macOS).

The doctor had no check for this helper — it checked the *symptom*
(immutable flag not set on enforcement files) but never the *cause*
(missing helper or sudoers entry).

## Implementation

Added `_check_plugin_lock_helper()` to `cortex_doctor/checks.py` and
called it from `check_governance()` right after
`_check_enforcer_immutability()`.

### Design

Single function, three states:

1. **Binary missing** → FAIL with deploy instructions, return early
2. **Binary not executable** → FAIL with chmod fix, return early
3. **`sudo -n hermes-plugin-lock status` fails** → FAIL with sudoers fix
4. **Everything works** → PASS

Key insight: `sudo -n` functional test IS the sudoers proof. Cannot
read `/etc/sudoers.d/` files as non-root (they're `r--r-----` root:root).

### The Check

```python
def _check_plugin_lock_helper(res):
    """Check that the plugin lock helper (hermes-plugin-lock) is deployed and functional."""
    helper_path = Path("/usr/local/sbin/hermes-plugin-lock")

    if not helper_path.exists():
        res.add("Plugin lock helper", "FAIL",
                "hermes-plugin-lock not found at /usr/local/sbin",
                "Run: sudo cortex-update.sh or deploy manually from the repo")
        return
    if not os.access(str(helper_path), os.X_OK):
        res.add("Plugin lock helper", "FAIL",
                "hermes-plugin-lock exists but is not executable",
                f"Fix: sudo chmod 755 {helper_path}")
        return

    try:
        result = subprocess.run(
            ["sudo", "-n", str(helper_path), "status"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            res.add("Plugin lock helper", "PASS",
                    f"helper + sudoers OK ({result.stdout.strip()[:60]})")
        else:
            res.add("Plugin lock helper", "FAIL",
                    f"sudo -n hermes-plugin-lock status exited "
                    f"{result.returncode}: {result.stderr.strip()[:60]}",
                    "Check sudoers entry: echo 'moses ALL=(root) NOPASSWD: "
                    "/usr/local/sbin/hermes-plugin-lock' | sudo tee "
                    "/etc/sudoers.d/hermes")
    except (subprocess.TimeoutExpired, OSError) as e:
        res.add("Plugin lock helper", "FAIL",
                f"sudo -n hermes-plugin-lock status failed: {e}",
                "Check sudoers entry and helper binary")
```

### Invocation Point

Inserted at `cortex_doctor/checks.py` in `check_governance()`:

```python
# ── Immutability (chattr +i) checks ──
_check_enforcer_immutability(res, plugin_dir, hooks_dir)

# ── Plugin lock helper (hermes-plugin-lock) ──
_check_plugin_lock_helper(res)

# ── Governance bypass coverage ──
```

### Sudoers File Naming

The warning in `cortex-update.sh` previously said to create
`/etc/sudoers.d/hermes-plugin-lock`. This was wrong — the convention
is `/etc/sudoers.d/hermes` (a single multi-rule file). Fixed the
warning path in the same commit.

### Related Files

- `cortex_doctor/checks.py` — `_check_plugin_lock_helper()` function
- `cortex_doctor/checks.py` — `check_governance()` invocation
- `cortex-update.sh` — deploy warning (line 1154)
- `ops/install/deploy/nginx/hermes-plugin-lock` — the helper script

### Verification

```bash
# Run the check
python3 cortex-doctor.py | grep "Plugin lock"

# Expected output when working:
# ✅ Plugin lock helper — helper + sudoers OK (----i---------e------- ...)

# Expected output when missing:
# ❌ Plugin lock helper — ... not found ...
```
