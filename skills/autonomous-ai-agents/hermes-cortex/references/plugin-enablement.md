# Plugin Enablement Pitfall

## Problem

The `install.sh` script creates the mycortex Hermes plugin files at `~/.hermes/plugins/legacy brain command/` but does NOT enable the plugin. Users will find the plugin shows as "not enabled" when running `hermes plugins list`, and the `/brain` slash command will not work.

## Root Cause

Hermes plugins are opt-in by default. The installer creates the plugin files (`__init__.py` and `plugin.yaml`) but plugin enablement is a separate step that requires user interaction or explicit CLI command.

## Solution

After running `install.sh`, explicitly enable the plugin:

```bash
hermes plugins enable legacy brain command
```

This takes effect on the next Hermes session. The plugin will not work in the current session — user must run `/reset` or restart the CLI.

## Verification

```bash
# Check plugin status
hermes plugins list | grep mycortex
# Should show "enabled" in the Status column

# Test the command in a new Hermes session
/brain what's on my mind?
```

## Full Post-Install Checklist

After running `install.sh`:

1. ✅ Verify Ollama: `curl -s http://127.0.0.1:11434/api/tags`
2. ✅ Verify mycortex: `mycortex --version`
3. ✅ Verify launchd services: `launchctl list | grep -E "(ollama|mycortex)"`
4. ✅ Enable plugin: `hermes plugins enable legacy brain command`
5. ✅ Verify plugin: `hermes plugins list | grep mycortex`
6. ✅ Test in new session: Start new Hermes session and run `/brain test query`

## Related Files

- `~/.hermes/plugins/legacy brain command/__init__.py` — Plugin implementation
- `~/.hermes/plugins/legacy brain command/plugin.yaml` — Plugin configuration
- `~/.hermes/config.yaml` — Hermes config (plugin enablement tracked here)

## Session Evidence

From session 2026-06-04:
- Plugin files existed at `~/.hermes/plugins/legacy brain command/`
- `hermes plugins list` showed status as "not enabled"
- Ran `hermes plugins enable legacy brain command` → "✓ Plugin legacy brain command enabled. Takes effect on next session."
