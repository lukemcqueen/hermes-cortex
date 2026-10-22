# gbrain Migration Recovery

When gbrain migrations wedge — typically after 3+ consecutive partial attempts at the same version — the system enters a degraded state that affects both the sensor's health checks and LLM-driven cron outputs.

## Detection

```bash
gbrain doctor --fast
```

Look for:
```
[FAIL] minions_migration → WEDGED MIGRATION(s): <version>
```

The version string looks like `0.32.2` — a semantic semver migration label.

The overall health score drops significantly (e.g. 70/100 instead of 90+/100).

## Recovery

### Step 1: Force-retry the wedged migration

```bash
gbrain apply-migrations --force-retry <version>
```

This writes a "retry" marker for that version.

### Step 2: Re-attempt

```bash
gbrain apply-migrations --yes
```

The migration runs and completes. Verify with `gbrain doctor --fast` — the `[FAIL]` entry should be gone.

### Step 3: Fix sync failures (if present)

If the migration wedge also caused sync failures:

```bash
gbrain sync --skip-failed
```

This acknowledges stale sync failures and gets sync back on track.

## Verification

```bash
gbrain doctor --fast | grep -E "FAIL|Overall"
```

Expected:
- No `[FAIL]` lines (only `[WARN]` is acceptable)
- `Overall health score: 90/100` or better

## Pitfalls

- **Do not skip the `--force-retry` step.** Running `gbrain apply-migrations --yes` on a wedged migration without force-retrying first will fail silently — the wedge marker prevents re-attempt.
- **Sync failures after migration.** The migration may have been in progress when sync tried to run, leaving stale sync failure records. `gbrain sync --skip-failed` is safe — it only acknowledges the failure, it doesn't skip future syncs.
- **MacOS vs Linux.** On macOS, gbrain runs as a launchd agent (`com.gbrain.autopilot`). On Linux, as a systemd user service (`gbrain-autopilot.service`). Migration recovery is the same regardless.
