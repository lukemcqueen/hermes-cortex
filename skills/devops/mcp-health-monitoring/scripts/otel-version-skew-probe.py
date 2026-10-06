#!/usr/bin/env python3
"""Detect OpenTelemetry namespace-package version skew on the CURRENT interpreter.

Failure class (2026-10-06, host moses): every MCP tool call failed with
`AttributeError: type object 'TraceFlags' has no attribute 'RANDOM_TRACE_ID'`
while all MCP servers were healthy. Cause: `opentelemetry` is a PEP 420
namespace package, so two site-packages on one sys.path are MERGED — the
runtime's older `opentelemetry-api` (e.g. 1.39.1, pulled in by `mcp>=2.0`)
answered for `opentelemetry.trace` while a newer tree's `opentelemetry-sdk`
(e.g. 1.45.0, pulled in with the Langfuse Observability plugin) supplied
`start_span`, which needs `TraceFlags.RANDOM_TRACE_ID` from the newer api.

The verdict is BEHAVIOURAL, not a version heuristic: a matched pair of old
api + old sdk (1.39.1/1.39.1) is perfectly healthy and must not be reported,
so the probe actually creates a span with a real TracerProvider and reports
SKEW only when that raises. (An earlier flag-existence heuristic false-positived
on exactly that healthy pair — the probe gets tested against the control too.)

Run it with the interpreter that serves the agent/MCP client, e.g.
    <env-venv>/bin/python3 otel-version-skew-probe.py
Exit 0 = no skew, 1 = skew detected, 2 = probe error.
Read-only for the host: it never writes files and never opens a governance lock.
It does install a TracerProvider in its own process, which is discarded on exit.
"""

from __future__ import annotations

import importlib
import sys
import traceback
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _module_file(name: str) -> str:
    """Where `name` resolves to, or a marker saying it cannot be imported."""
    try:
        module = importlib.import_module(name)
    except ModuleNotFoundError:
        return "<not importable>"
    return getattr(module, "__file__", None) or "<namespace portion, no __init__.py>"


def _version(dist: str) -> str:
    try:
        return version(dist)
    except PackageNotFoundError:
        return "<absent>"


def _span_smoke_test() -> str:
    """Create one real span with a real provider. Returns '', or the failure text."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.trace import SpanKind, set_tracer_provider

    set_tracer_provider(TracerProvider())
    try:
        with TracerProvider().get_tracer("otel-version-skew-probe").start_as_current_span(
            "probe", kind=SpanKind.CLIENT
        ):
            pass
    except AttributeError as exc:
        return f"{type(exc).__name__}: {exc}"
    except Exception as exc:  # a non-AttributeError failure is still worth surfacing
        return f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    return ""


def main() -> int:
    try:
        trace = importlib.import_module("opentelemetry.trace")
    except ModuleNotFoundError:
        print("otel-version-skew: no opentelemetry-api on this interpreter — nothing to skew.")
        return 0

    flags = sorted(a for a in dir(trace.TraceFlags) if a.isupper())
    trace_file = _module_file("opentelemetry.trace")
    sdk_file = _module_file("opentelemetry.sdk.trace")

    portions: list[str] = []
    namespace = False
    try:
        pkg = importlib.import_module("opentelemetry")
        portions = [str(Path(p)) for p in list(getattr(pkg, "__path__", []))]
        namespace = getattr(pkg, "__file__", None) is None
    except ModuleNotFoundError:
        pass

    print(f"interpreter             : {sys.executable}")
    print(f"python                  : {sys.version.split()[0]}")
    print(f"opentelemetry-api       : {_version('opentelemetry-api')}")
    print(f"opentelemetry-sdk       : {_version('opentelemetry-sdk')}")
    print(f"namespace-merge         : {namespace}")
    if portions:
        print("portions                :")
        for part in portions:
            print(f"  - {part}")
    print(f"opentelemetry.trace     -> {trace_file}")
    print(f"opentelemetry.sdk.trace -> {sdk_file}")
    print(f"TraceFlags members      -> {flags}")

    if sdk_file == "<not importable>":
        print("ok: no span-capable sdk on this interpreter, so no skew can bite here.")
        return 0

    failure = _span_smoke_test()
    if not failure:
        print("ok: real span created with the resolved api+sdk — no skew detected.")
        return 0

    print(f"SKEW: span creation failed on the resolved api/sdk pair — {failure}")
    print(
        "Every `mcp` tools/call is wrapped in such a span, so ALL MCP tools fail here.\n"
        "Align the pair with: uv pip install --python "
        f"{sys.executable} 'opentelemetry-api=={_version('opentelemetry-sdk')}'"
    )
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # probe must fail LOUD, never silently report "clean"
        print(f"probe error: {type(exc).__name__}: {exc}")
        raise SystemExit(2) from exc
