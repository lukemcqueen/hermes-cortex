# Uninstalled Service Detection (0 vs -1)

## Problem

Health check functions that only probe for a running process return `-1`
when the process isn't found — even if the binary **doesn't exist** on
that machine. This conflates two states:

| State | Should return | Previously returned |
|-------|---------------|-------------------|
| Binary exists, process running | `1` | `1` ✅ |
| Binary exists, process not running | `-1` | `-1` ✅ |
| Binary **not installed** | `0` (n/a) | `-1` ❌ (misleading) |

## Fix: `shutil.which()` guard

Add a binary-existence check at the top of each per-service function:

```python
def check_nginx() -> int:
    """nginx: 1 = running, 0 = not installed, -1 = installed but down."""
    if not shutil.which("nginx"):
        return 0  # not installed on this system
    if _pgrep("nginx"):
        return 1
    return -1
```

## Services updated

| Function | Binary check | Signals "installed" |
|----------|-------------|---------------------|
| `check_nginx()` | `shutil.which("nginx")` | Binary in PATH |
| `check_ollama()` | `shutil.which("ollama")` | Binary in PATH |
| `check_gbrain()` | `shutil.which("gbrain")` | Binary in PATH |
| `check_gbrain_sources_ok()` | `shutil.which("gbrain")` | Binary in PATH (shared with check_gbrain) |
| `check_services()` | Systemd unit existence (Linux) / pgrep (macOS) | At least one of nginx/ollama/gbrain installed |

## Context: the three-state contract

The health vector formally supports three states:

| Value | Meaning | Icon |
|-------|---------|------|
| `1` | Running / healthy | ✅ |
| `0` | Not applicable / not installed | ➖ (dash) |
| `-1` | Installed but down / unhealthy | ❌ |

The `0` state lets downstream tooling (orch-health-report, Telegram dashboards)
distinguish "this server doesn't have nginx" from "nginx is installed but crashed" —
reducing false alerts on heterogeneous agents (macOS dev boxes, minions, Docker-only hosts).
