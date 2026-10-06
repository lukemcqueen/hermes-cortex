# Incident evidence — client-side OTel namespace skew, host `moses` (2026-10-05 → 2026-10-06)

Captured output from the diagnosis, the fix, and the verification. Hosts, ports and
paths are as observed; nothing here is reconstructed from memory.

## 1. Symptom (real log lines, `~/.hermes/logs/errors.log`)

```
2026-10-06 08:25:09 ERROR tools.mcp_tool: MCP tool loop-governance/cache_search call failed:
  type object 'TraceFlags' has no attribute 'RANDOM_TRACE_ID'
2026-10-06 08:25:28 ERROR tools.mcp_tool: MCP tool cortex-bus/inbox_read call failed:
  type object 'TraceFlags' has no attribute 'RANDOM_TRACE_ID'
2026-10-06 09:22:49 WARNING hermes_cli.plugins: Hook 'pre_api_request' callback on_pre_llm_request raised:
  'TraceFlags' object has no attribute 'random_trace_id'
```

`hermes mcp list` showed every server `✓ enabled`; the servers' own `mcp-stderr.log`
contained no `TraceFlags` line — the servers were healthy and the *client* was broken.
71 pre-fix occurrences; first failure 2026-10-05 14:23, i.e. ~100 minutes after the
langfuse install below.

## 2. Two otel trees on one runtime path

```
# env venv (the runtime that failed)
opentelemetry_api-1.39.1.dist-info          # required by mcp 2.0.0 (Requires-Dist: opentelemetry-api>=1.28.0)
# shared tools-python site-packages, mtimes 2026-10-05 12:44
langfuse-4.16.0.dist-info                   # Requires-Dist: opentelemetry-api>=1.45.0,<2
opentelemetry_sdk-1.45.0.dist-info
opentelemetry_exporter_otlp_proto_http-1.45.0.dist-info
```

`opentelemetry` has no `__init__.py` in either tree — it is a PEP 420 namespace
package, so the two portions MERGE:

```
$ <env-venv>/bin/python3 -c "import opentelemetry; print(opentelemetry.__file__, list(opentelemetry.__path__))"
None ['…/installs/<id>/environments/<id>/venv/lib/python3.14/site-packages/opentelemetry',
      '…/.hermes/tools/python-3.14.7…/lib/python3.14/site-packages/opentelemetry']
```

## 3. Repro (fails before the fix, passes after)

```python
# append the other site-packages AFTER the venv (its portion then wins for `trace`)
import sys, glob
sys.path.append(glob.glob("/home/<user>/.hermes/tools/python-3.14*/lib/python3.14/site-packages")[0])
import opentelemetry.trace as t
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import set_tracer_provider, SpanKind
set_tracer_provider(TracerProvider())
from mcp.shared._otel import otel_span
with otel_span("tools/call cache_search", kind=SpanKind.CLIENT):
    pass
```

Before (captured):

```
trace module:  …/venv/lib/python3.14/site-packages/opentelemetry/trace/__init__.py
TraceFlags attrs: ['DEFAULT', 'SAMPLED']
sdk module:    …/.hermes/tools/python-3.14.7…/site-packages/opentelemetry/sdk/trace/__init__.py
  File "…/site-packages/opentelemetry/sdk/trace/__init__.py", line 1185, in start_span
    trace_flags = trace_api.TraceFlags(trace_flags | trace_api.TraceFlags.RANDOM_TRACE_ID)
AttributeError: type object 'TraceFlags' has no attribute 'RANDOM_TRACE_ID'
```

After the fix (same harness): `TraceFlags attrs: ['DEFAULT', 'RANDOM_TRACE_ID', 'SAMPLED']` → `SPAN OK`.

## 4. Fix applied (one command, host-local)

```
uv pip install --python <env-venv>/bin/python3 "opentelemetry-api==1.45.0"
  - opentelemetry-api==1.39.1
  + opentelemetry-api==1.45.0
```

Safe because `mcp` needs only `opentelemetry-api>=1.28.0`; aligning at the sdk's
version also satisfies `langfuse>=4.16` (`>=1.45.0,<2`).

## 5. Verification (three layers, real output)

1. Repro harness → `SPAN OK` (above).
2. Real MCP round trip, `mcp.client.stdio.stdio_client` against the live server:

```
REAL MCP: tools registered = 17
REAL MCP check_lock -> {
  "active": false,
  "lock": null
}
```

3. Live agent session on the host (`hermes -z "Call the tool mcp__loop_governance__cache_search …"`):

```
{"result": "[{\"id\": 82, \"source\": \"skill\", \"source_id\": \"verification-evidence\", …
```

No `TraceFlags` line in `errors.log` after 2026-10-06 09:25 (the last pre-fix entry);
the live session at 09:57 logged none.

## 6. Why it is not durable by itself


The repo pins the otlp extra (`opentelemetry-sdk==1.39.1`,
`opentelemetry-exporter-otlp-proto-http==1.39.1` in `pyproject.toml`/`uv.lock`), while the
Langfuse Observability plugin install pulls `>=1.45` into the *shared* tools-python
site-packages. A `hermes pm sync` that re-resolves the venv to the pinned api can re-create
the skew. The durable fix is upstream: plugin extras must not leave two opentelemetry
versions on one `sys.path`, or `mcp`'s api floor must be raised with the plugin's install.

## 7. Verifying the detector itself (`scripts/otel-version-skew-probe.py`)

A detector that only ever saw the broken host proves nothing — the probe was run against
two healthy controls and one synthetic skew.

Healthy control A (host `esther`, matched old pair api/sdk both 1.39.1):

```
TraceFlags members      -> ['DEFAULT', 'SAMPLED']
ok: real span created with the resolved api+sdk — no skew detected.        (exit 0)
```

Healthy control B (host `moses`, env venv post-fix, api 1.45.0, sdk absent there):

```
ok: no span-capable sdk on this interpreter, so no skew can bite here.     (exit 0)
```

Synthetic skew (temp portion holding the OLD `opentelemetry/trace` from the 3.11 venv,
placed first on `PYTHONPATH`, with the NEW sdk from the shared tools tree; nothing on the
host was modified, the temp dir was removed afterwards):

```
opentelemetry.trace     -> /tmp/otel-skew/opentelemetry/trace/__init__.py
opentelemetry.sdk.trace -> …/tools/python-3.14.7…/site-packages/opentelemetry/sdk/trace/__init__.py
TraceFlags members      -> ['DEFAULT', 'SAMPLED']
SKEW: span creation failed on the resolved api/sdk pair — AttributeError: type object
      'TraceFlags' has no attribute 'RANDOM_TRACE_ID'                     (exit 1)
```

The first draft of the probe used a flag-existence heuristic ("sdk importable but no
`RANDOM_TRACE_ID`") and false-positived on healthy control A — a matched old pair is
perfectly fine because the old sdk never references the newer flag. The verdict is
therefore behavioural (create a span, report only a real failure); keep it that way if
this probe is ever refactored.

## Automated check (added 2026-10-06)

`agent-mcp-health-watchdog.py` runs the probe above under every agent-runtime
interpreter every 5 min. Smoke it on any host:

```bash
bash skills/devops/mcp-health-monitoring/scripts/skew-watchdog-smoke.sh
```

Captured on esther (exit 0):

```text
== 1. scenario suite (stubs) ==
PASS  A healthy binary-CLI stays silent (no 'script not found' loop)
PASS  B crashed binary fails loudly with real reason
PASS  C hanging binary fails with timeout
PASS  D python-script server stays healthy via import path
PASS  E old-API python server healthy via stdio fallback (TypeError)
PASS  P platform_toolsets children are NOT phantom servers
PASS  F missing command fails fast
PASS  G missing args fails fast
PASS  R outage->recovery emits RECOVERED notice
PASS  S strike 1 stays quiet (no alert before the 2-strike threshold)
PASS  S strike 2 alerts: GOVERNANCE OFFLINE + the interpreter + the align command
PASS  S2 skew recovery emits a recovered notice
PASS  S3 missing skew probe reports UNVERIFIED
PASS  S4 the watched probe path holds the real script (watched dependency exists)

14/14 scenarios passed
suite_exit=0

== 2. live probe, every resolved runtime interpreter ==
probe: $HOME/hermes-cortex/skills/devops/mcp-health-monitoring/scripts/otel-version-skew-probe.py
  OK   $HOME/.hermes/hermes-agent/venv/bin/python3 
  OK   $HOME/.hermes/installs/483c6efb1d92c950/environments/161f630fbf524b6dba10c7caa764b526/venv/bin/python3 
  OK   $HOME/.hermes/installs/483c6efb1d92c950/environments/391b894a13414bceb01aa62f0f7fc7d7/venv/bin/python3 
  OK   $HOME/.hermes/installs/483c6efb1d92c950/environments/6806fe6206c2476e8d2609c1e020ba54/venv/bin/python3 
watchdog output after 2 runs: (silent)
interpreters_skewed=0
live_exit=0

VERDICT: PASS — the skew check works on this host and is silent when healthy
```
