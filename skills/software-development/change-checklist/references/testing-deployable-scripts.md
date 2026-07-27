# Testing Deployable Scripts

A pattern doc for testing scripts that other agents will deploy and run.

## The Trap: Testing in Isolation

```python
# ❌ WRONG — tested a function import, not the actual command
exec(open('script.py').read().split('def main')[0])
res = Results()
check_nginx(res)
# This passes because:
#   - No argv parsing
#   - No subprocess calls to sudo nginx -t
#   - No PermissionError from Path.exists() on root-owned files
```

The full script has different behavior when run as a command vs imported:
- `Path.exists()` raises `PermissionError` on root-owned files (e.g. Let's Encrypt certs)
- `subprocess.run(["sudo", "nginx", "-t"])` has different output
- `sys.exit()` changes the control flow
- Environment variables and working directory matter

## The Fix: Test the Full Command

```bash
# ✅ RIGHT — run the actual command the agent will use
python3 ops/scripts/manage/cortex-doctor.py --quiet
```

### Why This Matters

| Import test | Full command test |
|---|---|
| No argv parsing | Full argument handling |
| No sys.exit() | Exit codes verified |
| Subprocess calls skipped | Real subprocess behavior |
| Permission errors silent | Real permission checks |
| Single function focus | Full integration |

## Permission-Aware Testing Pattern

When a script reads system files, test as the target user:

```bash
# Test as self (non-root) — catches PermissionError
python3 script.py

# Test with sudo — catches root-only behavior
sudo python3 script.py

# Test with su — target user simulation
su - joseph -c 'python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py'
```

### Common Permission Pitfalls

| Path | Owner | Non-root behavior |
|---|---|---|
| `/etc/letsencrypt/live/*/` | root:root | `PermissionError` on `Path().exists()` |
| `/etc/nginx/*` | root:root | File exists but stat fails |
| `/root/*` | root:root | File exists but stat fails |

### The `_path_ok()` Pattern

Wrap `Path.exists()` in a PermissionError-safe helper:

```python
def _path_ok(p):
    try:
        return Path(p).exists()
    except PermissionError:
        return True  # file exists, just not readable
```

## Testing Patterns by Script Type

### Python scripts
```bash
# Syntax
python3 -c "import py_compile; py_compile.compile('script.py', doraise=True)"

# Run with --help (safest smoke test)
python3 script.py --help

# Run with real args
python3 script.py --json
python3 script.py --quiet

# Full integration test
python3 script.py
```

### Shell scripts
```bash
# Syntax
bash -n script.sh

# Dry run (if supported)
bash script.sh --dry-run

# Full run (may need sudo)
sudo bash script.sh
```

### Config generators
```bash
# Generate config
bash cortex-update.sh

# Diff against deployed
diff /tmp/hermes-services-processed.conf /etc/nginx/sites-available/hermes-services.conf

# Validate
sudo nginx -t
```

## Verification Checklist

- [ ] Script runs without errors as a normal user
- [ ] Script runs without errors as root (if applicable)
- [ ] Output is correct (not garbled, paths are valid)
- [ ] Filesystem side-effects are correct (files created/deleted in right places)
- [ ] Exit codes are correct (0 = success, non-zero = failure)
- [ ] Doctor passes after the change: `python3 cortex-doctor.py --quiet`
- [ ] Other agents can run it without modifications
- [ ] Works on both Linux and macOS (if applicable)
