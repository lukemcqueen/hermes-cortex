"""Tests for health-server.py core logic — CPU parsing, resource checks.

⚠️ OBSOLETE — The FastAPI health-server.py has been removed in favor of
health-vector.py (zero-dependency Python stdlib). These tests are preserved
for reference only — the CPU parsing logic they test was part of the old server.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


# ── CPU parsing tests (heart of the P-01 fix) ────────────────────

SAMPLE_PROC_STAT = """cpu  123456 78901 234567 8901234 45678 9012 3456 789 0 0
cpu0 61728 39450 117283 4450617 22839 4506 1728 394 0 0
cpu1 61728 39451 117284 4450617 22839 4506 1728 395 0 0
intr 12345678 ...
ctxt 98765432
btime 1234567890
processes 54321
procs_running 1
procs_blocked 0
"""


def _parse_cpu_from_proc_stat(stat_text: str) -> float | None:
    """Extract CPU usage percentage from /proc/stat text.
    (Mirrors the logic in health-server.py's Linux code path.)
    """
    for line in stat_text.split("\n"):
        if line.startswith("cpu "):
            vals = [int(x) for x in line.split()[1:]]
            if vals:
                total = sum(vals)
                idle = vals[3]
                return round(100 * (1 - idle / total), 1) if total else 0.0
    return None


def test_parse_cpu_from_proc_stat_normal():
    """Normal case: should calculate non-zero percentage."""
    result = _parse_cpu_from_proc_stat(SAMPLE_PROC_STAT)
    assert result is not None
    assert 0.0 < result < 100.0
    # vals: [123456, 78901, 234567, 8901234, 45678, 9012, 3456, 789, 0, 0]
    # total = 9397093, idle = 8901234
    # cpu% = (1 - 8901234/9397093) * 100 ≈ 5.3%
    assert result == pytest.approx(5.3, abs=0.5)


def test_parse_cpu_from_proc_stat_all_idle():
    """All idle: should return 0.0%."""
    text = "cpu  0 0 0 99999999 0 0 0 0 0 0\n"
    result = _parse_cpu_from_proc_stat(text)
    assert result == 0.0


def test_parse_cpu_from_proc_stat_no_cpu_line():
    """Empty or missing cpu line: should return None."""
    result = _parse_cpu_from_proc_stat("")
    assert result is None
    result = _parse_cpu_from_proc_stat("btime 12345\nctxt 67890\n")
    assert result is None


def test_parse_cpu_from_proc_stat_malformed():
    """Malformed values should handle gracefully."""
    text = "cpu  123 notanumber 456\n"
    try:
        result = _parse_cpu_from_proc_stat(text)
    except (ValueError, IndexError):
        pass  # acceptable failure mode


# ── Resource thresholds ─────────────────────────────────────────

def _check_resource_issues(
    disk_percent: int,
    memory_percent: int,
) -> list[dict]:
    """Simplified version of the health check logic from health-server.py."""
    issues: list[dict] = []
    if disk_percent and disk_percent > 90:
        issues.append({"severity": "critical", "check": "resources",
                       "detail": f"Disk at {disk_percent}%"})
    elif disk_percent and disk_percent > 80:
        issues.append({"severity": "warning", "check": "resources",
                       "detail": f"Disk at {disk_percent}%"})
    if memory_percent and memory_percent > 90:
        issues.append({"severity": "critical", "check": "resources",
                       "detail": f"Memory at {memory_percent}%"})
    elif memory_percent and memory_percent > 80:
        issues.append({"severity": "warning", "check": "resources",
                       "detail": f"Memory at {memory_percent}%"})
    return issues


def test_disk_memory_thresholds():
    # No issues below threshold
    assert _check_resource_issues(70, 70) == []
    # Warning at 85%
    issues = _check_resource_issues(85, 70)
    assert any(i["severity"] == "warning" and i["check"] == "resources" for i in issues)
    # Critical at 95%
    issues = _check_resource_issues(95, 95)
    criticals = [i for i in issues if i["severity"] == "critical"]
    assert len(criticals) >= 2


# ── Service check logic ─────────────────────────────────────────

def _determine_service_status(
    launchctl_out: str | None,
    launchctl_rc: int,
    pgrep_out: str | None,
) -> tuple[str, int | None]:
    """Simplified version of the service check logic from health-server.py."""
    status = "unknown"
    pid = None

    if launchctl_out is not None:
        if launchctl_rc == 0 and launchctl_out:
            import re
            m = re.search(r'\"PID\"\s*=\s*(\d+)', launchctl_out)
            if m:
                pid = int(m.group(1))
                status = "running"
            else:
                status = "stopped"
        else:
            status = "stopped"

    if status == "unknown" and pgrep_out is not None:
        pgrep_out = pgrep_out.strip()
        if pgrep_out:
            pids = pgrep_out.split()
            pid = int(pids[0]) if pids else None
            status = "running"
        else:
            status = "stopped"

    return status, pid


def test_service_launchctl_running():
    status, pid = _determine_service_status(
        '{\n    "PID" = 12345;\n    "Label" = "com.ollama.serve";\n}\n', 0, None)
    assert status == "running"
    assert pid == 12345


def test_service_launchctl_stopped():
    status, _ = _determine_service_status("", 1, None)
    assert status == "stopped"


def test_service_pgrep_fallback():
    status, pid = _determine_service_status(None, 1, "12345\n67890")
    assert status == "running"
    assert pid == 12345


def test_service_not_found():
    status, _ = _determine_service_status(None, 1, "")
    assert status == "stopped"


# ── OS detection (cross-platform helpers) ───────────────────────

def test_os_detection():
    """Platform detection should return consistent format."""
    s = platform.system().lower()
    assert s in ("darwin", "linux", "windows")


# ── Config validation ───────────────────────────────────────────

def test_config_yaml_exists():
    """The deploy config template should exist and be valid YAML."""
    config_path = Path(__file__).parent.parent / "ops" / "install" / "deploy" / "config" / "config.yaml"
    assert config_path.exists(), f"Missing deploy/config/config.yaml"
    import yaml
    with open(config_path) as f:
        data = yaml.safe_load(f)
    assert isinstance(data, dict)
    assert "model" in data or "provider" in data


# ── Import guard ────────────────────────────────────────────────

try:
    import pytest
    import platform
except ImportError:
    pass