# Example: Cross-platform service management in gbrain-wrapper.sh

This is the concrete implementation of Pattern F (boolean dispatch helpers) from the main SKILL.md.

## Source file

`ops/scripts/manage/gbrain-wrapper.sh` in the hermes-cortex repo.

## Architecture

1. **OS detection** (top): sets `$IS_MAC` / `$IS_LINUX` once via `uname -s`
2. **Service name mapping**: `gbrain-autopilot` (Linux) vs `com.gbrain.autopilot` (macOS)
3. **3 helper functions**: `_service_is_active`, `_service_stop`, `_service_start` — each dispatches internally
4. **Clean business logic**: calls helpers, never branches by OS

## Key design choices

| Decision | Why |
|----------|-----|
| Separate helper per operation | Callers read `_service_stop "$SERVICE"` — intention is clear, implementation is encapsulated |
| Boolean booleans ($IS_MAC, $IS_LINUX) | Cleaner than `if [[ "$(uname -s)" == "Darwin" ]];` repeated 6x |
| Function-local `local name="$1"` | Prevents variable leakage from one helper to another |
| `|| true` on stop/start | These are best-effort (service may not exist); business logic shouldn't fail on cleanup |
| `|| return 1` on get | Active check needs a definitive yes/no for the calling logic to branch on |

## What to change for a different service

Replace the `SERVICE_NAME` variable and update the `systemctl` unit name / `launchctl` label. The helper functions work for any user-scoped service.
