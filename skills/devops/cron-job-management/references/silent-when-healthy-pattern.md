# Silent-When-Healthy Pattern for no_agent Crons

A cron that only delivers output on failure, staying completely silent when healthy.

## The Problem

A no_agent cron runs a script every tick. If the script always prints status (even on success), every tick delivers a message — noisy, costly, and defeats the watchdog pattern.

## The Pattern

**Script outputs nothing on success → cron delivers nothing. Script outputs errors on failure → cron delivers the error.**

### Implementation

1. **Use `--quiet` flag** in the script that suppresses all success output
2. **Wrap the cron call** in a thin shell wrapper that redirects stderr to stdout (`2>&1`)
3. **Set cron `deliver=origin`** so output reaches the user

```bash
#!/usr/bin/env bash
# model-health-watchdog-cron.sh
exec python3 ~/.hermes/scripts/model-health-watchdog.py --quiet 2>&1
```

### Why `2>&1` is critical

For no_agent crons, the scheduler captures **stdout only**. If your script outputs errors to stderr (via `print(..., file=sys.stderr)`), they're silently lost. The `2>&1` in the wrapper merges stderr into stdout so failure output reaches the delivery channel.

### The script's contract

| Exit code | Stdout | Cron behavior |
|-----------|--------|---------------|
| 0 | Empty | Silent — no delivery |
| 1+ | Error text | Delivered to user |
| 1+ | Empty | Exit code logged, nothing delivered (rare — error text should always accompany non-zero exit) |

### Real example: model-health-watchdog

The Python script (`model-health-watchdog.py`) already had `--quiet` support:

```python
def main():
    quiet = "--quiet" in sys.argv
    # ...
    if not quiet:
        print(f"Checking Ollama...")
    # On failure, ALWAYS prints (regardless of --quiet):
    print(f"❌ Model missing — install with: ollama pull {model}")
    sys.exit(1)
```

The cron wrapper adds `2>&1`, and the job definition is:

| Field | Value |
|-------|-------|
| `script` | `model-health-watchdog-cron.sh` |
| `no_agent` | `true` |
| `deliver` | `origin` |

### When to use

- **Watchdog-style crons** — periodic health checks that should only alert on failure
- **Sensor crons** — file checks, API pings, service reachability
- **Pull-and-check crons** — git pull + verify nothing changed (silent if nothing new)

### When NOT to use

- **Data-reporting crons** — user expects a daily summary even if nothing changed
- **Audit crons** — user wants to confirm the cron actually ran (a daily delivery is proof of life)
- **Critical crons** — if a cron goes silent and the user can't tell if it's healthy or dead, a heartbeat delivery is safer

---

## LLM-Driven Crons — Same Pattern, Different Mechanism

LLM-driven crons (where the agent runs a prompt each tick, not a script) should also follow silent-when-healthy: **produce no output when there's nothing to report.**

### How it works

| Cron behavior | Output | Delivery |
|--------------|--------|----------|
| All clear — nothing actionable | Empty string or `[SILENT]` | Nothing delivered |
| Found issues to report | Summary of findings | Delivered to user |

### Implementation

Add this instruction at the end of the cron's prompt:

```
SILENT WHEN HEALTHY: Produce NO output when everything is clean. No all-clear summaries,
no "nothing to report" messages, no tables of zero counts. Only deliver output when you
find something actionable — failed workflows, stuck messages, blocked items, or critical
alerts. If all you did was archive routine health pings, stay silent.
```

### Real examples on this server

| Cron | Prompt instruction |
|------|-------------------|
| `cortex-bus-workday` | SILENT WHEN HEALTHY — only speaks on actionable bus items |
| `cortex-bus-evening` | Same |
| `cortex-bus-overnight` | Same |

### Same contract as no_agent scripts

| Agent produces | Cron behavior |
|---------------|---------------|
| Empty output | Silent — nothing delivered |
| Error/finding text | Delivered to user |
| Table of zero counts | **Still delivered** — don't do this |
