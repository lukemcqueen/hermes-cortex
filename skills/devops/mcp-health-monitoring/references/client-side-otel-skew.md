# Client-side OTel namespace skew — worked diagnosis, repro and verification

Reference recipe for the failure class in SKILL.md § "Client-Side MCP Outage". Every
block below is captured output from a real occurrence, kept because the shape of the
proof is the reusable part: which file to read, what the merge looks like, and how the
fix is verified end-to-end.

## 1. Symptom — servers healthy, client broken

```
ERROR tools.mcp_tool: MCP tool loop-governance/cache_search call failed:
  type object 'TraceFlags' has no attribute 'RANDOM_TRACE_ID'
ERROR tools.mcp_tool: MCP tool cortex-bus/inbox_read call failed:
  type object 'TraceFlags' has no attribute 'RANDOM_TRACE_ID'
WARNING hermes_cli.plugins: Hook 'pre_api_request' callback on_pre_llm_request raised:
  'TraceFlags' object has no attribute 'random_trace_id'
```

`hermes mcp list` showed every server enabled and the servers' own `mcp-stderr.log`
contained no `TraceFlags` line. Read `ERROR tools.mcp_tool: … call failed` — that is the
client-side line; the servers never see the exception.

## 2. Two otel trees on one runtime path

```
# the install's environment venv (the runtime that failed)
opentelemetry_api-1.39.1.dist-info          # required by mcp 2.0.0 (Requires-Dist: opentelemetry-api>=1.28.0)
# shared tools-python site-packages
langfuse-4.16.0.dist-info                   # Requires-Dist: opentelemetry-api>=1.45.0,<2
opentelemetry_sdk-1.45.0.dist-info
opentelemetry_exporter_otlp_proto_http-1.45.0.dist-info
```

`opentelemetry` has no `__init__.py` in either tree — it is a PEP 420 namespace package,
so the two portions MERGE instead of one shadowing the other:

```
$ <env-venv>/bin/python3 -c "import opentelemetry; print(opentelemetry.__file__, list(opentelemetry.__path__))"
None ['…/installs/<id>/environments/<id>/venv/lib/python3.14/site-packages/opentelemetry',
      '…/.hermes/tools/python-3.14.7…/lib/python3.14/site-packages/opentelemetry']
```

## 3. Repro harness (fails before the fix, passes after)

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

Skewed (captured):

```
trace module:  …/venv/lib/python3.14/site-packages/opentelemetry/trace/__init__.py
TraceFlags attrs: ['DEFAULT', 'SAMPLED']
sdk module:    …/.hermes/tools/python-3.14.7…/site-packages/opentelemetry/sdk/trace/__init__.py
  File "…/site-packages/opentelemetry/sdk/trace/__init__.py", line 1185, in start_span
    trace_flags = trace_api.TraceFlags(trace_flags | trace_api.TraceFlags.RANDOM_TRACE_ID)
AttributeError: type object 'TraceFlags' has no attribute 'RANDOM_TRACE_ID'
```

Aligned (same harness): `TraceFlags attrs: ['DEFAULT', 'RANDOM_TRACE_ID', 'SAMPLED']` → `SPAN OK`.

## 4. Fix (one command, host-local)

```
uv pip install --python <env-venv>/bin/python3 "opentelemetry-api==1.45.0"
  - opentelemetry-api==1.39.1
  + opentelemetry-api==1.45.0
```

Safe because `mcp` needs only `opentelemetry-api>=1.28.0`, and aligning at the sdk's
version also satisfies the plugin that required the newer api.

## 5. Verification — three layers, real output

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

4. `errors.log` shows no `TraceFlags` line after the fix (compare the last pre-fix entry's
timestamp against the live session's).

## 6. Why the fix is not durable by itself

A repo pin on the otlp extra (`opentelemetry-sdk==<old>`) coexists with a plugin install
that demands `>=<new>` into the *shared* tools-python site-packages. A later
`hermes pm sync` that re-resolves the venv to the pinned older api re-creates the skew.
The durable fix is upstream: plugin extras must not leave two opentelemetry versions on
one `sys.path`, or the MCP client's api floor must be raised with the plugin's install.
Re-pinning locally is interim — say so when reporting.

## 7. Verifying the detector itself (`scripts/otel-version-skew-probe.py`)

A detector that only ever saw the broken host proves nothing — run it against healthy
controls and a synthetic skew before trusting it.

Healthy control (matched old pair, api and sdk both on the same floor):

```
TraceFlags members      -> ['DEFAULT', 'SAMPLED']
ok: real span created with the resolved api+sdk — no skew detected.        (exit 0)
```

Synthetic skew (a temp portion holding an OLD `opentelemetry/trace` placed first on
`PYTHONPATH`, with the NEW sdk from the shared tools tree; nothing on the host was
modified and the temp dir was removed afterwards):

```
opentelemetry.trace     -> /tmp/otel-skew/opentelemetry/trace/__init__.py
opentelemetry.sdk.trace -> …/tools/python-3.14.7…/site-packages/opentelemetry/sdk/trace/__init__.py
TraceFlags members      -> ['DEFAULT', 'SAMPLED']
SKEW: span creation failed on the resolved api/sdk pair — AttributeError: type object
      'TraceFlags' has no attribute 'RANDOM_TRACE_ID'                     (exit 1)
```

The first draft used a flag-existence heuristic ("sdk importable but no
`RANDOM_TRACE_ID`") and false-positived on the healthy control — a matched old pair is
fine because the old sdk never references the newer flag. Keep the verdict BEHAVIOURAL
(exercise the real path, report only a real failure); a mutation that removes the
behavioural step must flip the test red, which is the only proof the test is not vacuous.
