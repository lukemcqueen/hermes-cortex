---
name: mcp-health-monitoring
description: "Probe MCP server health; extend the governance watchdog."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [mcp, health, watchdog, governance, monitoring, probe]
    related_skills: [mcp-server-building, fleet-commands, cron-job-management]
---

# MCP Health Monitoring

Detect and diagnose MCP server outages — the class that silently
write-deadlocked the fleet on 2026-08-18 (mcp SDK 2.0 removed the decorator
API; all three cortex servers crashed at import, sessions lost loop-governance
tools, and the enforcer blocked every write because the lock tool lived in the
dead server). The core lesson: **an MCP outage that goes unnoticed is a fleet
outage; the probe below catches the failure class in seconds.**

## When to Use

- MCP tools missing from a session's schema ("governance tools aren't exposed")
- Extending or tuning the fleet's MCP health watchdog
- Writing any health probe / smoke test for an MCP server
- Diagnosing a write-deadlock or "ALL WRITES BLOCKED" state
- Verifying a new MCP server works before registering it

## The Fleet Watchdog (already deployed — extend, don't duplicate)

`agent-mcp-health-watchdog` (no_agent cron, every 5 min, source
`ops/scripts/health/agent-mcp-health-watchdog.py`) probes **every configured
server** in `~/.hermes/config.yaml`:

- Spawns each server's configured python → import → `list_tools` → verifies
  required tool names present
- **Binary-CLI servers** (args[0] is a subcommand, not a file — e.g.
  `tirith mcp-server`) get a REAL stdio `initialize` handshake instead;
  `tools/list` is probed opportunistically (resource-only servers that reject
  it with -32601 still pass — the handshake is the health signal)
- Scans `~/.hermes/logs/mcp-stderr*.log` for import-crash signatures
  (watermark-based, catches the 2026-08-18 class on first fresh hit)
- **Severity:** loop-governance / tasks down → CRITICAL "⚠️ GOVERNANCE OFFLINE —
  ALL WRITES BLOCKED" (write-deadlock risk); agent-bus (a.k.a. cortex-bus) down
  → WARNING (no deadlock); unknown servers probed generically at WARNING
- **Strike logic:** 2 consecutive probe failures to alert (transient tolerance),
  hourly re-alert cap, "✅ MCP server recovered" notice when a server passes
  again. State: `~/.hermes-cortex/state/mcp-health-state.json`
- **Read-only, lock-free** — it keeps screaming while every session is
  deadlocked, which is exactly when it matters
- Delivers to Telegram home channel; silent when healthy (no_agent watchdog)

**Extending:** add the new server's config key to the `EXPECTED_TOOLS` map with
its severity + required tool names. Servers without a map entry are still
probed (WARNING, non-empty tool list required).

## Probe Recipe (canonical health check)

Catches the real failure class (import crash → no tools) without a full stdio
handshake. Runnable helper: `scripts/mcp-probe.py <server_path>` — invoke it
with the server's OWN python:

```bash
"$SERVER_PYTHON" "$HOME/.hermes/skills/devops/mcp-health-monitoring/scripts/mcp-probe.py" /path/to/server.py
# prints ["tool1","tool2",...] on success; exits non-zero with traceback on crash
```

Requires the server to expose module-level `async def list_tools(ctx,
params=None)` (the mcp 2.0 constructor-API shape) and guard `main()` behind
`if __name__ == "__main__":` so import never starts the stdio server.

The fleet watchdog dispatches automatically: python-script servers use this
import probe; binary-CLI servers (`command` is an executable and `args[0]` is
a subcommand, not a `.py` file) fall back to a real stdio initialize
handshake (`tests/test_mcp_health_watchdog.py` proves both paths — run it
after any probe change).

## Client-Side MCP Outage — OTel namespace-package version skew

**Symptom:** EVERY MCP tool call fails on one host with
`AttributeError: type object 'TraceFlags' has no attribute 'RANDOM_TRACE_ID'` (and the
langfuse `pre_api_request` hook logs `'TraceFlags' object has no attribute
'random_trace_id'`), while `hermes mcp list` shows every server enabled and the
servers' own `mcp-stderr.log` is clean. The MCP *servers* are healthy — the *client*
runtime is broken, so the per-server watchdog (which probes servers) stays green
through this class.

**Cause:** `opentelemetry` is a PEP 420 namespace package, so two site-packages on one
`sys.path` are MERGED rather than shadowed: the env venv's `opentelemetry.trace`
(e.g. api 1.39.1, pulled in by `mcp>=2.0`) answers while a newer tree's
`opentelemetry.sdk` (e.g. 1.45.0, pulled in with the Langfuse Observability plugin —
`langfuse>=4.16` requires `opentelemetry-api>=1.45`) supplies the span code. The older
`TraceFlags` has no `RANDOM_TRACE_ID`, so every span creation raises; `mcp` 2.x wraps
every `tools/call` in a span, so all MCP tools die at once.

**Diagnose (5 min):** list the otel installs on the whole runtime path, not just the
venv — `ls -d <venv>/lib/python*/site-packages/opentelemetry* <shared tools
python>/lib/python*/site-packages/opentelemetry*`. Confirm the merge with
`python3 -c "import opentelemetry; print(opentelemetry.__file__, list(opentelemetry.__path__))"`
(`__file__ is None` = namespace merge across portions) and
`python3 -c "import opentelemetry.trace as t; print(t.__file__, [a for a in dir(t.TraceFlags) if a.isupper()])"`
(only `['DEFAULT','SAMPLED']` = the too-old api). **Repro harness:** append the other
site-packages to `sys.path` AFTER the venv, `set_tracer_provider(TracerProvider())`,
then enter `mcp.shared._otel.otel_span("x", kind=SpanKind.CLIENT)` — it raises the exact
AttributeError. Static grep cannot find the culprit: the symbol exists only in the newer
tree, never in the failing environment.

**Fix:** align the versions — `uv pip install --python <venv>/bin/python3
"opentelemetry-api==<the sdk's version>"` (safe: `mcp` only needs
`opentelemetry-api>=1.28`). Verify with the repro (`SPAN OK`), a real
`mcp.client.stdio.stdio_client` `tools/call` against the server, then a live
`hermes -z` session calling the tool. A plain `hermes pm sync` can re-resolve the venv
back to the pinned older api and re-break it — the durable fix is upstream (plugin
installs must not skew otel across site-packages on one `sys.path`); re-pinning locally
is interim only.

**Ready-made tools:** `scripts/otel-version-skew-probe.py` runs the whole check on the
current interpreter (portions, both versions, `TraceFlags` members; exit 1 = skew) and
prints the align command — run it with the venv/interpreter that serves the MCP client.
This class is no longer doc-only: `agent-mcp-health-watchdog.py` runs the probe every
5 min under each agent-runtime interpreter (`~/.hermes-cortex/venv`, then
`~/.hermes/hermes-agent/venv`, then
`~/.hermes/installs/*/environments/*/venv`, bounded to 4) and raises **GOVERNANCE
OFFLINE — ALL WRITES BLOCKED** after 2 consecutive fails, with the align command, then
a `✅ otel runtime recovered` notice once the pair agrees again (no probe on the host ⇒
an "UNVERIFIED" warning, never silence). That is the check the per-server probes above
cannot give you: they stay green throughout this class.
The captured diagnosis, repro and three-layer verification for the 2026-10-06 moses
incident are in `references/otel-skew-incident-2026-10-06.md`.

## Pitfalls

- **HOME/cwd sensitivity (false negatives):** servers resolve `~/hermes-*`
  paths via `Path.home()` at import. Probing under a different HOME or a bare
  subprocess env fails with `ModuleNotFoundError: No module named
  'hermes_models'` while the server is perfectly healthy. Run probes with the
  user's real HOME and `cwd=HOME` to mirror the gateway's spawn environment.
- **Watermark must persist on first sight:** `offset = offsets.get(path, size)`
  then `if size == offset: continue` never stores the offset → the scan
  re-initializes every run and never fires. Correct: `offset = offsets.get(path);
  if offset is None: offsets[path] = size; continue`.
- **Verify tool NAMES, not "spawned ok":** a server can import cleanly yet lack
  enforcement-critical tools. Check the required-name list (e.g. for
  loop-governance: `begin_change`, `end_change`, `check_lock`).
- **Config key ≠ canonical name:** live config uses `agent-bus` while the
  doctor's expected list uses `cortex-bus`; the doctor's "configured" check
  passes via the args path, not the key. Parse the LIVE config for probes.
- **args[0] may be a subcommand, not a script (false-positive loop, 2026-08-18):**
  binary-CLI servers (e.g. `tirith mcp-server`, `python -m module`) have a
  non-`.py` args[0] — treating it as a script path failed with
  `script not found: mcp-server` every 5 min and alerted hourly while the
  server was perfectly healthy. The dispatcher now routes non-`.py` args to a
  real stdio handshake. Never `os.path.exists(args[0])` as the sole check.
- **Resource-only servers must pass the stdio probe:** `tools/list` errors
  (-32601) are normal for them; the initialize handshake (serverInfo) is the
  health signal. Don't fail a server whose tools/list is unsupported.
- **Respect `enabled: false`** and only probe servers actually configured on
  that host (loop-governance is orchestrator-only — a non-orchestrator without
  it must NOT false-CRITICAL).
- **Log-rotation:** a rotated/shrunk mcp-stderr log resets the watermark
  without alerting — the probes cover the gap.

## Fail-Loud Design Principles (from the 2026-08-18 party)

- **Detect first, prevent second.** A watchdog that proves "governance is
  alive" every 5 min is the highest-value change; update-path pre-flight is the
  second layer. See `docs/elicit/2026-08-18_governance-fail-loudly-party.md`.
- **Gateway restart does NOT recover an import-crash class.** MCP servers spawn
  per gateway; a deterministic import crash respawns identically. Recovery
  requires code fix → deploy → restart. Auto-restart only helps transient
  spawn failures — don't build it as the first-line mechanism.
- **2-strike + cooldown:** alert on the 2nd consecutive failure, re-alert at
  most hourly — loud without alert storms (288/day is noise, not alarm).
- **Read-only watchdog:** the probe must never need a governance lock, or it
  dies in the exact deadlock it exists to report.

## Verification

- Healthy config → watchdog exits 0 with empty output (silent)
- Fault injection: point a test config at a server using the removed decorator
  API → 2nd run emits the CRITICAL alert with the actual `AttributeError`
- Append a crash signature line to a fresh mcp-stderr log → immediate alert
- Fix the server → next run emits the RECOVERED notice
- Test with fake HOME to prove the probe's HOME-sensitivity is handled
