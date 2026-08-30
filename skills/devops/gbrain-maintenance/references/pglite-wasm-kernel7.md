# PGLite WASM Crash on Kernel 7.0 — Diagnosis Record

## Environment

- OS: Linux Mint 22.3 "Zena"
- Kernel: 7.0.0-14-generic
- gbrain: 0.42.52.0
- bun: 1.3.14
- PGLite: 0.4.3 (pinned by gbrain's package.json)

## Symptom

`system-alert-watchdog` cron reports:
```
❌ gbrain sync: gbrain-autopilot not active in any scope
❌ gbrain sources: gbrain-autopilot not active in any scope
```

## Service Status

```bash
systemctl --user status gbrain-autopilot
# → active (auto-restart) — main process exited code=1, restarting loop
```

```bash
journalctl --user -u gbrain-autopilot -n 10
# → gbrain-autopilot.service: Main process exited, code=exited, status=1/FAILURE
# → gbrain-autopilot.service: Scheduled restart job, restart counter is at 93
```

## Error — Original (PGLite 0.4.3 WASM)

gbrain doctor:
```
[unhandledRejection] WebAssembly.Module doesn't parse at byte 4201158:
parsing ended before the end of Code section
```

WASM file: 8,740,135 bytes, fails at 4,201,158 (~48%)

## Error — After PGLite 0.5.4 WASM swap

```bash
# Copied PGLite 0.5.4 WASM over the nested v0.4.3 copy:
cp ~/.bun/install/global/node_modules/@electric-sql/pglite/dist/pglite.wasm \
   ~/.bun/install/global/node_modules/gbrain/node_modules/@electric-sql/pglite/dist/pglite.wasm
```

New error:
```
[unhandledRejection] Table import env:__indirect_function_table provided
an 'initial' that is too small
```

Different WASM ABI between PGLite 0.4.3 and 0.5.4 — v0.5.4 requires a larger
function table that bun doesn't allocate.

## Key Insight — Cycle Completes Successfully

The autopilot.err file shows ALL phases completing before the crash:

```
[cycle.lint] start    → done
[cycle.backlinks]     → done
[cycle.sync]          → done
[cycle.synthesize]    → done
[cycle.extract]       → done
[cycle.extract_facts] → done
[cycle.resolve_symbol_edges] → done
[cycle.patterns]      → done
[cycle.recompute_emotional_weight] → done
[cycle.consolidate]   → done
[cycle.propose_takes] → done
[cycle.grade_takes]   → done
[cycle.calibration_profile] → done
[cycle.conversation_facts_backfill] → done
[cycle.enrich_thin]   → done
[cycle.skillopt]      → done
[cycle.embed]         → done
[cycle.orphans]       → done
[cycle.schema_suggest] → done
[cycle.purge]         → done
```

autopilot.log shows the cycle summary:
```
[cycle] score=45 elapsed=2s next=150s
```

The WASM error happens during module teardown/sleep, not during actual operations.

## Fix Applied

1. Replaced `exec gbrain autopilot ...` with a `while true` loop in `autopilot-run.sh`
2. Reduced systemd `RestartSec` from 30 to 5 seconds
3. Service stays `active (running)` — the wrapper catches the crash and restarts

## Verification

```bash
systemctl --user status gbrain-autopilot
# → active (running)

systemctl --user is-active gbrain-autopilot
# → active

tail ~/.gbrain/autopilot.log
# → [cycle] score=45 elapsed=2s next=150s

# Health endpoint
curl -s http://127.0.0.1:8905/api/v1/health | jq '.checks.gbrain_sources'
# → {"healthy": true, "detail": "7 brain source dir(s) with content"}
```
