# pgrep Flags: Exact vs Full Command Matching

## The Flags

| Flag | Meaning | Example match |
|------|---------|---------------|
| `-x` | Exact process name (or exact command with `-f`) | Matches if the process name / full command equals the pattern exactly |
| `-f` | Match against full command line (including args) | Matches if the full command contains the pattern as a substring |
| `-x -f` | **EXACT full command match** | Matches only if the ENTIRE command line equals the pattern — NOT a substring match |

## Common Pattern: `-x` alone

```bash
pgrep -x nginx
# Matches process whose NAME is exactly "nginx"
# ✅ /usr/sbin/nginx -g daemon on; master_process on;  (process name = nginx)
```

## Common Pattern: `-f` alone

```bash
pgrep -f "gateway run"
# Matches any process whose FULL COMMAND LINE contains "gateway run"
# ✅ /home/.../python -m hermes_cli.main gateway run
```

## Tricky Case: `-x -f` combined

```bash
pgrep -x -f "gateway run"
# Matches ONLY if the FULL COMMAND LINE equals "gateway run" exactly
# ❌ /home/.../python -m hermes_cli.main gateway run  (too long)
# Does NOT match even though -f would match and -x would match alone
```

## How This Relates to the `_pgrep()` Helper

```python
def _pgrep(pattern, exact=True, full=False):
    args = ["pgrep"]
    if exact:
        args += ["-x"]      # exact process name
    if full:
        args += ["-f"]      # full command line substring
    args.append(pattern)
```

**Correct calls:**

| Goal | Call | Resulting command |
|------|------|------------------|
| Match exact process name | `_pgrep("nginx")` | `pgrep -x nginx` |
| Match full command substring | `_pgrep("gateway run", exact=False, full=True)` | `pgrep -f "gateway run"` |
| Match exact process by full command | `_pgrep("python", full=True)` | `pgrep -x -f python` (rarely useful) |

**Wrong call that looks right:**

```python
_pgrep("gateway run", full=True)  
# DEFAULT: exact=True AND full=True
# Produces: pgrep -x -f "gateway run"
# This is an EXACT full-command-line match, not a substring match!
```