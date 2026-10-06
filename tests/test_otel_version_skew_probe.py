"""Contract tests for skills/devops/mcp-health-monitoring/scripts/otel-version-skew-probe.py.

The probe's verdict must be behavioural: report SKEW only when creating a span
actually fails. Both directions are pinned here against stub otel trees so the
test never depends on which otel happens to be installed on the host.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

PROBE = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "devops"
    / "mcp-health-monitoring"
    / "scripts"
    / "otel-version-skew-probe.py"
)

HEALTHY_TRACE = """
class TraceFlags(int):
    DEFAULT = 0x00
    SAMPLED = 0x01
    RANDOM_TRACE_ID = 0x02


class SpanKind:
    CLIENT = "client"


_state = {}


def set_tracer_provider(provider):
    _state["provider"] = provider
"""

HEALTHY_SDK = """
class _Span:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Tracer:
    def start_as_current_span(self, name, **kwargs):
        return _Span()


class TracerProvider:
    def get_tracer(self, name):
        return _Tracer()
"""

BROKEN_SDK = """
class _Tracer:
    def start_as_current_span(self, name, **kwargs):
        raise AttributeError(
            "type object 'TraceFlags' has no attribute 'RANDOM_TRACE_ID'"
        )


class TracerProvider:
    def get_tracer(self, name):
        return _Tracer()
"""


def _stub_tree(root: Path, trace_src: str, sdk_src: str) -> Path:
    """Build a minimal `opentelemetry` package tree for PYTHONPATH."""
    pkg = root / "opentelemetry"
    (pkg / "trace").mkdir(parents=True)
    (pkg / "sdk" / "trace").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "trace" / "__init__.py").write_text(textwrap.dedent(trace_src))
    (pkg / "sdk" / "__init__.py").write_text("")
    (pkg / "sdk" / "trace" / "__init__.py").write_text(textwrap.dedent(sdk_src))
    return root


def _run_probe(pythonpath: Path) -> subprocess.CompletedProcess:
    # -S keeps the host's real site-packages out of the picture, so the only
    # opentelemetry visible is the stub tree on PYTHONPATH.
    return subprocess.run(
        [sys.executable, "-S", str(PROBE)],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(pythonpath)},
        timeout=120,
        check=False,
    )


def test_healthy_pair_reports_no_skew(tmp_path):
    """A matched api/sdk pair must pass — this is the false-positive control."""
    result = _run_probe(_stub_tree(tmp_path, HEALTHY_TRACE, HEALTHY_SDK))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "no skew detected" in result.stdout
    assert "SKEW:" not in result.stdout


def test_span_failure_is_reported_as_skew(tmp_path):
    """A resolving pair whose span creation raises must be reported as skew."""
    result = _run_probe(_stub_tree(tmp_path, HEALTHY_TRACE, BROKEN_SDK))

    assert result.returncode == 1, result.stdout + result.stderr
    assert "SKEW:" in result.stdout
    assert "RANDOM_TRACE_ID" in result.stdout


def test_missing_otel_is_not_a_failure(tmp_path):
    """No otel at all is 'nothing to skew', never an alarm."""
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _run_probe(empty)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "nothing to skew" in result.stdout
