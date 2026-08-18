# Worked example: agent_bus → cortex_bus fleet rename verification (2026-08-04)

A fleet-wide bus rename (package `agent_bus` → `cortex_bus`, server restore,
schema migration, 85 files, 5 skill dirs, 4 crons, installers, doctor, nginx
upstream, both hosts' config.yaml) was committed and deployed, then reported as
"one bus, one name, zero confusion left". A follow-up verification pass found
two of the four "renamed" surfaces still old.

## What verification surfaced

| Surface | Esther host (:14004) | Moses host (:13004) |
|---|---|---|
| Bus daemon | ✅ `uvicorn cortex_bus.server:app`, started 18:48 | ✅ `uvicorn cortex_bus.server:app`, started 18:51 |
| Enforcer plugin (mtime) | 18:57 | 18:59 |
| Gateway `lstart` | 19:02 (AFTER deploy → new code loaded) | 17:41 (BEFORE deploy → OLD code in memory) |
| MCP child argv (`mcp_stdio_watchdog`) | ✅ `cortex-bus-mcp.py` | ❌ `agent-bus-mcp.py` + old loop-gov path |
| config.yaml MCP key | ❌ still `agent-bus:` (line 201) → tools `mcp__agent_bus__*` | updated path, key check pending |

- **Esther:** gateway restarted after the deploy → new enforcer + new MCP path
  live. But the config KEY was still `agent-bus`, so tools exposed
  `mcp__agent_bus__*` while the renamed skills reference `mcp__cortex_bus__*`.
- **Moses:** gateway started 17:41, deploy landed ~18:51–18:59 → children still
  spawned the old `agent-bus-mcp.py`; config on disk already pointed at
  `cortex-bus-mcp.py` but was not loaded. Restart required.

## Commands that produced the evidence

```bash
ps -eo pid,lstart,cmd | grep 'hermes_cli.main gateway' | grep -v grep
ps -eo pid,lstart,cmd | grep mcp_stdio_watchdog | grep -v grep
stat -c '%y %n' ~/.hermes/plugins/governance-enforcer/__init__.py ~/.hermes/config.yaml
grep -n -iE 'agent-bus|cortex-bus' ~/.hermes/config.yaml   # HYPHENS, not underscores
```

Note the grep trap: `grep -iE 'agent_bus|cortex_bus'` matched NOTHING in
config.yaml because config keys are hyphenated (`agent-bus:`) — the underscore
pattern only matches Python package names. The initial grep only looked
"successful" because the `mcp`/`enforcer` keywords matched other lines.

## Secondary symptom: script config-path drift

`report-agent-health.py` (no_agent watchdog deployed fleet-wide) read
`CONFIG_FILE = ~/.hermes/cortex-bus.conf` — a path retired when bus config was
standardized at `~/.hermes-cortex/cortex-bus.conf` (commit `d2fd304d`). Result:
exit 1 with `ERROR: CORTEX_BUS_FALLBACK_URL (or CORTEX_INBOX_URL) not set`,
even though the canonical conf existed with the right values. When touching any
bus script, grep for the retired path first:

```bash
grep -rn "\.hermes/cortex-bus.conf" ~/hermes-cortex/ops/scripts/
```

## Lesson

The migration had 3 pushed commits + an "all renamed" claim, but the live
config key and one script's config path were still old. The only signal that
"everything renamed" was overstated came from the file-mutation verifier
flagging the refused config.yaml patch. Four surfaces, four checks: **repo
strings, config key, deployed script paths, running process argv.**

Related: the config.yaml direct-patch refusal ("Agent cannot modify
security-sensitive configuration") means MCP/plugin config changes go through
`hermes config set/unset` or a user edit — not patch/write_file.
